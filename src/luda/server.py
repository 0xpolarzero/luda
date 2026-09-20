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
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations

from .common import DesktopError, operation_scope, checkpoint
from .session_reconnect import prepare_reconnect
from .keyboard import set_recovery_hooks
from .desktop import Desktop
from .apps import list_applications, launch_application

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
        {'ok':False, 'code':code, 'message':message, 'effect':effect, **details}, ensure_ascii=False))])


def execute(method, *args, _cancelled=None, **kwargs):
    global backend
    acquired = False
    started = time.monotonic()
    operation_id = uuid.uuid4().hex
    event = {'operation_id':operation_id, 'method':method}
    try:
        if _quarantined.is_set():
            raise DesktopError('BUSY', 'Previous cancelled operation is still cleaning up; no new input sent.')
        acquired = _operation_gate.acquire(blocking=False)
        if not acquired:
            raise DesktopError('BUSY', 'Another operation is in progress; reconnect does not cancel it.')
        d = get_backend()
        observation = method in ('reconnect','list_applications','doctor','list_windows','window_overview','observe','inspect','workspaces','wait_for','wait_condition') or (method=='element' and len(args)>1 and args[1]=='read')
        guard = None if observation else d.control.require_active
        with operation_scope(timeout=12, cancelled=_cancelled, guard=guard) as operation:
            try:
                if method == 'reconnect':
                    with prepare_reconnect(d, args[0] if args else None, Desktop) as (candidate, result):
                        checkpoint()
                        with _backend_lock:
                            backend = candidate
                            atexit.register(candidate.close)
                    d.close()
                    atexit.unregister(d.close)
                else:
                    with d.transaction():
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
        content=[TextContent(type='text',text=json.dumps(result,ensure_ascii=False))]
        if image:
            content.append(ImageContent(type='image',data=image,mimeType='image/png'))
        return CallToolResult(content=content,isError=False)
    except DesktopError as exc:
        event.update(ok=False, code=exc.code, effect=exc.effect)
        return result_error(exc.code,str(exc),exc.effect,details=exc.details,operation_id=operation_id)
    except Exception as exc:
        event.update(ok=False, code='INTERNAL_ERROR', effect='uncertain')
        return result_error('INTERNAL_ERROR', str(exc)[:400], 'uncertain', operation_id=operation_id)
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
        return CallToolResult(content=[TextContent(type='text',text=json.dumps({'ok':True,**state}))])
    except DesktopError as exc:
        return result_error(exc.code,str(exc),exc.effect)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_status() -> CallToolResult:
    """Return recent operation outcomes after timeout/cancellation. No input text or screenshots are retained."""
    with _history_lock:
        history = list(_history)
    return CallToolResult(content=[TextContent(type='text',text=json.dumps({'ok':True,'recovering':_quarantined.is_set(),'operations':history}))])


@mcp.tool()
async def desktop_reconnect(session_pid: int | None = None) -> CallToolResult:
    """Reconnect this MCP connection to a running XFCE session owned by this account after a desktop restart. Omit PID only when exactly one session exists. Validates display and bus before replacing the backend; failed validation preserves it. Returns BUSY during other operations, never restarts apps or replays input. All prior window, element and screenshot IDs expire; observe again. The selected display's pause state remains in force."""
    return await execute_async('reconnect', session_pid)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_doctor() -> CallToolResult:
    """Check actual display access, desktop session, dependencies and accessibility availability."""
    return await execute_async('doctor')


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
    """Return screenshot plus window layout and a 15-second snapshot ID. Coordinates are image pixels."""
    return await execute_async('observe',max_width)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_inspect(window_id: str, limit: int = 150, name: str | None = None, role: str | None = None, states: list[str] | None = None, max_depth: int = 30) -> CallToolResult:
    """Inspect a window or find controls by name/role substring and required states. Returns bounded tree, parent IDs, supported actions and 60-second element IDs. Empty matches and unavailable accessibility are distinct."""
    return await execute_async('inspect',window_id,limit,name=name,role=role,states=states,max_depth=max_depth)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def desktop_read_text(element_id: str, limit: int = 16000) -> CallToolResult:
    """Read exact accessible text, preserving whitespace. Protected fields are unsupported. Maximum 1 MB."""
    if not 1<=limit<=1_000_000:
        return result_error('INVALID_ARGUMENT', 'limit must be 1–1000000')
    return await execute_async('element',element_id,'read',limit=limit)


