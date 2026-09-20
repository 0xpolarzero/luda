"""Test-only DOM selection candidate using cooperating public EditorView mappings."""
import time
from luda._browser_worker import Refused

SELECT = """({held,start,end,backward})=>{
 const probe=window.ludaSelectionProbe, now=probe.identity();
 if(now.root!==held.root||now.model!==held.model||now.generation!==held.generation||now.documentId!==held.documentId) return {error:'STALE_TARGET'};
 if(!document.hasFocus()||document.activeElement!==held.root)return {error:'FOCUS_CHANGED'};
 const composition=window.__ludaOwnedComposition;
 if(!composition?.known||composition.active)return {error:'COMPOSITION_UNKNOWN'};
 const a=probe.at(start),b=probe.at(end);
 if(a.roundtrip!==a.position||b.roundtrip!==b.position)return {error:'SELECTION_UNVERIFIED'};
 if(backward)getSelection().setBaseAndExtent(b.node,b.offset,a.node,a.offset);
 else getSelection().setBaseAndExtent(a.node,a.offset,b.node,b.offset);
 return {positions:[a.position,b.position],dom:probe.current(),immediateModel:window.__ludaProseMirror.list()[0].read().selection};
}"""


class SelectionProbe:
    def __init__(self,worker,token,desktop,window):
        self.worker=worker;self.token=token;self.desktop=desktop;self.window=window
    def read(self):
        self.desktop.target_window(self.window,True)
        return self.worker.snapshot(self.token,mutation=True,focus=True)[1]
    def capture(self):
        return self.worker.page.evaluate_handle('window.ludaSelectionProbe.identity()')
    def select(self,start,end,backward=False,held=None):
        before=self.read()
        if type(start) is not int or type(end) is not int or not 0<=start<=end<=len(before['text']):raise Refused('INVALID_ARGUMENT')
        owned=held is None;held=held or self.capture()
        try:
            result=self.worker.page.evaluate(SELECT,{'held':held,'start':start,'end':end,'backward':backward})
            if 'error' in result:raise Refused(result['error'])
            endtime=time.monotonic()+.75;polls=0
            while True:
                after=self.read();polls+=1
                if after['model']!=before['model']:raise Refused('TEXT_CHANGED')
                if (after['start'],after['end'])==(start,end) and (start==end or (after['direction']=='backward')==backward):break
                if time.monotonic()>=endtime:raise Refused('SELECTION_UNVERIFIED')
                self.worker.page.wait_for_timeout(10)
            return {'mapping':result,'polls':polls,'selection':after['selection']}
        finally:
            if owned:held.dispose()
    def replace(self,text,delete_first=False):
        before=self.read();start,end=before['start'],before['end']
        if start is None or end is None:raise Refused('UNSUPPORTED_SELECTION')
        prefix,suffix=before['text'][:start],before['text'][end:]
        styles_before=before['styled'][:start];styles_after=before['styled'][end:]
        expected=prefix+text+suffix
        if len(expected)>64000 or len(expected.split('\n'))>128 or len(text.split('\n'))>27:raise Refused('VERIFICATION_LIMIT')
        current=before;inserted='';steps=[];self.trace=[]
        if delete_first and start!=end:
            self.worker.rich_key('Backspace','Backspace',8)
            current=self.read()
            self.trace.append({'action':'initial-delete','actual':current['text'],'model':current['model']})
            if current['text']!=prefix+suffix or current['styled'][:start]!=styles_before or current['styled'][start:]!=styles_after:raise Refused('TEXT_MISMATCH')
            if (current['start'],current['end'])!=(start,start):raise Refused('SELECTION_UNVERIFIED')
        for index,segment in enumerate(text.split('\n')):
            actions=([('return',None)] if index else [])+([('text',segment)] if segment else [('delete',None)] if index==0 and start!=end and not delete_first else [])
            for action,payload in actions:
                fresh=self.read()
                if (fresh['model'],fresh['selection'],fresh['stored_marks'])!=(current['model'],current['selection'],current['stored_marks']):raise Refused('TEXT_CHANGED')
                dom=self.worker.page.evaluate('window.ludaSelectionProbe.current()')
                boundaries=self.worker.page.evaluate("text=>[0,...Array.from(new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text),s=>Array.from(text.slice(0,s.index+s.segment.length)).length)]",fresh['text'])
                self.trace.append({'action':action,'dom_before':dom,'model_selection':fresh['selection'],'grapheme_boundaries':boundaries,'endpoints_are_grapheme_boundaries':fresh['start'] in boundaries and fresh['end'] in boundaries})
                if action=='return':self.worker.rich_key('Enter','Enter',13);inserted+='\n'
                elif action=='delete':self.worker.rich_key('Backspace','Backspace',8)
                else:self.worker.protocol.send('Input.insertText',{'text':payload});inserted+=payload
                after=self.read();intended=prefix+inserted+suffix
                if after['text']!=intended or after['paragraphs']!=intended.split('\n'):raise Refused('TEXT_MISMATCH')
                if after['styled'][:start]!=styles_before or after['styled'][start+len(inserted):]!=styles_after:raise Refused('FORMATTING_CHANGED')
                if (after['start'],after['end'])!=(start+len(inserted),start+len(inserted)):raise Refused('SELECTION_UNVERIFIED')
                steps.append({'action':action,'selection':after['selection'],'model':after['model']});current=after
        return {'expected':expected,'actual':current['text'],'model':current['model'],'steps':steps,'trace':self.trace,'unaffected_marks':True}
