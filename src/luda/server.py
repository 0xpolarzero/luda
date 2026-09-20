import argparse
import asyncio
from importlib.metadata import version
import atexit
from collections import deque
import json
import threading
import time
from typing import Literal
import uuid

import anyio
from .protocol import DesktopMCP
from .identity import version_identity
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations

from .common import DesktopError, operation_scope, checkpoint, environment_scope
from .session_reconnect import prepare_reconnect
from .keyboard import set_recovery_hooks, recover_keyboard_input
from .desktop import Desktop
from .apps import list_applications, launch_application
from .session_state import require_session_input

mcp = DesktopMCP('luda', product_version=version('luda'), instructions='Local desktop: observe, select a window, inspect its controls, then act. Screenshot coordinates use the returned image, with its snapshot ID. Text replacement and insertion are distinct. Verify dispatched actions before repeating them; cancellation or timeout can leave effects. Use desktop_status to inspect recent operation outcomes.')
backend = None
_backend_lock = threading.RLock()
_operation_gate = threading.Lock()
_history_lock = threading.Lock()
_history = deque(maxlen=32)
_quarantined = threading.Event()
_quarantine_lock = threading.Lock()
_quarantine_owners = set()


def _retain_quarantine(task):
    with _quarantine_lock:
        _quarantine_owners.add(task)
        _quarantined.set()


def _release_quarantine(task):
    with _quarantine_lock:
        _quarantine_owners.discard(task)
        if not _quarantine_owners:
            _quarantined.clear()


set_recovery_hooks(_retain_quarantine, _release_quarantine)

def get_backend():
    global backend
    with _backend_lock:
        if backend is None:
            backend = Desktop()
            atexit.register(backend.close)
        return backend


def result_error(code, message, effect='none', **details):
    return CallToolResult(isError=True, content=[TextContent(type='text', text=json.dumps(
        {'ok':False, 'code':code, 'message':message, 'effect':effect, **details}, ensure_ascii=False,separators=(',',':')))])


def execute(method, *args, _cancelled=None, **kwargs):
    global backend
    acquired = False
    started = time.monotonic()
    operation_id = uuid.uuid4().hex
    event = {'operation_id':operation_id, 'method':method}
    if method == 'element' and len(args) > 1:
        from .reporting import ELEMENT_ACTIONS
        if isinstance(args[1], str) and args[1] in ELEMENT_ACTIONS:
            event['action'] = args[1]
    try:
        if _quarantined.is_set() and method != 'recover_input':
            raise DesktopError('BUSY', 'Previous cancelled operation is still cleaning up; no new input sent.')
        acquired = _operation_gate.acquire(blocking=False)
        if not acquired:
            raise DesktopError('BUSY', 'Another operation is in progress; reconnect does not cancel it.')
        d = get_backend()
        observation = method in ('reconnect','list_applications','doctor','list_windows','window_overview','observe','ocr','inspect','workspaces','wait_for','wait_condition') or (method=='element' and len(args)>1 and args[1]=='read')
        guard = None if observation or method == 'recover_input' else d.control.require_active
        with operation_scope(timeout=12, cancelled=_cancelled, guard=guard) as operation:
            try:
                if method == 'recover_input':
                    # Recovery releases only recorded ownership. It must work
                    # while paused/quarantined, without entering the ordinary
                    # transaction that intentionally refuses pending cleanup.
                    with environment_scope(d.environment):
                        result = recover_keyboard_input()
                    result['recovering'] = _quarantined.is_set()
                elif method == 'reconnect':
                    with prepare_reconnect(d, args[0] if args else None, Desktop) as (candidate, result):
                        checkpoint()
                        with _backend_lock:
                            backend = candidate
                            atexit.register(candidate.close)
                    d.close()
                    atexit.unregister(d.close)
                else:
                    with d.transaction():
                        if method not in ('doctor', 'list_applications'):
                            d.require_supported_backend()
                        if not observation:
                            require_session_input()
                        application_methods = {'list_applications':list_applications, 'launch_application':launch_application}
                        handler = application_methods[method] if method in application_methods else getattr(d,method)
                        result = handler(*args,**kwargs)
            except DesktopError as exc:
                if operation.effect != 'none' and exc.effect == 'none':
                    exc.effect = 'uncertain'
                    exc.details['prior_effects_possible'] = True
                raise
        if not isinstance(result,dict):
            result={('windows' if method=='list_windows' else 'workspaces' if method=='workspaces' else 'items'):result}
        image = result.pop('image_base64',None)
        result={'ok':True,'operation_id':operation_id,'elapsed_ms':round((time.monotonic()-started)*1000),**result}
        event.update(ok=True, effect=result.get('effect','none'))
        content=[TextContent(type='text',text=json.dumps(result,ensure_ascii=False,separators=(',',':')))]
        if image:
            content.append(ImageContent(type='image',data=image,mimeType='image/png'))
        return CallToolResult(content=content,isError=False)
    except DesktopError as exc:
        event.update(ok=False, code=exc.code, effect=exc.effect)
        return result_error(exc.code,str(exc),exc.effect,details=exc.details,operation_id=operation_id,elapsed_ms=round((time.monotonic()-started)*1000))
    except Exception:
        # Exception text/repr can contain protected input or provider contents.
        # Correlate with metadata-only history rather than returning that text.
        event.update(ok=False, code='INTERNAL_ERROR', effect='uncertain')
        return result_error('INTERNAL_ERROR', 'Unexpected backend failure. Inspect desktop_status and current application state before retrying; input may already have occurred.', 'uncertain', operation_id=operation_id, elapsed_ms=round((time.monotonic()-started)*1000))
    finally:
        if acquired:
            _operation_gate.release()
        event['elapsed_ms'] = round((time.monotonic()-started)*1000)
        with _history_lock:
            _history.append(event)


