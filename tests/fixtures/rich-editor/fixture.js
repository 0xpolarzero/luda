import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { schema } from 'prosemirror-schema-basic';
import { keymap } from 'prosemirror-keymap';
import { baseKeymap, toggleMark } from 'prosemirror-commands';

const params = new URLSearchParams(location.search);
const mode = params.get('mode') || 'prosemirror';
const documentId = crypto.randomUUID();
const events = [];
let generation = 0, revision = 0, view = null, root;
let persistTail = Promise.resolve();
let spoofNextComposition = false;
const allowed = new Set(['doc', 'paragraph', 'text', 'hard_break']);

function snapshot() {
  const model = view?.state.doc;
  const unsupported = [];
  model?.descendants(node => { if (!allowed.has(node.type.name)) unsupported.push(node.type.name); });
  const selection = getSelection();
  return {
    mode, documentId, generation, revision,
    editorComposing: view?.composing ?? null,
    fieldValue: root instanceof HTMLTextAreaElement ? root.value : null,
    model: model?.toJSON() ?? null,
    modelText: model?.textBetween(0, model.content.size, '\n', node => node.type.name === 'hard_break' ? '\n' : '\uFFFC') ?? null,
    unsupported,
    renderedText: root.innerText,
    textContent: root.textContent,
    html: root.innerHTML,
    active: document.activeElement === root,
    selection: selection ? {text: selection.toString(), anchorOffset: selection.anchorOffset, focusOffset: selection.focusOffset} : null,
    events: events.slice(-30),
  };
}
function persist() {
  const actual = snapshot();
  persistTail = persistTail.then(() => fetch('/oracle', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(actual)
  })).catch(() => {});
}
function mount() {
  view?.destroy();
  document.querySelector('#host').replaceChildren();
  generation++;
  if (mode === 'prosemirror') {
    view = new EditorView(document.querySelector('#host'), {
      state: EditorState.create({schema, plugins: [keymap({
        'Mod-b': toggleMark(schema.marks.strong), 'Mod-i': toggleMark(schema.marks.em),
      }), keymap(baseKeymap)]}),
      attributes: {'aria-label': 'Observed rich editor', role: 'textbox', class: 'editor'},
      dispatchTransaction(transaction) {
        view.updateState(view.state.apply(transaction));
        if (transaction.docChanged) revision++;
        persist();
      },
    });
    root = view.dom;
  } else {
    view = null;
    root = document.createElement(mode === 'textarea' ? 'textarea' : 'div');
    if (mode !== 'textarea') root.contentEditable = 'true';root.className = 'editor';root.id = 'generic-editor';
    root.setAttribute('role', 'textbox');root.setAttribute('aria-label', 'Observed rich editor');
    if (mode === 'generic-prewrap') root.style.whiteSpace = 'pre-wrap';
    document.querySelector('#host').append(root);
    root.addEventListener('input', () => {revision++;persist();});
  }
  root.id = 'editor';
  root.addEventListener('compositionstart', event => {
    if (event.isTrusted && spoofNextComposition) {
      spoofNextComposition = false;
      setTimeout(() => { root.dispatchEvent(new CompositionEvent('compositionend', {data: '', bubbles: true})); persist(); }, 1500);
    }
  });
  for (const type of ['beforeinput', 'input', 'paste', 'compositionstart', 'compositionend']) {
    root.addEventListener(type, event => {
      events.push({type, inputType: event.inputType ?? null, isComposing: event.isComposing ?? null, trusted: event.isTrusted});
      queueMicrotask(persist);
    });
  }
  document.querySelector('#mode').textContent = mode;
  persist();
}
mount();
document.querySelector('#replace').onclick = mount;
document.querySelector('#spoof').onclick = () => { spoofNextComposition = true; };
document.querySelector('#reload').onclick = () => location.reload();
document.querySelector('#composition').onclick = () => {
  root.focus();root.dispatchEvent(new CompositionEvent('compositionstart', {data: '', bubbles: true}));persist();
};
document.querySelector('#image').onclick = () => {
  if (view) {view.dispatch(view.state.tr.replaceSelectionWith(schema.nodes.image.create({src: 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==', alt: 'fixture embedded object'})));view.focus();}
};
// Cooperating read-only fixture API; no setters, requested payload or driver args.
Object.defineProperty(window, 'ludaRichProbe', {value: Object.freeze({snapshot}), configurable: false});
