"""Fixed-operation Playwright owner. No caller-supplied scripts or protocol methods."""
import json
import os
import sys
import time
import uuid
from ._browser_rich import decode as decode_rich, RichInvalid, unchanged_prefix, insertion_layout, layout_over_budget
from urllib.parse import urlsplit
from .progress import RichProgress, MAX_RICH_SEGMENTS, rich_text_progress

MAX_TEXT = 64000
MONITOR = """(() => {
 let active=false;
 window.addEventListener('compositionstart',e=>{if(e.isTrusted)active=true;},true);
 window.addEventListener('compositionend',e=>{if(e.isTrusted)active=false;},true);
 Object.defineProperty(window,'__ludaOwnedComposition',{get:()=>({known:true,active}),configurable:false});
})()"""
SNAPSHOT = """node => {
 if(!node.isConnected || node.getRootNode()!==document)return {error:'STALE_TARGET'};
 const tag=node.tagName, type=node.type;
 if(type==='password')return {error:'PROTECTED_FIELD'};
 if(!(tag==='TEXTAREA'||(tag==='INPUT'&&['text','search','url','tel'].includes(type))))return {error:'UNSUPPORTED_FIELD'};
 const style=getComputedStyle(node), rect=node.getBoundingClientRect();
 const enabled=!node.disabled&&!node.readOnly&&!node.closest('[inert]');
 const visible=rect.width>0&&rect.height>0&&style.display!=='none'&&style.visibility==='visible';
 if(node.value.length>128000)return {error:'VERIFICATION_LIMIT'};
 const text=node.value;
 if(Array.from(text).length>64000)return {error:'VERIFICATION_LIMIT'};
 const offsets=[node.selectionStart,node.selectionEnd];
 if(offsets.some(x=>x===null))return {error:'UNSUPPORTED_SELECTION'};
 if(offsets.some(x=>x>0&&x<text.length&&/[\uD800-\uDBFF]/.test(text[x-1])&&/[\uDC00-\uDFFF]/.test(text[x])))return {error:'UNSUPPORTED_SELECTION'};
 const cp=x=>Array.from(text.slice(0,x)).length;
 return {text,start:cp(offsets[0]),end:cp(offsets[1]),native:offsets,
   direction:node.selectionDirection,enabled,visible,focused:document.hasFocus()&&document.activeElement===node,
   type,tag,composition:window.__ludaOwnedComposition??{known:false,active:null}};
}"""


class Refused(Exception):
    def __init__(self, code, stage=None):
        self.code = code
        self.stage = stage