async def execute_async(method, *args, **kwargs):
    cancelled = threading.Event()
    task = asyncio.create_task(asyncio.to_thread(execute, method, *args, _cancelled=cancelled, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        cancelled.set()
        # Let the worker stop its child and release input/lock before accepting
        # more mutations. If it cannot, quarantine instead of racing it.
        _retain_quarantine(task)
        task.add_done_callback(_release_quarantine)
        with anyio.CancelScope(shield=True):
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass  # This task's completion callback owns its recovery lease.
            finally:
                if task.done():
                    _release_quarantine(task)  # Idempotent if callback already ran.
        raise


@mcp.tool()
async def desktop_control(action: Literal['status','pause','resume']='status') -> CallToolResult:
    """Pause/resume cooperating agent input across servers on this display. Pause interrupts at the next checkpoint; already-delivered input is not undone. Observation remains available. This does not stop arbitrary external input programs."""
    try:
        # Linearize control's selected display with reconnect's backend swap.
        with _backend_lock:
            control = get_backend().control
            state = control.status() if action=='status' else control.set_paused(action=='pause')
        return CallToolResult(content=[TextContent(type='text',text=json.dumps({'ok':True,**state},separators=(',',':')))])
    except DesktopError as exc:
        return result_error(exc.code,str(exc),exc.effect)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_ocr(snapshot_id: str, language: str = 'eng', limit: int = 200) -> CallToolResult:
    """Read uncertain local OCR word candidates from this exact retained screenshot, never a new capture. Returns image-pixel boxes and uncalibrated engine scores, not exact text or action permission. Snapshot expires after 15 seconds or cache eviction; changed layout is refused. Optional Tesseract and the selected language must be installed. No input is sent."""
    return await execute_async('ocr', snapshot_id, language, limit)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_status() -> CallToolResult:
    """Return recent operation outcomes after timeout/cancellation. No input text or screenshots are retained."""
    with _history_lock:
        history = list(_history)
    return CallToolResult(content=[TextContent(type='text',text=json.dumps({'ok':True,'recovering':_quarantined.is_set(),'operations':history},separators=(',',':')))])


async def _collect_report(cli=False):
    from .reporting import build_report
    with _history_lock:
        history = list(_history)
    try:
        probe = await desktop_doctor()
        health = json.loads(probe.content[0].text) if not probe.isError else {}
    except Exception:
        health = {}
    return await anyio.to_thread.run_sync(lambda: build_report(health, history, cli=cli, recovering=_quarantined.is_set()))


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_report() -> CallToolResult:
    """Return a sanitized bug-report JSON: fixed environment/dependency versions, projected health and up to 32 recent operation IDs/methods/effects/timings, fixed error codes and semantic verbs from this MCP process. Excludes desktop content, paths, exceptions and action arguments. No files, uploads or replay. Supply synthetic repro steps separately; explicitly save/delete the returned report if needed."""
    report = await _collect_report()
    return CallToolResult(content=[TextContent(type='text', text=json.dumps(report, separators=(',', ':')))])


@mcp.tool()
async def desktop_recover_input() -> CallToolResult:
    """Retry cleanup of this server's interrupted supervised input, without replaying keys/clicks or resuming a paused desktop. Uses each operation's original session; a replaced X server is left untouched. Unproven cleanup stays blocked. Returns pending_count and recovery proofs; observe again before acting. Returns BUSY if another operation is still running."""
    return await execute_async('recover_input')


@mcp.tool()
async def desktop_reconnect(session_pid: int | None = None) -> CallToolResult:
    """Reconnect this MCP connection to a running XFCE session owned by this account after a desktop restart. Omit PID only when exactly one session exists. Validates display and bus before replacing the backend; failed validation preserves it. Returns BUSY during other operations, never restarts apps or replays input. All prior window, element and screenshot IDs expire; observe again. The selected display's pause state remains in force."""
    return await execute_async('reconnect', session_pid)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_doctor() -> CallToolResult:
    """Check actual display access, desktop session, dependencies and accessibility availability. Reports driver version and content identities for tool declarations and the server-bundled skill; the latter does not identify the skill loaded by your agent."""
    response = await execute_async('doctor')
    if not response.isError:
        payload = json.loads(response.content[0].text)
        payload['versions'] = version_identity([tool.model_dump(mode='json', exclude_none=True) for tool in await mcp.list_tools()])
        response.content[0].text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    return response


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_applications(query: str = '', limit: int = 50) -> CallToolResult:
    """Find installed desktop applications by name, description or ID. Returns application_id and file/URI support; works while input is paused. Use an exact returned ID with desktop_launch."""
    return await execute_async('list_applications',query,limit)


@mcp.tool()
async def desktop_launch(application_id: str, files_or_uris: list[str] | None = None) -> CallToolResult:
    """Launch an installed application by its desktop_applications ID, optionally opening absolute existing paths or URIs. No command strings. Returns dispatched, not ready: inspect desktop_windows for the new or existing app; never blindly retry an uncertain launch."""
    return await execute_async('launch_application',application_id,files_or_uris)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_windows(query: str | None = None, limit: int = 50, offset: int = 0) -> CallToolResult:
    """List window identities, titles, focus and client bounds, optionally filtering title/class. Returns counts, unavailable rows and next_offset when paginated. Each call is a fresh enumeration."""
    return await execute_async('window_overview',query,limit,offset)


@mcp.tool()
async def desktop_activate(window_id: str) -> CallToolResult:
    """Activate a window from desktop_windows and verify focus. Observe again afterward."""
    return await execute_async('activate',window_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_observe(max_width: int = 1280) -> CallToolResult:
    """Return screenshot plus window layout and a 15-second snapshot ID. Pointer coordinates and window/popup image_bounds use returned-image pixels; bounds/frame_bounds remain native X11 root pixels. image_bounds is null when no integer screenshot pixel maps into the client. Use integer image points."""
    return await execute_async('observe',max_width)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_inspect(window_id: str, limit: int = 150, name: str | None = None, role: str | None = None, states: list[str] | None = None, max_depth: int = 30) -> CallToolResult:
    """Inspect a window or find controls by name/role substring and required states. Returns bounded tree, parent IDs, supported actions and 60-second element IDs. Empty matches and unavailable accessibility are distinct."""
    return await execute_async('inspect',window_id,limit,name=name,role=role,states=states,max_depth=max_depth)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_read_text(element_id: str, limit: int = 16000) -> CallToolResult:
    """Read accessible text and representation metadata, preserving whitespace. limit counts Unicode code points (default 16000, maximum 1000000), not bytes. Opaque embedded objects are not exact logical plain text: check plain_text_verification_supported. Normalization reads the bounded full field; a smaller limit does not enable streaming. Protected fields are refused."""
    if not 1<=limit<=1_000_000:
        return result_error('INVALID_ARGUMENT', 'limit must be 1–1000000')
    return await execute_async('element',element_id,'read',limit=limit)


@mcp.tool()
async def desktop_type(element_id: str, text: str, mode: Literal["insert", "replace"] = "insert") -> CallToolResult:
    """Type into an editable element and verify exact readback. Default insert preserves surrounding text and replaces the selection; replace changes the entire field. Preserves Unicode/LF/tabs, never adds a submit key. Exact readback does not prove application commit or guarantee autocomplete events; inspect the result before an explicit commit or suggestion selection."""
    return await execute_async('type_text',element_id,text,mode)


@mcp.tool()
async def desktop_type_secret(element_id: str, text: str) -> CallToolResult:
    """Replace an observed protected field. Never reads back or echoes the value, uses no clipboard, and reports dispatched only. Requires protected EditableText support; submission is a separate action."""
    return await execute_async('element',element_id,'secret',text=text)


@mcp.tool()
async def desktop_choose(element_id: str, extend: bool = False) -> CallToolResult:
    """Choose an observed list/radio/combo option or a visible table cell and verify selection. A table cell selects its whole row. Default makes the choice exclusive; extend preserves other list or table-row selections. Scroll offscreen rows into view and inspect again; reacquire after sorting/filtering. Open collapsed options and inspect first."""
    return await execute_async('element',element_id,'choose',extend=extend)


@mcp.tool()
async def desktop_paste(window_id: str, text: str, shortcut: Literal['ctrl_v','ctrl_shift_v','shift_insert'] | None = None) -> CallToolResult:
    """Paste through CLIPBOARD when semantic typing is unavailable. Chooses common app shortcut from window class, with optional override. Destination is unverified; inspect dialogs/read back. Terminals can execute pasted newlines."""
    return await execute_async('paste',window_id,text,shortcut)


@mcp.tool()
async def desktop_press_keys(window_id: str, chord: str, count: int = 1) -> CallToolResult:
    """Send a deliberate chord, e.g. ctrl+s, ctrl+plus, ctrl+minus, Return, Tab, Escape or Down. Punctuation uses X11 names (plus, equal, bracketleft, slash); implicit Shift follows the current layout. count is 1–20 complete press/release repetitions, default 1. Revalidates target identity, focus and input state between repetitions; stops on the first failure and never retries. Requires target focus, refuses held keys/buttons, and preserves the current keyboard mapping. Unavailable symbols return UNSUPPORTED_KEYMAP; text belongs in desktop_type. Dispatched count is not application completion."""
    return await execute_async('key',window_id,chord,count)


@mcp.tool()
async def desktop_click(window_id: str, snapshot_id: str, x: float, y: float, button: Literal['left','middle','right']='left', count: Literal[1,2,3]=1) -> CallToolResult:
    """Click screenshot-image coordinates in the active window or its observed menus. Rejects expired snapshots, changed window layout/identity and covered targets. Snapshot validity does not prove unchanged application content; observe again after content transitions before selecting a control."""
    return await execute_async('pointer',window_id,snapshot_id,x,y,button=button,count=count)


@mcp.tool()
async def desktop_scroll(window_id: str, snapshot_id: str, x: float, y: float, direction: Literal['up','down','left','right'], ticks: int=3) -> CallToolResult:
    """Scroll 1–20 wheel ticks at a point in the observed active target. Read resulting state to confirm."""
    return await execute_async('pointer',window_id,snapshot_id,x,y,kind='scroll',direction=direction,count=ticks)


@mcp.tool()
async def desktop_drag(window_id: str, snapshot_id: str, x: float, y: float, end_x: float, end_y: float, button: Literal['left','middle','right']='left') -> CallToolResult:
    """Drag between two observed points inside the same active window; always attempts button release. Use desktop_drag_to for another destination window."""
    return await execute_async('pointer',window_id,snapshot_id,x,y,kind='drag',button=button,end_x=end_x,end_y=end_y)


@mcp.tool()
async def desktop_focus_element(element_id: str) -> CallToolResult:
    """Request accessibility focus in the active window. Inspect to confirm focused state."""
    return await execute_async('element',element_id,'focus')


@mcp.tool()
async def desktop_invoke(element_id: str, action: str | None = None) -> CallToolResult:
    """Invoke the sole action returned by inspect, or supply its exact action name. Multiple actions require an explicit choice; no click/press naming guess is needed for a single-action button. Completion means dispatch, not verified application outcome."""
    return await execute_async('element',element_id,'invoke',action=action)


@mcp.tool()
async def desktop_select(element_id: str, start_offset: int, end_offset: int) -> CallToolResult:
    """Select a text range using Unicode code-point offsets, or place caret when equal; verify the result."""
    return await execute_async('element',element_id,'select',start_offset=start_offset,end_offset=end_offset)


@mcp.tool()
async def desktop_set_value(element_id: str, value: float) -> CallToolResult:
    """Set a numeric control within its inspected range and verify its accessibility numeric value. Displayed formatting and application commit may differ; inspect/read both, then explicitly commit only when intended."""
    return await execute_async('element',element_id,'value',value=value)


@mcp.tool()
async def desktop_set_checked(element_id: str, checked: bool) -> CallToolResult:
    """Set a checkable control to the requested state; avoid a blind toggle when it already matches."""
    return await execute_async('element',element_id,'check',checked=checked)


@mcp.tool()
async def desktop_set_expanded(element_id: str, expanded: bool) -> CallToolResult:
    """Expand or collapse a supported control and verify state. Reinspect newly exposed children."""
    return await execute_async('element',element_id,'expand',expanded=expanded)


@mcp.tool()
async def desktop_window(window_id: str, action: Literal['move','resize','maximize','minimize','fullscreen','raise','restore','close','workspace'], x: int | None = None, y: int | None = None, width: int | None = None, height: int | None = None, workspace: int | None = None) -> CallToolResult:
    """Manage one window. move uses frame x/y; resize uses client width/height; workspace requires its index. fullscreen requests WM fullscreen; restore exits fullscreen/maximization/minimization; raise changes stacking without activation. Other actions take no extra parameters. Close reports an owned blocking dialog without confirming it."""
    return await execute_async('manage_window',window_id,action,x=x,y=y,width=width,height=height,workspace=workspace)


@mcp.tool()
async def desktop_workspaces(workspace: int | None = None) -> CallToolResult:
    """List workspaces, or switch to an existing index and verify the active workspace."""
    return await execute_async('workspaces') if workspace is None else await execute_async('switch_workspace',workspace)


@mcp.tool()
async def desktop_hover(window_id: str, snapshot_id: str, x: float, y: float) -> CallToolResult:
    """Move the pointer to a recent observed point without clicking; observe tooltips/submenus afterward."""
    return await execute_async('hover',window_id,snapshot_id,x,y)


@mcp.tool()
async def desktop_drag_to(source_window_id: str, target_window_id: str, snapshot_id: str, x: float, y: float, end_x: float, end_y: float, button: Literal['left','middle','right'] = 'left') -> CallToolResult:
    """Drag from the active source into a second observed window. Coordinates refer to one screenshot. Verify transfer in the applications; dispatch does not prove a drop was accepted."""
    return await execute_async('drag_between',source_window_id,target_window_id,snapshot_id,x,y,end_x,end_y,button)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_wait(condition: Literal['window_present','window_absent','window_active','text_equals','text_contains','element_present','element_absent','pixels_stable'], window_id: str | None = None, element_id: str | None = None, text: str | None = None, timeout: float = 5, name: str | None = None, role: str | None = None, states: list[str] | None = None, stable_for: float = .3) -> CallToolResult:
    """Wait for a bounded observed condition. Element waits use fresh name/role substring and required-state filters; absence requires complete coverage. pixels_stable samples the target client rectangle for stable_for seconds, not general application idleness."""
    return await execute_async('wait_condition',condition,window_id=window_id,element_id=element_id,text=text,timeout=timeout,name=name,role=role,states=states,stable_for=stable_for)



def main():
    parser = argparse.ArgumentParser(description='Luda local desktop MCP server and session controls')
    parser.add_argument('--version',action='version',version=version('luda'))
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('doctor',help='Print real desktop readiness as JSON')
    sub.add_parser('report',help='Print sanitized bug-report JSON; no earlier-process history')
    control = sub.add_parser('control',help='Coordinate human/agent input on this display')
    control.add_argument('action',choices=['status','pause','resume'])
    args = parser.parse_args()
    if args.command=='report':
        print(json.dumps(asyncio.run(_collect_report(cli=True)), separators=(',', ':')))
        return
    if args.command=='doctor':
        result = asyncio.run(desktop_doctor())
        print(result.content[0].text)
        raise SystemExit(1 if result.isError or not json.loads(result.content[0].text).get('ready') else 0)
    if args.command=='control':
        result = asyncio.run(desktop_control(args.action))
        print(result.content[0].text)
        raise SystemExit(1 if result.isError else 0)
    mcp.run(transport='stdio')


if __name__=='__main__':
    main()
