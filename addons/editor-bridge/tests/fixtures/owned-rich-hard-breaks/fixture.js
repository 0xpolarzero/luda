import {registerProseMirror} from '/bridge.mjs';
import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { schema } from 'prosemirror-schema-basic';
import { keymap } from 'prosemirror-keymap';
import { baseKeymap, toggleMark } from 'prosemirror-commands';

const params = new URLSearchParams(location.search);
const mode = 'prosemirror';
let legacy=false,wrong=false;
const contract=()=>legacy?{paragraphs:'enter'}:{paragraphs:'enter',hard_breaks:'shift-enter'};
const documentId = crypto.randomUUID();
const events = [];
let generation = 0, revision = 0, view = null, root, unregister;
let persistTail = Promise.resolve();
let spoofNextComposition = false, spoofNextKey = false, blurNext = false;
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
    model: model?.toJSON() ?? null, modelSelection:view.state.selection.toJSON(),modelCaretCodePoints:Array.from(model.textBetween(0,view.state.selection.head,'\n',node=>node.type.name==='hard_break'?'\n':'\uFFFC')).length,
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
  unregister?.();
  view?.destroy();
  document.querySelector('#host').replaceChildren();
  generation++;
  if (mode === 'prosemirror') {
    view = new EditorView(document.querySelector('#host'), {
      state: EditorState.create({schema, plugins: [keymap({
        'Shift-Enter': (state,dispatch,v)=>{if(wrong)return baseKeymap.Enter(state,dispatch,v);if(dispatch)dispatch(state.tr.replaceSelectionWith(schema.nodes.hard_break.create()).scrollIntoView());return true;},
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
    unregister = registerProseMirror(view,contract());
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
  root.addEventListener('input',e=>{if(e.isTrusted&&blurNext){blurNext=false;document.querySelector('#blur').focus();queueMicrotask(persist);}});
  root.addEventListener('compositionstart', event => {
    if (event.isTrusted && spoofNextKey) {
      spoofNextKey = false;
      setTimeout(() => {
        root.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', code:'Escape', isComposing:true, bubbles:true}));
        root.dispatchEvent(new KeyboardEvent('keyup', {key:'Escape', code:'Escape', isComposing:false, bubbles:true}));
        persist();
      }, 1000);
    }
    if (event.isTrusted && spoofNextComposition) {
      spoofNextComposition = false;
      setTimeout(() => { root.dispatchEvent(new CompositionEvent('compositionend', {data: '', bubbles: true})); persist(); }, 1500);
    }
  });
  for (const type of ['beforeinput', 'input', 'paste', 'keydown', 'compositionstart', 'compositionend']) {
    root.addEventListener(type, event => {
      events.push({type, key:event.key??null, shift:event.shiftKey??false, inputType: event.inputType ?? null, isComposing: event.isComposing ?? null, trusted: event.isTrusted});
      queueMicrotask(persist);
    });
  }
  document.querySelector('#mode').textContent = mode;
  persist();
}
mount();
document.querySelector('#replace').onclick = mount;
document.querySelector('#spoof-key').onclick = () => { spoofNextKey = true; };
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

document.querySelector('#blur').onclick=()=>{blurNext=true;};
document.querySelector('#reregister').onclick=()=>{unregister();unregister=registerProseMirror(view,contract());generation++;persist();};

document.querySelector('#pending-link').onclick=()=>{view.dispatch(view.state.tr.setStoredMarks([schema.marks.link.create({href:'https://example.invalid'})]));persist();};

document.querySelector('#paragraph-limit').onclick=()=>{view.updateState(EditorState.create({schema,doc:schema.node('doc',null,Array.from({length:128},()=>schema.node('paragraph'))),plugins:[keymap(baseKeymap)]}));revision++;persist();};

function mixed(){return schema.node('doc',null,[schema.node('paragraph',null,[schema.text('A😀',[schema.marks.strong.create()]),schema.nodes.hard_break.create(null,null,[schema.marks.strong.create()]),schema.text('éZ',[schema.marks.em.create()])]),schema.node('paragraph',null,[schema.text('TAIL',[schema.marks.strong.create()])])]);}
function seed(){view.dispatch(view.state.tr.replaceWith(0,view.state.doc.content.size,mixed().content));persist();}
for(const [label,action] of [
 ['Fresh hard-break editor',()=>{legacy=false;wrong=false;mount();}],
 ['Mixed marked document',()=>{legacy=false;wrong=false;mount();seed();}],
 ['Legacy editor',()=>{legacy=true;wrong=false;mount();}],
 ['Legacy mixed document',()=>{legacy=true;wrong=false;mount();seed();}],
 ['Wrong break binding',()=>{legacy=false;wrong=true;mount();}]]){const b=document.createElement('button');b.textContent=label;b.onclick=action;document.querySelector('#host').before(b);}
