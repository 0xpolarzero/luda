"""Test-only readback prototype for an explicitly owned cooperating browser fixture.
No general selectors, mutation scripts, editor setters or production API.
"""
import hashlib
import json
from pathlib import Path

COMPOSITION_MONITOR = """(() => {
  let active = false;
  document.addEventListener('compositionstart', () => { active = true; }, true);
  document.addEventListener('compositionend', () => { active = false; }, true);
  Object.defineProperty(window, '__ludaRichComposition', {
    get: () => ({known: true, active}), configurable: false
  });
})()"""


class Refused(Exception):
    pass


def process_start(pid):
    return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]


def content_identity(snapshot):
    value = {key: snapshot[key] for key in ('documentId', 'generation', 'model', 'html')}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Readback:
    def __init__(self, page, desktop, browser_pid, window_id, monitored_before_document):
        self.page = page
        self.desktop = desktop
        self.browser_pid = browser_pid
        self.pid_start = process_start(browser_pid)
        self.window_id = window_id
        self.monitored = monitored_before_document
        self.document = page.evaluate_handle('document')
        self.node = page.query_selector('#editor')
        if self.node is None:
            raise Refused('NODE_MISSING')
        self.initial = self.read(require_focus=False)
        self.content = content_identity(self.initial)

    def read(self, require_focus=True):
        if self.page.is_closed() or len(self.page.context.pages) != 1:
            raise Refused('PAGE_IDENTITY_CHANGED')
        if process_start(self.browser_pid) != self.pid_start:
            raise Refused('BROWSER_IDENTITY_CHANGED')
        windows = [w for w in self.desktop.list_windows() if w['pid'] == self.browser_pid]
        if len(windows) != 1 or windows[0]['window_id'] != self.window_id:
            raise Refused('NATIVE_WINDOW_AMBIGUOUS_OR_CHANGED')
        try:
            current = self.page.evaluate('(doc) => document === doc', self.document)
        except Exception:
            current = False
        if not current:
            raise Refused('DOCUMENT_CHANGED')
        value = self.node.evaluate("""node => ({
          connected: node.isConnected, editable: node.isContentEditable || (node.tagName === 'TEXTAREA' && !node.readOnly),
          visible: node.getClientRects().length > 0 && document.visibilityState === 'visible',
          focused: document.hasFocus() && document.activeElement === node,
          snapshot: window.ludaRichProbe.snapshot(),
          composition: window.__ludaRichComposition ?? {known:false, active:null}
        })""")
        if not value['connected']:
            raise Refused('NODE_REPLACED')
        if not value['editable'] or not value['visible']:
            raise Refused('NODE_NOT_EDITABLE_OR_VISIBLE')
        if require_focus and not value['focused']:
            raise Refused('FOCUS_CHANGED')
        if not self.monitored or not value['composition']['known']:
            raise Refused('COMPOSITION_UNKNOWN')
        if value['composition']['active']:
            raise Refused('COMPOSITION_PENDING')
        snapshot = value['snapshot']
        if snapshot['unsupported']:
            raise Refused('MODEL_EMBED_UNSUPPORTED')
        snapshot['representation'] = ('prosemirror-paragraph-lf-hardbreak-lf-v1' if snapshot['mode'] == 'prosemirror' else 'html-textarea-value' if snapshot['mode'] == 'textarea' else 'whatwg-rendered-innerText')
        snapshot['logicalText'] = (snapshot['modelText'] if snapshot['mode'] == 'prosemirror' else snapshot['fieldValue'] if snapshot['mode'] == 'textarea' else snapshot['renderedText'])
        return snapshot

    def before_input(self):
        actual = self.read()
        if content_identity(actual) != self.content:
            raise Refused('CONTENT_CHANGED')
        return actual

    def dispose(self):
        self.node.dispose()
        self.document.dispose()

# Separate candidate: the original synthetic baseline monitor above is retained.
NATIVE_COMPOSITION_MONITOR = """(() => {
  let active = false, trustedStarts = 0, trustedEnds = 0, ignored = 0;
  const events = [];
  for (const type of ['compositionstart', 'compositionupdate', 'compositionend', 'beforeinput', 'input', 'keydown', 'keyup']) {
    window.addEventListener(type, event => {
      events.push({type, trusted: event.isTrusted, inputType: event.inputType ?? null,
        isComposing: event.isComposing ?? null, data: event.data ?? null,
        key: event.key ?? null, target: event.target?.id ?? null});
      if (events.length > 160) events.shift();
    }, true);
  }
  document.addEventListener('compositionstart', event => {
    if (!event.isTrusted) { ignored++; return; }
    active = true; trustedStarts++;
  }, true);
  document.addEventListener('compositionend', event => {
    if (!event.isTrusted) { ignored++; return; }
    active = false; trustedEnds++;
  }, true);
  Object.defineProperty(window, '__ludaRichComposition', {
    get: () => ({known: true, active, trustedStarts, trustedEnds, ignored, events: events.slice()}),
    configurable: false
  });
})()"""
