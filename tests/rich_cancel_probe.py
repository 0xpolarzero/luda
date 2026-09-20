"""Test-only, explicitly requested native Escape cancellation correlation."""
from rich_editor_probe import Readback, Refused

CANCEL_MONITOR = """(() => {
  let active=false, generation=0, serial=0, pending=null, completed=null;
  const events=[];
  const note = event => {
    events.push({type:event.type,trusted:event.isTrusted,key:event.key??null,
      code:event.code??null,isComposing:event.isComposing??null,
      inputType:event.inputType??null,target:event.target?.id??null,generation});
    if(events.length>160) events.shift();
  };
  for(const type of ['compositionstart','compositionend','keydown','keyup','beforeinput','input']) {
    window.addEventListener(type,event=> {
      note(event);
      if(!event.isTrusted)return;
      if(type==='compositionstart'){active=true;generation++;pending=null;completed=null;return;}
      if(type==='compositionend'){active=false;pending=null;return;}
      if(!pending)return;
      if(Date.now()>pending.deadline || pending.generation!==generation || event.target!==pending.target){pending=null;return;}
      if(type==='keydown') {
        if(event.code==='Escape' && event.isComposing===true && !event.repeat) pending.down=true;
        else pending=null;
      } else if(type==='keyup' && event.code==='Escape') {
        if(pending.down && event.isComposing===false){active=false;completed=pending.token;}
        pending=null;
      }
    },true);
  }
  window.addEventListener('blur', event=>{if(event.isTrusted){pending=null;completed=null;}},true);
  Object.defineProperty(window,'__ludaRichComposition',{get:()=>({known:true,active,generation,completed,pending:!!pending,events:events.slice()}),configurable:false});
  Object.defineProperty(window,'__ludaCancelProbe',{value:Object.freeze({
    arm(target){
      if(!active)return {error:'NO_COMPOSITION_ACTIVE'};
      if(!target?.isConnected || document.activeElement!==target || !document.hasFocus())return {error:'FOCUS_CHANGED'};
      pending={token:++serial,target,generation,deadline:Date.now()+1500,down:false};
      return {token:pending.token,generation};
    },
    disarm(){pending=null;},
    consume(token, expectedGeneration){
      if(active || generation!==expectedGeneration || completed!==token)return false;
      completed=null;pending=null;return true;
    }
  }),configurable:false});
})()"""


class CancelReadback(Readback):
    def arm_cancel(self):
        self.read(allow_composition=True)
        result=self.node.evaluate('node=>window.__ludaCancelProbe.arm(node)')
        if 'error' in result:raise Refused(result['error'])
        return result

    def finish_cancel(self, ticket):
        # Revalidate native window, Document, exact node and focus before
        # consuming a correlation. No trust in a successful key dispatch alone.
        self.read(allow_composition=True)
        state=self.page.evaluate('window.__ludaRichComposition')
        self.page.evaluate('window.__ludaCancelProbe.disarm()')
        if state['generation']!=ticket['generation'] or state['active'] or state['completed']!=ticket['token']:
            raise Refused('CANCEL_UNCONFIRMED')
        consumed=self.page.evaluate('t=>window.__ludaCancelProbe.consume(t.token,t.generation)',ticket)
        if not consumed:raise Refused('CANCEL_UNCONFIRMED')
        return self.read()
