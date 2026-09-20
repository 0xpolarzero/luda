import {EditorState} from 'prosemirror-state';
import {EditorView} from 'prosemirror-view';
import {schema} from 'prosemirror-schema-basic';
import {keymap} from 'prosemirror-keymap';
import {baseKeymap} from 'prosemirror-commands';
import {registerProseMirror} from '/bridge.mjs';
const doc=schema.node('doc',null,[schema.node('paragraph',null,[
 schema.text('Plan 🧭: ',[schema.marks.strong.create()]),
 schema.text('old meeting details'),schema.text(' — approved',[schema.marks.em.create()])])]);
const events=[];
const view=new EditorView(document.querySelector('#host'),{
 state:EditorState.create({schema,doc,plugins:[keymap({'Shift-Enter':(state,dispatch)=>{if(dispatch)dispatch(state.tr.replaceSelectionWith(schema.nodes.hard_break.create()).scrollIntoView());return true;}}),keymap(baseKeymap)]}),
 attributes:{'aria-label':'Meeting note',role:'textbox'},
});
const unregister=registerProseMirror(view,{paragraphs:'enter',hard_breaks:'shift-enter'});
window.addEventListener('pagehide',unregister);
for(const type of ['beforeinput','input','paste'])view.dom.addEventListener(type,e=>events.push({type,inputType:e.inputType??null,trusted:e.isTrusted}));
document.querySelector('#save').onclick=async()=>{
 const actual={selection:view.state.selection.toJSON(),modelCaretCodePoints:Array.from(view.state.doc.textBetween(0,view.state.selection.head,'\n',node=>node.type.name==='hard_break'?'\n':'\uFFFC')).length,model:view.state.doc.toJSON(),html:view.dom.innerHTML,
  paragraphs:[...view.dom.querySelectorAll('p')].map(p=>p.textContent),
  strong:[...view.dom.querySelectorAll('strong')].map(p=>p.textContent),
  em:[...view.dom.querySelectorAll('em')].map(p=>p.textContent),events};
 const response=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(actual)});
 if(response.ok){document.querySelector('#status').textContent='Meeting note saved';document.title='Meeting note saved';}
};
