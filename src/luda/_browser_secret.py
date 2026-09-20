"""Password-only metadata and explicit native replacement; never returns value text."""
SNAPSHOT = """node => {
 if(!node.isConnected || node.getRootNode()!==document)return {error:'STALE_TARGET'};
 if(node.tagName!=='INPUT'||node.type!=='password')return {error:'NOT_PROTECTED_FIELD'};
 const style=getComputedStyle(node),rect=node.getBoundingClientRect();
 return {type:'password',tag:'INPUT',
   enabled:!node.disabled&&!node.readOnly&&!node.closest('[inert]'),
   visible:rect.width>0&&rect.height>0&&style.display!=='none'&&style.visibility==='visible',
   focused:document.hasFocus()&&document.activeElement===node,
   selection_all:node.selectionStart===0&&node.selectionEnd===node.value.length,max_length:node.maxLength,
   composition:window.__ludaOwnedComposition??{known:false,active:null}};
}"""


# DOM selection avoids Chromium's virtual Ctrl+A exporting old password text to
# X11 PRIMARY. Recheck the private metadata in the same JS call as selection.
SELECT = """node => {
 const state=("""+SNAPSHOT+""")(node);
 if(state.error)return state;
 if(!state.composition.known)return {error:'COMPOSITION_UNKNOWN'};
 if(state.composition.active)return {error:'IME_COMPOSITION_ACTIVE'};
 if(!state.enabled||!state.visible)return {error:'NOT_EDITABLE'};
 if(!state.focused)return {error:'FOCUS_CHANGED'};
 node.setSelectionRange(0,node.value.length);
 return {selected:true};
}"""


def replace(worker, token, text, Refused):
    # Import lazily: the worker owns exception/effect transport; no circular init.
    MAX_TEXT=64000
    from .common import DesktopError
    if not isinstance(text,str) or len(text)>MAX_TEXT or any(c in text for c in ('\0','\r','\n')) or any(0xD800<=ord(c)<=0xDFFF for c in text):
        raise Refused('UNSUPPORTED_TEXT')
    item,before=worker.snapshot(token,mutation=True,secret=True)
    if before.get('max_length',-1)>=0 and len(text.encode('utf-16-le'))//2>before['max_length']:
        raise Refused('UNSUPPORTED_TEXT')
    if not before['focused']:
        worker.effect='uncertain'
        worker.page.bring_to_front()
        item['node'].focus()
        worker.snapshot(token,mutation=True,focus=True,secret=True)
    def plan(chord):
        if not worker.native_target:raise Refused('FOCUS_CHANGED')
        try:worker.input.prepare_key(worker.native_target,chord)
        except DesktopError as exc:raise Refused(exc.code) from None
        # Native plan can block: recheck the exact node after it, before CDP.
        return worker.snapshot(token,mutation=True,focus=True,secret=True)[1]
    plan('ctrl+a')
    worker.effect='uncertain'
    selected=item['node'].evaluate(SELECT)
    if selected.get('error'):raise Refused(selected['error'])
    if selected.get('selected') is not True:raise Refused('SELECTION_UNVERIFIED')
    current=plan('BackSpace' if text=='' else 'ctrl+a')
    if current.get('max_length',-1)>=0 and len(text.encode('utf-16-le'))//2>current['max_length']:
        raise Refused('UNSUPPORTED_TEXT')
    if current['selection_all'] is not True:raise Refused('SELECTION_UNVERIFIED')
    worker.effect='uncertain'
    if text:worker.protocol.send('Input.insertText',{'text':text})
    else:worker.send_key('Backspace','Backspace',8)
    # Detect masking/type/focus/identity changes without reading entered text.
    worker.snapshot(token,mutation=True,focus=True,secret=True)
    return {'effect':'dispatched','secret_dispatched':True}