class Worker:
    def __init__(self, profile):
        self.profile = profile
        self.pw = self.context = self.page = self.protocol = None
        self.elements = {}
        self.effect = 'none'
        self.progress = None
        from ._browser_clipboard import Clipboard
        self.clipboard=Clipboard(profile)
        self.clipboard_changed=False
        self.native_target=None

    def open(self, request):
        if self.context:
            raise Refused('BROWSER_ALREADY_OPEN')
        url = request['url']
        parts = urlsplit(url)
        if len(url) > 8192 or parts.username or parts.password or not (url == 'about:blank' or parts.scheme in ('http', 'https') and parts.netloc):
            raise Refused('INVALID_ARGUMENT')
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.effect = 'uncertain'
        self.context = self.pw.chromium.launch_persistent_context(
            self.profile, executable_path=request['executable'], headless=False,
            chromium_sandbox=True, timeout=6000, no_viewport=True,
            env=dict(os.environ, ACCESSIBILITY_ENABLED='1'),
            args=['--force-renderer-accessibility'])
        self.context.set_default_timeout(1500)
        self.context.add_init_script(MONITOR)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        # Initial blank page existed before monitor registration: navigate fresh.
        self.page.goto(url, wait_until='domcontentloaded', timeout=5000)
        self.protocol = self.context.new_cdp_session(self.page)
        self.protocol.send('Emulation.setFocusEmulationEnabled', {'enabled':False})
        session = self.context.browser.new_browser_cdp_session()
        pid = next(int(p['id']) for p in session.send('SystemInfo.getProcessInfo')['processInfo'] if p['type']=='browser')
        session.detach()
        return {'pid':pid, 'version':self.context.browser.version, 'effect':'dispatched'}

    def scope(self):
        if not self.page or self.page.is_closed():
            raise Refused('BROWSER_CLOSED')
        # Sync Playwright caches frame events only while dispatching protocol
        # traffic. Check the live document too, including pending frame nodes.
        no_frames = self.page.evaluate("() => window === window.top && !document.querySelector('iframe,frame')")
        if not no_frames or len(self.context.pages) != 1 or len(self.page.frames) != 1:
            raise Refused('BROWSER_SCOPE_UNSUPPORTED')

    def inspect(self, request):
        self.scope()
        now = time.monotonic()
        for key, entry in list(self.elements.items()):
            if now-entry['time'] >= 60:
                self.dispose(key)
        doc = self.page.evaluate_handle('document')
        fields = self.page.locator('input,textarea')
        count = fields.count()
        handles = [fields.nth(i).element_handle(timeout=300) for i in range(min(count,500))]
        handles = [node for node in handles if node is not None]
        rows = []
        more = False
        try:
            for node in handles[:500]:
                meta = node.evaluate("""n=>({name:(n.getAttribute('aria-label')||Array.from(n.labels||[]).map(x=>x.textContent).join(' ')||n.getAttribute('placeholder')||'').slice(0,300),type:n.type,tag:n.tagName,disabled:n.disabled||n.readOnly,protected:n.type==='password'})""")
                role = 'entry'
                if request.get('name') and request['name'].casefold() not in meta['name'].casefold():
                    node.dispose();continue
                if request.get('role') and request['role'].casefold() not in role:
                    node.dispose();continue
                supported = meta['tag']=='TEXTAREA' or meta['type'] in ('text','search','url','tel')
                state = ['editable'] if supported and not meta['disabled'] else []
                if request.get('states') and not set(request['states']) <= set(state):
                    node.dispose();continue
                if len(rows) >= request['limit']:
                    more = True;node.dispose();continue
                token = uuid.uuid4().hex
                self.elements[token] = {'node':node,'document':self.page.evaluate_handle('document'),'time':now,'type':meta['type'],'tag':meta['tag']}
                rows.append({'token':token,'name':meta['name'],'role':role,'states':state,'protected':meta['protected'],
                             'supported':supported and not meta['protected'],'secret_entry_supported':meta['protected'] and meta['tag']=='INPUT','provider':'owned_browser',
                             'text_representation':'html_value','multiline':meta['tag']=='TEXTAREA','line_break_semantics':'LF' if meta['tag']=='TEXTAREA' else None,'actions':['focus','read','select','type'] if supported and not meta['protected'] else [],
                             'interfaces':['Text'],'unsupported_reason':'PROTECTED_FIELD' if meta['protected'] else None if supported else 'UNSUPPORTED_FIELD'})
            kept = {id(v['node']) for v in self.elements.values()}
            for node in handles:
                if id(node) not in kept:
                    node.dispose()
            while len(self.elements)>1000:
                self.dispose(next(iter(self.elements)))
            rich, rich_more = self.inspect_rich(request, now, max(0, request['limit']-len(rows)))
            rows.extend(rich)
            while len(self.elements)>1000:self.dispose(next(iter(self.elements)))
            return {'fields':rows,'truncated':count>500 or more or rich_more,'unsupported':{'frames':False,'shadow_roots':'not traversed; field tokens only refer to light DOM','contenteditable':'only explicitly registered basic paragraph editors'},'effect':'none'}
        finally:
            doc.dispose()

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

    def dispose(self, token):
        item = self.elements.pop(token)
        for name in ('node','document','bridge'):
            try:item[name].dispose()
            except Exception:pass

    def snapshot(self, token, mutation=False, focus=False, secret=False):
        self.scope()
        item = self.elements.get(token)
        if not item or time.monotonic()-item['time'] >= 60:
            raise Refused('STALE_TARGET')
        try:
            current = self.page.evaluate('doc=>document===doc',item['document'])
        except Exception:
            current = False
        if not current:
            raise Refused('STALE_TARGET')
        self.protocol.send('Emulation.setFocusEmulationEnabled', {'enabled':False})
        if secret:
            if 'bridge' in item:raise Refused('NOT_PROTECTED_FIELD')
            from ._browser_secret import SNAPSHOT as SECRET_SNAPSHOT
            value=item['node'].evaluate(SECRET_SNAPSHOT)
        elif 'bridge' in item:
            value=item['bridge'].evaluate("entry => window.__ludaProseMirror?.get(entry.id)===entry ? entry.read() : {error:'STALE_TARGET'}")
            if 'error' not in value:
                try:value=decode_rich(value)
                except RichInvalid as exc:raise Refused(exc.code) from None
        else:
            value = item['node'].evaluate(SNAPSHOT)
        if 'error' in value:
            raise Refused(value['error'])
        if value['type'] != item['type'] or value['tag'] != item['tag']:
            raise Refused('STALE_TARGET')
        if not value['visible']:
            raise Refused('NOT_EDITABLE')
        if mutation:
            if not value['composition']['known']:
                raise Refused('COMPOSITION_UNKNOWN')
            if value['composition']['active']:
                raise Refused('IME_COMPOSITION_ACTIVE')
            if not value['enabled'] or not value['visible']:
                raise Refused('NOT_EDITABLE')
        if focus and not value['focused']:
            raise Refused('FOCUS_CHANGED')
        return item, value

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

    def focus(self, token):
        item, _ = self.snapshot(token, mutation=True)
        self.effect = 'uncertain'
        self.page.bring_to_front()
        item['node'].focus()
        self.snapshot(token, mutation=True, focus=True)
        return {'effect':'verified','focused':True}

    def select(self, token, start, end):
        item, before = self.snapshot(token, mutation=True, focus=True)
        if type(start) is not int or type(end) is not int or not 0<=start<=end<=len(before['text']):
            raise Refused('INVALID_ARGUMENT')
        if before['tag']=='PROSEMIRROR':
            # Keep established full/end native selection behavior. The public
            # editor keymap synchronizes Ctrl+A's model selection directly;
            # DOM range mapping is only needed for arbitrary interior ranges.
            if start==end==len(before['text']):self.rich_key('End','End',35,2)
            elif (start,end)==(0,len(before['text'])):self.rich_key('a','KeyA',65,2)
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
        self.effect = 'uncertain'
        # Fixed selection-only operation: never assigns value or model content.
        item['node'].evaluate("""(node,range)=>{const chars=Array.from(node.value);node.setSelectionRange(chars.slice(0,range[0]).join('').length,chars.slice(0,range[1]).join('').length,'forward');}""",[start,end])
        _, after = self.snapshot(token, mutation=True, focus=True)
        if after['text']!=before['text'] or (after['start'],after['end'])!=(start,end):
            raise Refused('SELECTION_UNVERIFIED')
        return {'effect':'verified','start_offset':start,'end_offset':end,'offset_units':'Unicode code points'}

    def require_text_boundaries(self, text, start, end):
        # Public offsets remain code points. Chromium's native text transport
        # may normalize an intra-grapheme selection only during insertion.
        # Whole-field edges need no segmenter and remain usable without it.
        if start in (0,len(text)) and end in (0,len(text)):
            return
        valid=self.page.evaluate("""({text,start,end})=>{
          if(typeof Intl==='undefined'||typeof Intl.Segmenter!=='function')return null;
          const points=Array.from(text),a=points.slice(0,start).join('').length,b=points.slice(0,end).join('').length;
          const wanted=new Set([a,b]);wanted.delete(0);wanted.delete(text.length);
          for(const part of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text)){
            wanted.delete(part.index);wanted.delete(part.index+part.segment.length);
            if(!wanted.size)return true;
          }
          return wanted.size===0;
        }""",{'text':text,'start':start,'end':end})
        if valid is None:raise Refused('TEXT_BOUNDARY_UNAVAILABLE')
        if valid is not True:raise Refused('UNSUPPORTED_TEXT_BOUNDARY')

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
        if line_breaks is not None:raise Refused('UNSUPPORTED_ACTION')
        if before['tag']=='INPUT' and any(c in text for c in ('\n','\t')):
            raise Refused('UNSUPPORTED_TEXT')
        start,end=(0,len(before['text'])) if mode=='replace' else (before['start'],before['end'])
        if text or start!=end:
            self.require_text_boundaries(before['text'],start,end)
        if not before['focused']:
            self.focus(token)
            _, focused = self.snapshot(token, mutation=True, focus=True)
            if (focused['text'],focused['start'],focused['end']) != (before['text'],before['start'],before['end']):
                raise Refused('TEXT_CHANGED')
            before = focused
        start,end = (0,len(before['text'])) if mode=='replace' else (before['start'],before['end'])
        expected = before['text'][:start]+text+before['text'][end:]
        if len(expected)>MAX_TEXT:
            raise Refused('VERIFICATION_LIMIT')
        if mode=='replace':
            self.select(token,start,end)
        _, current = self.snapshot(token,mutation=True,focus=True)
        if current['text']!=before['text'] or (current['start'],current['end'])!=(start,end):
            raise Refused('TEXT_CHANGED')
        if text:
            self.require_text_boundaries(current['text'],start,end)
            self.effect = 'uncertain'
            self.protocol.send('Input.insertText',{'text':text})
        elif start!=end:
            self.require_text_boundaries(current['text'],start,end)
            self.effect = 'uncertain'
            # Browser-native deletion; never a DOM value setter.
            self.protocol.send('Input.dispatchKeyEvent',{'type':'keyDown','key':'Backspace','code':'Backspace','windowsVirtualKeyCode':8})
            self.protocol.send('Input.dispatchKeyEvent',{'type':'keyUp','key':'Backspace','code':'Backspace','windowsVirtualKeyCode':8})
        deadline=time.monotonic()+1
        while True:
            _, after=self.snapshot(token,mutation=True,focus=True)
            if after['text']==expected:
                return {'effect':'verified' if self.effect!='none' else 'none','exact_match':True,'expected_characters':len(expected),'actual_characters':len(after['text']),
                        'caret_verified':after['start']==after['end']==start+len(text),'verification':'Exact native DOM value after owned browser input; application commit is separate.'}
            if time.monotonic()>=deadline:
                raise Refused('TEXT_MISMATCH')
            self.page.wait_for_timeout(30)

    def rich_key(self, key, code, number, modifiers=0):
        self.effect='uncertain'
        self.protocol.send('Input.dispatchKeyEvent',{'type':'keyDown','key':key,'code':code,'windowsVirtualKeyCode':number,'modifiers':modifiers})
        self.protocol.send('Input.dispatchKeyEvent',{'type':'keyUp','key':key,'code':code,'windowsVirtualKeyCode':number,'modifiers':0})

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
            else:self.rich_key('End','End',35,2)
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
                if action=='return':self.progress.begin();self.rich_key('Enter','Enter',13,8 if line_breaks=='hard_break' else 0);expected+='\n';expected_layout+=insertion_layout('\n',line_breaks)
                elif action=='delete':self.progress.begin();self.rich_key('Backspace','Backspace',8)
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
        from .common import DesktopError
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
                        self.progress.begin();self.rich_key('v','KeyV',86,2);inserted+=payload;inserted_layout+=insertion_layout(payload,line_breaks)
                    else:
                        self.clipboard.prepare_key(self.native_target,('shift+Return' if line_breaks=='hard_break' else 'Return') if action=='return' else 'BackSpace')
                        _,ready=self.snapshot(token,mutation=True,focus=True)
                        if (ready['model'],ready['selection'],ready['stored_marks'])!=(fresh['model'],fresh['selection'],fresh['stored_marks']):raise Refused('TEXT_CHANGED')
                        self.progress.begin()
                        self.rich_key('Enter','Enter',13,8 if line_breaks=='hard_break' else 0) if action=='return' else self.rich_key('Backspace','Backspace',8)
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
                'existing_formatting':'preserved' if mode=='insert' else 'replaced_with_field'}

    def dispatch(self, request):
        self.effect = 'none'
        self.progress = None
        self.clipboard_changed=False
        self.native_target=request.get('native_target')
        op=request.get('op')
        if op=='open':return self.open(request)
        if op=='inspect':return self.inspect(request)
        token=request.get('token')
        if op=='read':return self.read(token,request.get('limit',16000))
        if op=='focus':return self.focus(token)
        if op=='select':return self.select(token,request['start_offset'],request['end_offset'])
        if op=='secret':
            from ._browser_secret import replace
            return replace(self,token,request.get('text'),Refused)
        if op=='type':return self.type(token,request['text'],request['mode'],request.get('line_breaks'),request.get('transport','native'))
        raise Refused('UNSUPPORTED_ACTION')


def main():
    worker=Worker(sys.argv[1])
    try:
        for raw in sys.stdin.buffer:
            if len(raw)>1024*1024:break
            worker.progress=None
            try:
                result=worker.dispatch(json.loads(raw))
            except Refused as exc:
                result={'error':exc.code,'effect':worker.effect,'clipboard_may_have_changed':worker.clipboard_changed}
                if exc.stage in ('selection_sync','caret_readback'):result['provider_stage']=exc.stage
            except Exception:
                result={'error':'BROWSER_OPERATION_FAILED','effect':worker.effect,'clipboard_may_have_changed':worker.clipboard_changed}
            progress=rich_text_progress(worker.progress.value) if worker.progress is not None else None
            if progress is not None:result['progress']=progress
            data=json.dumps(result,ensure_ascii=False,separators=(',',':'))
            if len(data.encode())>1024*1024:
                data=json.dumps({'error':'VERIFICATION_LIMIT','effect':worker.effect,**({'progress':progress} if progress is not None else {})})
            print(data,flush=True)
    finally:
        worker.clipboard.close()
        if worker.context:
            worker.context.close()
        if worker.pw:
            worker.pw.stop()


if __name__=='__main__':
    main()
