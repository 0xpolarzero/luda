import {EditorState} from 'prosemirror-state';
import {EditorView} from 'prosemirror-view';
import {schema} from 'prosemirror-schema-basic';
import {keymap} from 'prosemirror-keymap';
import {baseKeymap} from 'prosemirror-commands';
import {registerProseMirror} from '/bridge.mjs';
const doc=schema.node('doc',null,[schema.node('paragraph',null,[
 schema.text('Pré 👩🏽‍💻: ',[schema.marks.strong.create()]),
 schema.text('ancien é'),schema.text(' / FIN',[schema.marks.em.create()])])]);
const events=[];
const view=new EditorView(document.querySelector('#host'),{
 state:EditorState.create({schema,doc,plugins:[keymap(baseKeymap)]}),
 attributes:{'aria-label':'Travel note',role:'textbox'},
});
const unregister=registerProseMirror(view,{paragraphs:'enter'});
window.addEventListener('pagehide',unregister);
for(const type of ['beforeinput','input','paste'])view.dom.addEventListener(type,e=>events.push({type,inputType:e.inputType??null,trusted:e.isTrusted}));
document.querySelector('#save').onclick=async()=>{
 const actual={model:view.state.doc.toJSON(),html:view.dom.innerHTML,
  paragraphs:[...view.dom.querySelectorAll('p')].map(p=>p.textContent),
  strong:[...view.dom.querySelectorAll('strong')].map(p=>p.textContent),
  em:[...view.dom.querySelectorAll('em')].map(p=>p.textContent),events};
 const response=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(actual)});
 if(response.ok){document.querySelector('#status').textContent='Travel note saved';document.title='Travel note saved';}
};
