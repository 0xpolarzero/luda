"""Editor-only backend; native toolbar actions stay in the owned browser window."""
from luda.desktop import Desktop
from luda.common import DesktopError, validate_text
from luda.timing import elapsed_time
from .browser import OwnedBrowser

class EditorDesktop(Desktop):
    browser_class = OwnedBrowser

    def target_window(self, window_id, require_focus=True):
        if window_id != self.browser.window_id or self.browser.window_id is None:
            raise DesktopError('BROWSER_SCOPE_UNSUPPORTED', 'Use the window returned by editor_open in this add-on session.')
        return super().target_window(window_id, require_focus)

    def inspect(self, window_id, limit=150, name=None, role=None, states=None, max_depth=30):
        result = super().inspect(window_id,limit,name,role,states,max_depth)
        fields = result.get('text_fields', [])
        unsupported = result.get('owned_browser',{}).get('code') == 'BROWSER_SCOPE_UNSUPPORTED'
        result['editor_bridge'] = {
            'status':'unsupported_page_scope' if unsupported else 'connected' if fields else 'no_matching_editor',
            'supported_editors':sum(field.get('supported') is True for field in fields),
            'next_step': 'Return to one top-level page without frames; the owned editor provider does not support this page scope.' if unsupported else 'Use a supported text_fields element_id.' if fields else 'Remove filters to check all editors. If still empty, the application developer must register its ProseMirror EditorView with the bridge.'}
        return result

    def type_text(self, element_id, text, mode='insert', line_breaks=None, transport='native'):
        validate_text(text)
        if mode not in ('insert','replace') or transport not in ('native','clipboard') or line_breaks not in (None,'paragraph','hard_break'):
            raise DesktopError('INVALID_ARGUMENT', 'Choose a supported mode, line-break policy and transport.')
        target = self.elements.get(element_id)
        if not target or elapsed_time()-target['time']>=60:
            raise DesktopError('STALE_TARGET', 'Editor expired; inspect again.')
        if target.get('provider') != 'owned_browser':
            raise DesktopError('UNSUPPORTED_FIELD', 'Use an editor from editor_inspect text_fields; native toolbar nodes are not editor documents.')
        return self.browser.element(target, 'type', text=text, mode=mode, line_breaks=line_breaks, transport=transport)

    def close_browser(self):
        self.browser.close()
        self.elements.clear()
        self.snapshots.clear()
        return {'effect':'verified','closed':True,'retention':'Temporary browser/profile removed; unsaved content is lost.'}
