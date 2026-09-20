"""Optional ProseMirror worker; inherits core browser ownership and target checks."""
import time
import uuid
from luda._browser_worker import Worker as BrowserWorker, Refused, MAX_TEXT, main
from .model import decode as decode_rich, RichInvalid, unchanged_prefix, insertion_layout, layout_over_budget
from .progress import RichProgress, MAX_RICH_SEGMENTS, rich_text_progress

class Worker(BrowserWorker):
    def __init__(self, profile):
        super().__init__(profile)
        from .clipboard import Clipboard
        self.clipboard = Clipboard(profile)

    def inspect(self, request):
        self.scope()
        now = time.monotonic()
        for key, entry in list(self.elements.items()):
            if now-entry['time'] >= 60:
                self.dispose(key)
        rows, more = self.inspect_rich(request, now, request['limit'])
        while len(self.elements)>1000:
            self.dispose(next(iter(self.elements)))
        return {'fields':rows,'truncated':more,'unsupported':{'frames':False,'contenteditable':'explicitly registered supported ProseMirror only'},'bridge': 'connected' if rows else 'no_matching_editor',
                'setup':'The application must register a supported ProseMirror editor; installing the agent plugin alone does not enable arbitrary websites.', 'effect':'none'}

    def read_value(self, item, secret=False):
        if secret:
            raise Refused('NOT_PROTECTED_FIELD')
        value=item['bridge'].evaluate("entry => window.__ludaProseMirror?.get(entry.id)===entry ? entry.read() : {error:'STALE_TARGET'}")
        if 'error' not in value:
            try:
                value=decode_rich(value)
            except RichInvalid as exc:
                raise Refused(exc.code) from None
        return value

    def receipt_progress(self):
        return rich_text_progress(self.progress.value) if self.progress is not None else None

    def close_input(self):
        self.clipboard.close()

    def dispatch_type(self, request):
        return self.type(request.get('token'),request['text'],request['mode'],request.get('line_breaks'),request.get('transport','native'))

    def inspect_rich(self, request, now, limit):
        registry=self.page.evaluate_handle("() => window.__ludaProseMirror?.version===1 ? window.__ludaProseMirror.list().slice(0,32) : []")
        entries=registry.get_properties();rows=[];more=False
        try:
            for key,entry in entries.items():
                if not key.isdigit():entry.dispose();continue
                node=entry.get_property('root')
                meta=node.evaluate("n=>({name:(n.getAttribute('aria-label')||'').slice(0,300)})")
                observed=entry.evaluate('entry=>entry.read()')
                problem=observed.get('error')
                if not problem:
                    try:decode_rich(observed)
                    except RichInvalid as exc:problem=exc.code
                role='entry';states=['editable'] if not problem and observed.get('enabled') else []
                if request.get('name') and request['name'].casefold() not in meta['name'].casefold() or request.get('role') and request['role'].casefold() not in role or request.get('states') and not set(request['states'])<=set(states):
                    entry.dispose();node.dispose();continue
                if len(rows)>=limit:
                    more=True;entry.dispose();node.dispose();continue
                ranges=entry.evaluate("entry=>typeof entry.at==='function'&&typeof entry.identity==='function'")
                token=uuid.uuid4().hex
                self.elements[token]={'node':node,'bridge':entry,'document':self.page.evaluate_handle('document'),'time':now,'type':observed.get('contract','basic-paragraphs-v1'),'tag':'PROSEMIRROR'}
                rows.append({'token':token,'name':meta['name'],'role':role,'states':states,'protected':False,'supported':not problem,'unsupported_reason':problem,
                             'provider':'owned_browser','text_representation':'paragraphs_with_hard_breaks' if observed.get('contract')=='basic-paragraphs-hard-breaks-v1' else 'paragraphs','actions':[] if problem else ['focus','read','select','type'],
                             'interfaces':['Text'],'multiline':True,'line_break_semantics':'explicit paragraph or hard_break' if observed.get('contract')=='basic-paragraphs-hard-breaks-v1' else 'paragraph','supported_line_breaks':['paragraph','hard_break'] if observed.get('contract')=='basic-paragraphs-hard-breaks-v1' else ['paragraph'],'write_scope':'native: whole-field replace or append at end; explicit clipboard: selected code-point range','transports':['native','clipboard'],'selection_scope':'code-point ranges' if ranges else 'whole-field or end; update cooperating bridge for arbitrary ranges'})
            return rows,more
        finally:registry.dispose()

    def read(self, token, limit):
        _, value = self.snapshot(token)
        text = value['text']
        result = {'effect':'none','text':text[:limit],'characters':len(text),'truncated':len(text)>limit,
                'caret_offset':value['start'] if value['direction']=='backward' else value['end'],
                'selections':[{'start_offset':value['start'],'end_offset':value['end']}] if value['start']!=value['end'] else [],
                'offset_units':'Unicode code points','provider_offset_units':'UTF-16 code units',
                'plain_text_verification_supported':True,'text_representation':'html_value',
                'composition':value['composition']}
        if value['tag']=='PROSEMIRROR':
            result.update(text_representation='paragraphs_with_hard_breaks' if value['hard_breaks_supported'] else 'paragraphs',model=value['model'] if len(text)<=limit else None,model_truncated=len(text)>limit,stored_marks=value['stored_marks'],line_breaks='paragraph_and_hard_break' if value['hard_breaks_supported'] else 'paragraph',selection_supported=value['start'] is not None)
            if value['hard_breaks_supported']:result['line_break_boundaries']=[{'offset':i,'kind':'paragraph' if kind=='p' else 'hard_break'} for i,kind in enumerate(value['layout'][:limit]) if kind!='t']
        return result

    def select(self, token, start, end):
        item, before = self.snapshot(token, mutation=True, focus=True)
        if type(start) is not int or type(end) is not int or not 0<=start<=end<=len(before['text']):
            raise Refused('INVALID_ARGUMENT')
        # Keep established full/end native selection behavior. The public
        # editor keymap synchronizes Ctrl+A's model selection directly;
        # DOM range mapping is only needed for arbitrary interior ranges.
        if start==end==len(before['text']):self.send_key('End','End',35,2)
        elif (start,end)==(0,len(before['text'])):self.send_key('a','KeyA',65,2)
        elif not item['bridge'].evaluate("entry=>typeof entry.at==='function'&&typeof entry.identity==='function'"):
            raise Refused('UNSUPPORTED_SELECTION')
        else:
            held=item['bridge'].evaluate_handle('entry=>entry.identity()')
            try:
                # The captured model must still match the snapshot before selection.
                _,current=self.snapshot(token,mutation=True,focus=True)
                if current['model']!=before['model']:raise Refused('TEXT_CHANGED')
                self.effect='uncertain'
                result=item['bridge'].evaluate("""(entry,{held,start,end})=>{
                  if(window.__ludaProseMirror?.get(entry.id)!==entry||entry.identity()!==held)return {error:'STALE_TARGET'};
                  if(!document.hasFocus()||document.activeElement!==entry.root)return {error:'FOCUS_CHANGED'};
                  if(!window.__ludaOwnedComposition?.known||window.__ludaOwnedComposition.active)return {error:'COMPOSITION_UNKNOWN'};
                  const a=entry.at(start),b=entry.at(end);
                  if(!a||!b||!entry.root.contains(a.node)||!entry.root.contains(b.node)||a.node.getRootNode()!==document||b.node.getRootNode()!==document||a.roundtrip!==a.position||b.roundtrip!==b.position)return {error:'SELECTION_UNVERIFIED'};
                  getSelection().setBaseAndExtent(a.node,a.offset,b.node,b.offset);return {};
                }""",{'held':held,'start':start,'end':end})
                if result.get('error'):raise Refused(result['error'])
            finally:held.dispose()
        deadline=time.monotonic()+.75
        while True:
            _,after=self.snapshot(token,mutation=True,focus=True)
            if after['model']!=before['model']:raise Refused('TEXT_CHANGED')
            if (after['start'],after['end'])==(start,end):break
            if time.monotonic()>=deadline:raise Refused('SELECTION_UNVERIFIED','selection_sync')
            self.page.wait_for_timeout(10)
        return {'effect':'verified','start_offset':start,'end_offset':end,'offset_units':'Unicode code points'}

    def type(self, token, text, mode, line_breaks=None, transport="native"):
        if not isinstance(text,str) or len(text)>MAX_TEXT or '\r' in text or '\x00' in text:
            raise Refused('UNSUPPORTED_TEXT')
        if mode not in ('insert','replace'):
            raise Refused('INVALID_ARGUMENT')
        if transport not in ('native','clipboard'):raise Refused('INVALID_ARGUMENT')
        _, before = self.snapshot(token, mutation=True)
        if transport=='clipboard':
            if before['tag']!='PROSEMIRROR':raise Refused('UNSUPPORTED_ACTION')
            return self.rich_clipboard_type(token,text,mode,line_breaks,before)
        if before['tag']=='PROSEMIRROR':return self.rich_type(token,text,mode,line_breaks,before)
        raise Refused('UNSUPPORTED_FIELD')

    def rich_type(self, token, text, mode, line_breaks, before):
        if '\n' in text and line_breaks not in ('paragraph','hard_break'):raise Refused('LINE_BREAK_SEMANTICS_REQUIRED')
        if line_breaks not in (None,'paragraph','hard_break') or line_breaks=='hard_break' and not before.get('hard_breaks_supported'):raise Refused('UNSUPPORTED_ACTION')
        if mode=='insert' and (before['start'],before['end'])!=(len(before['text']),len(before['text'])):
            raise Refused('UNSUPPORTED_SELECTION')
        predicted_layout=(before['layout'] if mode=='insert' else '')+insertion_layout(text,line_breaks)
        if layout_over_budget(predicted_layout):raise Refused('VERIFICATION_LIMIT')
        segments=text.split('\n')
        if len(segments)>MAX_RICH_SEGMENTS or (len(before['paragraphs']) if mode=='insert' else 1)+(len(segments)-1 if line_breaks!='hard_break' else 0)>128 or len(text)+(len(before['text']) if mode=='insert' else 0)>MAX_TEXT:
            raise Refused('VERIFICATION_LIMIT')
        self.progress=RichProgress(len(segments))
        if text:
            start,end=(0,len(before['text'])) if mode=='replace' else (before['start'],before['end'])
            self.require_text_boundaries(before['text'],start,end)
        if not before['focused']:self.focus(token)
        _,current=self.snapshot(token,mutation=True,focus=True)
        if current['model']!=before['model'] or (current['start'],current['end'],current['stored_marks'])!=(before['start'],before['end'],before['stored_marks']):raise Refused('TEXT_CHANGED')
        if mode=='replace':
            if before['text']:self.select(token,0,len(before['text']))
            else:self.send_key('End','End',35,2)
            _,current=self.snapshot(token,mutation=True,focus=True)
            if current['model']!=before['model']:raise Refused('TEXT_CHANGED')
        expected=before['text'] if mode=='insert' else ''
        expected_layout=before['layout'] if mode=='insert' else ''
        original=before if mode=='insert' else None
        deadline=time.monotonic()+6
        for index,segment in enumerate(segments):
            actions=([('return',None)] if index else [])+([('text',segment)] if segment else [('delete',None)] if index==0 and mode=='replace' and before['text'] else [])
            for action,payload in actions:
                if time.monotonic()>=deadline:raise Refused('BROWSER_TIMEOUT')
                _,fresh=self.snapshot(token,mutation=True,focus=True)
                if (fresh['model'],fresh['selection'],fresh['stored_marks'])!=(current['model'],current['selection'],current['stored_marks']):raise Refused('TEXT_CHANGED')
                if action=='return':self.progress.begin();self.send_key('Enter','Enter',13,8 if line_breaks=='hard_break' else 0);expected+='\n';expected_layout+=insertion_layout('\n',line_breaks)
                elif action=='delete':self.progress.begin();self.send_key('Backspace','Backspace',8)
                else:
                    self.require_text_boundaries(fresh['text'],fresh['start'],fresh['end'])
                    self.progress.begin();self.effect='uncertain';self.protocol.send('Input.insertText',{'text':payload});expected+=payload;expected_layout+=insertion_layout(payload,line_breaks)
                _,after=self.snapshot(token,mutation=True,focus=True)
                if after['text']!=expected or after['layout']!=expected_layout:
                    raise Refused('TEXT_MISMATCH')
                if original and not unchanged_prefix(original,after):raise Refused('FORMATTING_CHANGED')
                if after['start']!=after['end'] or after['end']!=len(expected):raise Refused('SELECTION_UNVERIFIED','caret_readback')
                current=after
            self.progress.complete()
        return {'effect':'verified' if self.effect!='none' else 'none','exact_match':True,'expected_characters':len(expected),'actual_characters':len(current['text']),
                'caret_verified':current['start']==current['end']==len(expected),'text_representation':'paragraphs_with_hard_breaks' if before.get('hard_breaks_supported') else 'paragraphs','line_breaks':line_breaks or 'paragraph',
                'model':current['model'],'stored_marks':current['stored_marks'],'existing_formatting':'preserved' if mode=='insert' else 'replaced_with_field',
                'verification':'Exact paragraph text, structure and unaffected existing marks; new formatting follows application behavior. Application commit is separate.'}

    def rich_clipboard_type(self, token, text, mode, line_breaks, before):
        from luda.common import DesktopError
        if '\n' in text and line_breaks not in ('paragraph','hard_break'):raise Refused('LINE_BREAK_SEMANTICS_REQUIRED')
        if line_breaks not in (None,'paragraph','hard_break') or line_breaks=='hard_break' and not before.get('hard_breaks_supported'):raise Refused('UNSUPPORTED_ACTION')
        start,end=(0,len(before['text'])) if mode=='replace' else (before['start'],before['end'])
        if start is None or end is None:raise Refused('UNSUPPORTED_SELECTION')
        prefix,suffix=before['text'][:start],before['text'][end:]
        expected=prefix+text+suffix
        expected_layout=before['layout'][:start]+insertion_layout(text,line_breaks)+before['layout'][end:]
        if len(expected)>MAX_TEXT or layout_over_budget(expected_layout) or len(text.split('\n'))>MAX_RICH_SEGMENTS:raise Refused('VERIFICATION_LIMIT')
        self.progress=RichProgress(len(text.split('\n')))
        if not self.native_target:raise Refused('BROWSER_SCOPE_UNSUPPORTED')
        try:self.clipboard.preflight()
        except DesktopError as exc:raise Refused(exc.code) from None
        if not before['focused']:self.focus(token)
        _,current=self.snapshot(token,mutation=True,focus=True)
        if (current['model'],current['selection'],current['stored_marks'])!=(before['model'],before['selection'],before['stored_marks']):raise Refused('TEXT_CHANGED')
        if mode=='replace':
            self.select(token,start,end)
            _,current=self.snapshot(token,mutation=True,focus=True)
            if current['model']!=before['model']:raise Refused('TEXT_CHANGED')
        prefix_marks=before['styled'][:start];suffix_marks=before['styled'][end:]
        inserted='';inserted_layout='';deadline=time.monotonic()+6
        for index,segment in enumerate(text.split('\n')):
            actions=([('return',None)] if index else [])+([('paste',segment)] if segment else [('delete',None)] if index==0 and start!=end else [])
            for action,payload in actions:
                if time.monotonic()>=deadline:raise Refused('BROWSER_TIMEOUT')
                _,fresh=self.snapshot(token,mutation=True,focus=True)
                if (fresh['model'],fresh['selection'],fresh['stored_marks'])!=(current['model'],current['selection'],current['stored_marks']):raise Refused('TEXT_CHANGED')
                try:
                    self.clipboard.preflight()
                    if action=='paste':
                        def publishing():
                            self.progress.begin();self.effect='uncertain';self.clipboard_changed=True
                        self.clipboard.stage(payload,publishing)
                        _,staged=self.snapshot(token,mutation=True,focus=True)
                        if (staged['model'],staged['selection'],staged['stored_marks'])!=(fresh['model'],fresh['selection'],fresh['stored_marks']):raise Refused('TEXT_CHANGED')
                        self.clipboard.verify(payload)
                        self.clipboard.prepare_key(self.native_target,'ctrl+v')
                        self.clipboard.verify(payload)
                        _,ready=self.snapshot(token,mutation=True,focus=True)
                        if (ready['model'],ready['selection'],ready['stored_marks'])!=(fresh['model'],fresh['selection'],fresh['stored_marks']):raise Refused('TEXT_CHANGED')
                        self.progress.begin();self.send_key('v','KeyV',86,2);inserted+=payload;inserted_layout+=insertion_layout(payload,line_breaks)
                    else:
                        self.clipboard.prepare_key(self.native_target,('shift+Return' if line_breaks=='hard_break' else 'Return') if action=='return' else 'BackSpace')
                        _,ready=self.snapshot(token,mutation=True,focus=True)
                        if (ready['model'],ready['selection'],ready['stored_marks'])!=(fresh['model'],fresh['selection'],fresh['stored_marks']):raise Refused('TEXT_CHANGED')
                        self.progress.begin()
                        self.send_key('Enter','Enter',13,8 if line_breaks=='hard_break' else 0) if action=='return' else self.send_key('Backspace','Backspace',8)
                        if action=='return':inserted+='\n';inserted_layout+=insertion_layout('\n',line_breaks)
                except DesktopError as exc:raise Refused(exc.code) from None
                intended=prefix+inserted+suffix
                until=min(deadline,time.monotonic()+.75)
                while True:
                    _,after=self.snapshot(token,mutation=True,focus=True)
                    if after['text']==intended:break
                    if time.monotonic()>=until:raise Refused('TEXT_MISMATCH')
                    self.page.wait_for_timeout(10)
                if after['layout']!=before['layout'][:start]+inserted_layout+before['layout'][end:]:raise Refused('TEXT_MISMATCH')
                if after['styled'][:start]!=prefix_marks or after['styled'][start+len(inserted):]!=suffix_marks:raise Refused('FORMATTING_CHANGED')
                if (after['start'],after['end'])!=(start+len(inserted),start+len(inserted)):raise Refused('SELECTION_UNVERIFIED')
                current=after
            self.progress.complete()
        return {'effect':'verified' if self.effect!='none' else 'none','exact_match':True,'transport':'clipboard',
                'clipboard_changed':self.clipboard_changed,'clipboard':'Final nonempty segment remains until another owner replaces it or the temporary browser session closes; PRIMARY unchanged.' if self.clipboard_changed else 'CLIPBOARD and PRIMARY unchanged by this request.',
                'expected_characters':len(expected),'actual_characters':len(current['text']),'caret_verified':True,
                'text_representation':'paragraphs_with_hard_breaks' if before.get('hard_breaks_supported') else 'paragraphs','line_breaks':line_breaks or 'paragraph','model':current['model'],'stored_marks':current['stored_marks'],
                'existing_formatting':'preserved' if mode=='insert' else 'replaced_with_field',
                'verification':'Exact paragraph text, structure and unaffected existing marks; new formatting follows application behavior. Application commit is separate.'}


if __name__ == '__main__':
    main(Worker)