@mcp.tool()
async def desktop_type(element_id: str, text: str, mode: Literal["insert", "replace"] = "insert") -> CallToolResult:
    """Type into an editable element and verify exact readback. Default insert preserves surrounding text and replaces the selection; replace changes the entire field. Preserves Unicode/LF/tabs, never adds a submit key."""
    return await execute_async('type_text',element_id,text,mode)


@mcp.tool()
async def desktop_type_secret(element_id: str, text: str) -> CallToolResult:
    """Replace an observed protected field. Never reads back or echoes the value, uses no clipboard, and reports dispatched only. Requires protected EditableText support; submission is a separate action."""
    return await execute_async('element',element_id,'secret',text=text)


@mcp.tool()
async def desktop_choose(element_id: str, extend: bool = False) -> CallToolResult:
    """Choose an observed list option, radio or supported combo option and verify selection. Default makes the choice exclusive; extend preserves other list selections. Open collapsed options and inspect first."""
    return await execute_async('element',element_id,'choose',extend=extend)


@mcp.tool()
async def desktop_paste(window_id: str, text: str, shortcut: Literal['ctrl_v','ctrl_shift_v','shift_insert'] | None = None) -> CallToolResult:
    """Paste through CLIPBOARD when semantic typing is unavailable. Chooses common app shortcut from window class, with optional override. Destination is unverified; inspect dialogs/read back. Terminals can execute pasted newlines."""
    return await execute_async('paste',window_id,text,shortcut)


@mcp.tool()
async def desktop_press_keys(window_id: str, chord: str) -> CallToolResult:
    """Send one deliberate chord, e.g. ctrl+s, ctrl+shift+v, Return, Tab, Escape. Requires target focus, refuses held keys/buttons, and uses the current keyboard group without changing its mapping. Unavailable symbols return UNSUPPORTED_KEYMAP; never use this to type text."""
    return await execute_async('key',window_id,chord)


@mcp.tool()
async def desktop_click(window_id: str, snapshot_id: str, x: float, y: float, button: Literal['left','middle','right']='left', count: Literal[1,2,3]=1) -> CallToolResult:
    """Click screenshot-image coordinates in the active window or its observed menus. Rejects stale or covered targets."""
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
async def desktop_invoke(element_id: str, action: str) -> CallToolResult:
    """Invoke an exact action name returned by inspect. Completion means dispatch, not verified application outcome."""
    return await execute_async('element',element_id,'invoke',action=action)


@mcp.tool()
async def desktop_select(element_id: str, start_offset: int, end_offset: int) -> CallToolResult:
    """Select a text range using Unicode code-point offsets, or place caret when equal; verify the result."""
    return await execute_async('element',element_id,'select',start_offset=start_offset,end_offset=end_offset)


@mcp.tool()
async def desktop_set_value(element_id: str, value: float) -> CallToolResult:
    """Set a numeric control to a value within its inspected range and verify the actual value."""
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
    control = sub.add_parser('control',help='Coordinate human/agent input on this display')
    control.add_argument('action',choices=['status','pause','resume'])
    args = parser.parse_args()
    if args.command=='doctor':
        result = execute('doctor')
        print(result.content[0].text)
        raise SystemExit(1 if result.isError or not json.loads(result.content[0].text).get('ready') else 0)
    if args.command=='control':
        result = asyncio.run(desktop_control(args.action))
        print(result.content[0].text)
        raise SystemExit(1 if result.isError else 0)
    mcp.run(transport='stdio')


if __name__=='__main__':
    main()
