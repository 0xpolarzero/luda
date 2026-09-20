import {EditorState} from 'prosemirror-state';
import {EditorView} from 'prosemirror-view';
import {schema} from 'prosemirror-schema-basic';
import {keymap} from 'prosemirror-keymap';
import {baseKeymap} from 'prosemirror-commands';
import {registerProseMirror} from '/bridge.mjs';

// Initial fixture data only. All subsequent task edits come through native UI.
const doc = schema.node('doc', null, [schema.node('paragraph', null,
  [schema.text('Bold prefix: ', [schema.marks.strong.create()])])]);
const view = new EditorView(document.querySelector('#host'), {
  state: EditorState.create({schema, doc, plugins: [keymap(baseKeymap)]}),
  attributes: {'aria-label': 'Synthetic paragraph document', role: 'textbox'},
});
const unregister = registerProseMirror(view, {paragraphs: 'enter'});
window.addEventListener('pagehide', () => unregister());
document.querySelector('#save').onclick = async () => {
  // App save handler reads the real application model and DOM, never the bridge.
  const payload = {model: view.state.doc.toJSON(), html: view.dom.innerHTML,
    paragraphs: [...view.dom.querySelectorAll('p')].map(p => p.textContent),
    strong: [...view.dom.querySelectorAll('strong')].map(p => p.textContent)};
  const response = await fetch('/save', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  if (response.ok) document.title = 'Synthetic document saved';
};
