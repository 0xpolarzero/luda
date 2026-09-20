"""Separate optional MCP service. Core Luda never imports or discovers this module."""
import argparse
import asyncio
import atexit
from importlib.metadata import version
import json
from typing import Literal
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from luda.protocol import DesktopMCP
from luda import server as runtime
from .desktop import EditorDesktop
from .progress import operation_progress

mcp = DesktopMCP('luda-editor-bridge', product_version=version('luda-editor-bridge'), instructions='Optional ProseMirror editor tools. The website developer must register its editor with the application bridge. Open a temporary browser, inspect supported text_fields, read before editing, and verify afterward. Input verification does not confirm saving. Browser/profile disappear on disconnect; use editor_close only after saving.')

async def execute_async(method, *args, **kwargs):
    return await runtime.execute_async(method, *args, _progress_parser=operation_progress, **kwargs)

@mcp.tool()
async def editor_open(url: str, lifetime: Literal['temporary_session']) -> CallToolResult:
    """Open an isolated temporary Chromium for an application that installed the ProseMirror bridge. Requires configured LUDA_CHROMIUM_EXECUTABLE and X11. No existing profile/browser attachment. Browser/profile and unsaved content are deleted on disconnect or editor_close. Returns the only window accepted by this add-on."""
    return await execute_async('open_browser', url, lifetime)

@mcp.tool()
async def editor_close() -> CallToolResult:
    """Close this temporary browser and delete its profile. Save first: unsaved content is lost. Core Luda's separate browser is unaffected."""
    return await execute_async('close_browser')

@mcp.tool()
async def editor_type(element_id: str, text: str, mode: Literal['insert','replace']='insert', line_breaks: Literal['paragraph','hard_break'] | None=None, transport: Literal['native','clipboard']='native') -> CallToolResult:
    """Edit a registered ProseMirror document and verify exact text/structure/unaffected marks. Insert replaces selection; replace replaces the whole document. Native supports whole replacement/end append. Explicit clipboard supports interior ranges and leaves the last nonempty segment in CLIPBOARD. LF requires paragraph or an app-declared hard_break policy. New formatting follows app behavior. Partial failure is not rolled back; inspect before retrying. Verification does not confirm saving."""
    return await execute_async('type_text',element_id,text,mode,line_breaks=line_breaks,transport=transport)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def editor_doctor() -> CallToolResult:
    """Check Linux/X11 and browser prerequisites. Connection to an app bridge is checked by editor_inspect after editor_open."""
    result = await execute_async('doctor')
    if not result.isError:
        value = json.loads(result.content[0].text)
        value['ready'] = value.get('ready') is True and value.get('owned_browser',{}).get('available') is True
        value['editor_bridge'] = {'version':version('luda-editor-bridge'),'application_bridge_required':True,'automatic_injection':False,'browser_lifetime':'temporary_session','connection_check':'editor_open then editor_inspect'}
        result.content[0].text = json.dumps(value,separators=(',',':'))
    return result

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def editor_status() -> CallToolResult:
    """Read this add-on process's recent operation outcomes after interruption; excludes typed contents. Counts never authorize replay."""
    return await runtime.desktop_status()

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def editor_report() -> CallToolResult:
    """Return this add-on's sanitized diagnostic report without document content or typed text."""
    from luda.reporting import build_report
    with runtime._history_lock:
        history = list(runtime._history)
    probe = await editor_doctor()
    health = json.loads(probe.content[0].text) if not probe.isError else {}
    report = build_report(health,history,recovering=runtime._quarantined.is_set(),progress_parser=operation_progress)
    report['product'] = 'luda-editor-bridge'
    return CallToolResult(content=[TextContent(type='text',text=json.dumps(report,separators=(',',':')))])

@mcp.tool()
async def editor_activate(window_id: str) -> CallToolResult:
    """Activate the owned browser window returned by editor_open and verify focus. Observe again afterward."""
    return await execute_async('activate',window_id)

@mcp.tool()
async def editor_observe(max_width: int = 1280) -> CallToolResult:
    """Return screenshot plus window layout and a 15-second snapshot ID. Pointer coordinates and window/popup image_bounds use returned-image pixels; bounds/frame_bounds remain native X11 root pixels. image_bounds is null when no integer screenshot pixel maps into the client. Use integer image points."""
    return await execute_async('observe',max_width)

