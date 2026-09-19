import atexit
import json
import time
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

from .common import DesktopError
from .desktop import Desktop

mcp = FastMCP('luda', instructions='Local X11 desktop. Start with desktop_doctor and desktop_observe. Activate an explicit window before input. Pointer actions require the latest screenshot ID and image-pixel coordinates. Use set_text for verified full replacement; enter_text pastes at the caret but requires verification. Never automatically retry an uncertain mutation.')
backend = None


def get_backend():
    global backend
    if backend is None:
        backend = Desktop()
        atexit.register(backend.close)
    return backend


def execute(method, *args, **kwargs):
    started = time.monotonic()
    try:
        d = get_backend()
        with d.transaction():
            result = getattr(d,method)(*args,**kwargs)
        if not isinstance(result,dict):
            result={'windows':result}
        image = result.pop('image_base64',None)
        result={'ok':True,'elapsed_ms':round((time.monotonic()-started)*1000),**result}
        content=[TextContent(type='text',text=json.dumps(result,ensure_ascii=False))]
        if image:
            content.append(ImageContent(type='image',data=image,mimeType='image/png'))
        return CallToolResult(content=content,isError=False)
    except DesktopError as exc:
        return CallToolResult(isError=True,content=[TextContent(type='text',text=json.dumps({'ok':False,'code':exc.code,'message':str(exc),'effect':exc.effect,'details':exc.details,'elapsed_ms':round((time.monotonic()-started)*1000)},ensure_ascii=False))])
    except Exception as exc:
        # Unknown errors must never imply that a mutation did not happen.
        return CallToolResult(isError=True,content=[TextContent(type='text',text=json.dumps({'ok':False,'code':'INTERNAL_ERROR','message':str(exc)[:400],'effect':'uncertain'}))])


@mcp.tool()
def desktop_doctor() -> CallToolResult:
    """Check actual display access, desktop session, dependencies and accessibility availability."""
    return execute('doctor')


@mcp.tool()
def desktop_windows() -> CallToolResult:
    """List window identities, titles, process identity, focus and native client bounds."""
    return execute('list_windows')


@mcp.tool()
def desktop_activate(window_id: str) -> CallToolResult:
    """Activate a window from desktop_windows and verify focus. Observe again afterward."""
    return execute('activate',window_id)


@mcp.tool()
def desktop_observe(max_width: int = 1280) -> CallToolResult:
    """Return screenshot plus window layout and a 15-second snapshot ID. Coordinates are image pixels."""
    return execute('observe',max_width)


@mcp.tool()
def desktop_inspect(window_id: str, limit: int = 150) -> CallToolResult:
    """Return a bounded accessibility tree with opaque 60-second element IDs, roles, states and actions."""
    return execute('inspect',window_id,limit)


@mcp.tool()
def desktop_read_text(element_id: str, limit: int = 16000) -> CallToolResult:
    """Read exact accessible text, preserving whitespace. Protected fields are unsupported. Maximum 1 MB."""
    if not 1<=limit<=1_000_000:
        return CallToolResult(isError=True,content=[TextContent(type='text',text='limit must be 1–1000000')])
    return execute('element',element_id,'read',limit=limit)


@mcp.tool()
def desktop_set_text(element_id: str, text: str) -> CallToolResult:
    """Replace all text through accessibility and compare exact readback. Preserves LF, Tab and Unicode; rejects other control characters. Does not submit."""
    return execute('element',element_id,'set',text=text)


@mcp.tool()
def desktop_enter_text(window_id: str, text: str, shortcut: Literal['ctrl_v','ctrl_shift_v','shift_insert']) -> CallToolResult:
    """Paste literal text at the current caret using the application's explicit shortcut. Replaces CLIPBOARD; target contents are NOT verified. Terminals may execute newlines. Observe dialogs/read back before proceeding."""
    return execute('paste',window_id,text,shortcut)


@mcp.tool()
def desktop_press_keys(window_id: str, chord: str) -> CallToolResult:
    """Send one deliberate chord, e.g. ctrl+s, ctrl+shift+v, Return, Tab, Escape. Requires target focus; never use this to type text."""
    return execute('key',window_id,chord)


@mcp.tool()
def desktop_click(window_id: str, snapshot_id: str, x: float, y: float, button: Literal['left','middle','right']='left', count: Literal[1,2,3]=1) -> CallToolResult:
    """Click screenshot-image coordinates inside the active target client. Rejects expired or changed layouts."""
    return execute('pointer',window_id,snapshot_id,x,y,button=button,count=count)


@mcp.tool()
def desktop_scroll(window_id: str, snapshot_id: str, x: float, y: float, direction: Literal['up','down','left','right'], ticks: int=3) -> CallToolResult:
    """Scroll 1–20 wheel ticks at a point in the observed active target. Read resulting state to confirm."""
    return execute('pointer',window_id,snapshot_id,x,y,kind='scroll',direction=direction,count=ticks)


@mcp.tool()
def desktop_drag(window_id: str, snapshot_id: str, x: float, y: float, end_x: float, end_y: float, button: Literal['left','middle','right']='left') -> CallToolResult:
    """Drag between two observed points inside the same active window; always attempts button release. Cross-window drags are not supported yet."""
    return execute('pointer',window_id,snapshot_id,x,y,kind='drag',button=button,end_x=end_x,end_y=end_y)


@mcp.tool()
def desktop_focus_element(element_id: str) -> CallToolResult:
    """Request accessibility focus in the active window. Inspect to confirm focused state."""
    return execute('element',element_id,'focus')


@mcp.tool()
def desktop_invoke(element_id: str, action: str) -> CallToolResult:
    """Invoke an exact action name returned by inspect. Completion means dispatch, not verified application outcome."""
    return execute('element',element_id,'invoke',action=action)


def main():
    mcp.run(transport='stdio')


if __name__=='__main__':
    main()
