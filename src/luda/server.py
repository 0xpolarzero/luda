import asyncio
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
        with operation_scope(timeout=12, cancelled=_cancelled) as operation:
            try:
                d = get_backend()
                with d.transaction():
                    result = getattr(d,method)(*args,**kwargs)
            except DesktopError as exc:
                if operation.effect != 'none' and exc.effect == 'none':
                    exc.effect = 'uncertain'
                    exc.details['prior_effects_possible'] = True
                raise
        if not isinstance(result,dict):
            result={'windows':result}
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
async def desktop_inspect(window_id: str, limit: int = 150) -> CallToolResult:
    """Return a bounded accessibility tree with opaque 60-second element IDs, roles, states and actions."""
    return await execute_async('inspect',window_id,limit)


@mcp.tool()
async def desktop_read_text(element_id: str, limit: int = 16000) -> CallToolResult:
    """Read exact accessible text, preserving whitespace. Protected fields are unsupported. Maximum 1 MB."""
    if not 1<=limit<=1_000_000:
        return result_error('INVALID_ARGUMENT', 'limit must be 1–1000000')
    return await execute_async('element',element_id,'read',limit=limit)


@mcp.tool()
async def desktop_set_text(element_id: str, text: str) -> CallToolResult:
    """Replace all text through accessibility and compare exact readback. Preserves LF, Tab and Unicode; rejects other control characters. Does not submit."""
    return await execute_async('element',element_id,'set',text=text)


@mcp.tool()
async def desktop_enter_text(window_id: str, text: str, shortcut: Literal['ctrl_v','ctrl_shift_v','shift_insert']) -> CallToolResult:
    """Paste literal text at the current caret using the application's explicit shortcut. Replaces CLIPBOARD; target contents are NOT verified. Terminals may execute newlines. Observe dialogs/read back before proceeding."""
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


def main():
    mcp.run(transport='stdio')


if __name__=='__main__':
    main()