@mcp.tool()
async def editor_inspect(window_id: str, limit: int = 150, name: str | None = None, role: str | None = None, states: list[str] | None = None, max_depth: int = 30) -> CallToolResult:
    """Inspect the owned browser's native toolbar controls and registered ProseMirror text_fields. Only supported text_fields accept editor_type. An empty list means no matching registered editor; the application developer must install/register the bridge. Filters can hide connected editors; retry without filters to diagnose readiness."""
    return await execute_async('inspect',window_id,limit,name,role,states,max_depth=max_depth)

@mcp.tool()
async def editor_read(element_id: str, limit: int = 16000) -> CallToolResult:
    """Read accessible text and representation metadata, preserving whitespace. limit counts Unicode code points (default 16000, maximum 1000000), not bytes. Opaque embedded objects are not exact logical plain text: check plain_text_verification_supported. Normalization reads the bounded full field; a smaller limit does not enable streaming. Protected fields are refused. Generic native readback reports composition known=false, active=null; pending preedit is not checked."""
    if not 1<=limit<=1_000_000:
        return runtime.result_error('INVALID_ARGUMENT', 'limit must be 1–1000000')
    return await execute_async('element',element_id,'read',limit=limit)

@mcp.tool()
async def editor_press_keys(window_id: str, chord: str, count: int = 1) -> CallToolResult:
    """Send a deliberate chord, e.g. ctrl+s, ctrl+plus, ctrl+minus, Return, Tab, Escape or Down. Punctuation uses X11 names (plus, equal, bracketleft, slash); implicit Shift follows the current layout. count is 1–20 complete press/release repetitions, default 1. Revalidates target identity, focus and input state between repetitions; stops on the first failure and never retries. Requires target focus, refuses held keys/buttons, and preserves the current keyboard mapping. Unavailable symbols return UNSUPPORTED_KEYMAP; text belongs in editor_type. When a final companion receipt is available, progress reports fully dispatched, possibly partial and not-started repetitions. Dispatched count is not application completion."""
    return await execute_async('key',window_id,chord,count)

@mcp.tool()
async def editor_scroll(window_id: str, snapshot_id: str, x: float, y: float, direction: Literal['up','down','left','right'], ticks: int=3) -> CallToolResult:
    """Scroll 1–20 wheel ticks at a point in the observed active target. Read resulting state to confirm."""
    return await execute_async('pointer',window_id,snapshot_id,x,y,kind='scroll',direction=direction,count=ticks)

@mcp.tool()
async def editor_focus(element_id: str) -> CallToolResult:
    """Request element focus in the active window; owned browser fields refuse active/unknown composition before focus. Inspect to confirm focused state."""
    return await execute_async('element',element_id,'focus')

@mcp.tool()
async def editor_invoke(element_id: str, action: str | None = None) -> CallToolResult:
    """Invoke the sole action returned by inspect, or supply its exact action name. Multiple actions require an explicit choice; no click/press naming guess is needed for a single-action button. Completion means dispatch, not verified application outcome."""
    return await execute_async('element',element_id,'invoke',action=action)

@mcp.tool()
async def editor_select(element_id: str, start_offset: int, end_offset: int) -> CallToolResult:
    """Select Unicode code-point offsets in a registered editor, or place its caret when equal. Focus first. Native typing supports full replacement/end append; use explicit clipboard transport to edit interior ranges. Selection is verified against the unchanged model."""
    return await execute_async('element',element_id,'select',start_offset=start_offset,end_offset=end_offset)

def main():
    parser = argparse.ArgumentParser(description='Optional Luda Editor Bridge MCP server for cooperating ProseMirror applications')
    parser.add_argument('--version',action='version',version=version('luda-editor-bridge'))
    parser.add_argument('command',nargs='?',choices=['doctor'])
    args=parser.parse_args()
    runtime.backend=EditorDesktop()
    atexit.register(runtime.backend.close)
    if args.command=='doctor':
        result=asyncio.run(editor_doctor())
        print(result.content[0].text)
        raise SystemExit(1 if result.isError or not json.loads(result.content[0].text).get('ready') else 0)
    mcp.run(transport='stdio')

if __name__ == '__main__':
    main()
