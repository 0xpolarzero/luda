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
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

from .common import DesktopError, operation_scope
from .desktop import Desktop

mcp = FastMCP('luda', instructions='Local desktop: observe, select a window, inspect its controls, then act. Screenshot coordinates use the returned image, with its snapshot ID. Text replacement and insertion are distinct. Verify dispatched actions before repeating them; cancellation or timeout can leave effects. Use desktop_status to inspect recent operation outcomes.')
backend = None
_backend_lock = threading.Lock()
_history_lock = threading.Lock()
_history = deque(maxlen=32)
_quarantined = threading.Event()


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
    started = time.monotonic()
    operation_id = uuid.uuid4().hex
    event = {'operation_id':operation_id, 'method':method}
    try:
        if _quarantined.is_set():
            raise DesktopError('BUSY', 'Previous cancelled operation is still cleaning up; no new input sent.')
        d = get_backend()
        observation = method in ('doctor','list_windows','observe','inspect','workspaces','wait_for') or (method=='element' and len(args)>1 and args[1]=='read')
        guard = None if observation else d.control.require_active
        with operation_scope(timeout=12, cancelled=_cancelled, guard=guard) as operation:
            try:
                with d.transaction():
                    result = getattr(d,method)(*args,**kwargs)
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
        _quarantined.set()
        with anyio.CancelScope(shield=True):
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.add_done_callback(lambda _: _quarantined.clear())
            else:
                _quarantined.clear()
        raise


@mcp.tool()
async def desktop_control(action: Literal['status','pause','resume']='status') -> CallToolResult:
    """Pause/resume cooperating agent input across servers on this display. Pause interrupts at the next checkpoint; already-delivered input is not undone. Observation remains available. This does not stop arbitrary external input programs."""
    try:
        control = get_backend().control
        state = control.status() if action=='status' else control.set_paused(action=='pause')
        return CallToolResult(content=[TextContent(type='text',text=json.dumps({'ok':True,**state}))])
    except DesktopError as exc:
        return result_error(exc.code,str(exc),exc.effect)


@mcp.tool()
async def desktop_status() -> CallToolResult:
    """Return recent operation outcomes after timeout/cancellation. No input text or screenshots are retained."""
    with _history_lock:
        history = list(_history)
    return CallToolResult(content=[TextContent(type='text',text=json.dumps({'ok':True,'recovering':_quarantined.is_set(),'operations':history}))])


@mcp.tool()
async def desktop_doctor() -> CallToolResult:
    """Check actual display access, desktop session, dependencies and accessibility availability."""
    return await execute_async('doctor')


@mcp.tool()
async def desktop_windows() -> CallToolResult:
    """List window identities, titles, process identity, focus and native client bounds."""
    return await execute_async('list_windows')


@mcp.tool()
async def desktop_activate(window_id: str) -> CallToolResult:
    """Activate a window from desktop_windows and verify focus. Observe again afterward."""
    return await execute_async('activate',window_id)


@mcp.tool()
async def desktop_observe(max_width: int = 1280) -> CallToolResult:
    """Return screenshot plus window layout and a 15-second snapshot ID. Coordinates are image pixels."""
    return await execute_async('observe',max_width)


@mcp.tool()
async def desktop_inspect(window_id: str, limit: int = 150, name: str | None = None, role: str | None = None, states: list[str] | None = None, max_depth: int = 30) -> CallToolResult:
    """Inspect a window or find controls by name/role substring and required states. Returns bounded tree, parent IDs, supported actions and 60-second element IDs. Empty matches and unavailable accessibility are distinct."""
    return await execute_async('inspect',window_id,limit,name=name,role=role,states=states,max_depth=max_depth)


@mcp.tool()
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
async def desktop_paste(window_id: str, text: str, shortcut: Literal['ctrl_v','ctrl_shift_v','shift_insert'] | None = None) -> CallToolResult:
    """Paste through CLIPBOARD when semantic typing is unavailable. Chooses common app shortcut from window class, with optional override. Destination is unverified; inspect dialogs/read back. Terminals can execute pasted newlines."""
    return await execute_async('paste',window_id,text,shortcut)


@mcp.tool()
async def desktop_press_keys(window_id: str, chord: str) -> CallToolResult:
    """Send one deliberate chord, e.g. ctrl+s, ctrl+shift+v, Return, Tab, Escape. Requires target focus; never use this to type text."""
    return await execute_async('key',window_id,chord)


@mcp.tool()
async def desktop_click(window_id: str, snapshot_id: str, x: float, y: float, button: Literal['left','middle','right']='left', count: Literal[1,2,3]=1) -> CallToolResult:
    """Click screenshot-image coordinates inside the active target client. Rejects expired or changed layouts."""
    return await execute_async('pointer',window_id,snapshot_id,x,y,button=button,count=count)


@mcp.tool()
async def desktop_scroll(window_id: str, snapshot_id: str, x: float, y: float, direction: Literal['up','down','left','right'], ticks: int=3) -> CallToolResult:
    """Scroll 1–20 wheel ticks at a point in the observed active target. Read resulting state to confirm."""
    return await execute_async('pointer',window_id,snapshot_id,x,y,kind='scroll',direction=direction,count=ticks)


@mcp.tool()
async def desktop_drag(window_id: str, snapshot_id: str, x: float, y: float, end_x: float, end_y: float, button: Literal['left','middle','right']='left') -> CallToolResult:
    """Drag between two observed points inside the same active window; always attempts button release. Cross-window drags are not supported yet."""
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
async def desktop_window(window_id: str, action: Literal['move','resize','maximize','minimize','restore','close','workspace'], x: int | None = None, y: int | None = None, width: int | None = None, height: int | None = None, workspace: int | None = None) -> CallToolResult:
    """Manage one window. move uses frame x/y; resize uses client width/height; workspace requires its index. Other actions take no extra parameters. A close can open a save dialog."""
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


@mcp.tool()
async def desktop_wait(condition: Literal['window_present','window_absent','window_active','text_equals','text_contains'], window_id: str | None = None, element_id: str | None = None, text: str | None = None, timeout: float = 5) -> CallToolResult:
    """Wait up to 10 seconds for an observable condition without repeating input. Window conditions use window_id; text conditions use element_id and text. A timeout returns matched=false."""
    return await execute_async('wait_for',condition,window_id=window_id,element_id=element_id,text=text,timeout=timeout)


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
