import {registerProseMirror} from '/bridge.mjs';
import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { schema } from 'prosemirror-schema-basic';
import { keymap } from 'prosemirror-keymap';
import { baseKeymap, toggleMark } from 'prosemirror-commands';

const params = new URLSearchParams(location.search);
const mode = params.get('mode') || 'prosemirror';
const documentId = crypto.randomUUID();
const events = [];
let generation = 0, revision = 0, view = null, root, unregister;
let persistTail = Promise.resolve();
let spoofNextComposition = false, spoofNextKey = false, blurNext = false;
const SEEDS={plain:'A👩🏽‍💻B éC', paragraphs:'first\n\nlast', marks:'LEFT middle RIGHT', empty:'', boundaries:'AB\nCD\nEF'};
const allowed = new Set(['doc', 'paragraph', 'text', 'hard_break']);

function snapshot() {
  const model = view?.state.doc;
  const unsupported = [];
  model?.descendants(node => { if (!allowed.has(node.type.name)) unsupported.push(node.type.name); });
  const selection = getSelection();
  return {
    mode, documentId, generation, revision,
    htmlValue:document.querySelector('#comparison').value,
    editorComposing: view?.composing ?? null,
    fieldValue: root instanceof HTMLTextAreaElement ? root.value : null,
    model: model?.toJSON() ?? null,
    modelSelection:view?.state.selection.toJSON()??null, storedMarks:view?.state.storedMarks?.map(m=>m.toJSON())??null,
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
      state: EditorState.create({schema, doc: schema.node('doc',null,(SEEDS[params.get('seed')]??SEEDS.plain).split('\n').map(line=>schema.node('paragraph',null,line?[schema.text(line)]:[]))), plugins: [keymap({
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
    unregister = registerProseMirror(view,{paragraphs:"enter"});
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
  if(params.get('seed')==='marks') view.dispatch(view.state.tr.addMark(1,5,schema.marks.strong.create()).addMark(13,18,schema.marks.em.create()));
  root.addEventListener('input',e=>{if(e.isTrusted&&blurNext){blurNext=false;document.querySelector('#blur').focus();queueMicrotask(persist);}});
  root.addEventListener('paste',e=>{if(e.isTrusted&&blurNext){blurNext=false;queueMicrotask(()=>{document.querySelector('#blur').focus();persist();});}});
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
document.querySelector('#reregister').onclick=()=>{unregister();unregister=registerProseMirror(view,{paragraphs:'enter'});generation++;persist();};

document.querySelector('#pending-link').onclick=()=>{view.dispatch(view.state.tr.setStoredMarks([schema.marks.link.create({href:'https://example.invalid'})]));persist();};

document.querySelector('#paragraph-limit').onclick=()=>{view.updateState(EditorState.create({schema,doc:schema.node('doc',null,Array.from({length:128},()=>schema.node('paragraph'))),plugins:[keymap(baseKeymap)]}));revision++;persist();};

// Prototype-only read-only public EditorView mappings. No requested text or setters.
Object.defineProperty(window,'ludaSelectionProbe',{value:Object.freeze({
  identity:()=>({root,documentId,generation,model:view.state.doc}),
  at(offset,side=0){
    if(!Number.isInteger(offset)||offset<0)throw new Error('offset');
    let logical=0,position=0,target=null;
    for(let i=0;i<view.state.doc.childCount;i++){
      const paragraph=view.state.doc.child(i),text=paragraph.textContent,chars=Array.from(text);
      if(offset>=logical&&offset<=logical+chars.length){target=position+1+chars.slice(0,offset-logical).join('').length;break;}
      logical+=chars.length+1;position+=paragraph.nodeSize;
    }
    if(target===null)throw new Error('offset');
    const dom=view.domAtPos(target,side);
    return {...dom,position:target,roundtrip:view.posAtDOM(dom.node,dom.offset,1)};
  },
  current(){const s=getSelection();return s?.anchorNode&&root.contains(s.anchorNode)&&root.contains(s.focusNode)?{anchor:view.posAtDOM(s.anchorNode,s.anchorOffset,1),head:view.posAtDOM(s.focusNode,s.focusOffset,1)}:null;}
}),configurable:false});

document.querySelector('#comparison').addEventListener('input',persist);
document.querySelector('#same-length').onclick=()=>{view.dispatch(view.state.tr.insertText('Z',1,2));persist();};
