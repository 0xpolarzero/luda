"""Fixed-operation Playwright owner. No caller-supplied scripts or protocol methods."""
import json
import os
import sys
import time
import uuid
from urllib.parse import urlsplit

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
    def __init__(self, code):
        self.code = code


class Worker:
    def __init__(self, profile):
        self.profile = profile
        self.pw = self.context = self.page = self.protocol = None
        self.elements = {}
        self.effect = 'none'

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
                             'supported':supported and not meta['protected'],'provider':'owned_browser',
                             'text_representation':'html_value','actions':['focus','read','select','type'] if supported and not meta['protected'] else [],
                             'interfaces':['Text'],'unsupported_reason':'PROTECTED_FIELD' if meta['protected'] else None if supported else 'UNSUPPORTED_FIELD'})
            kept = {id(v['node']) for v in self.elements.values()}
            for node in handles:
                if id(node) not in kept:
                    node.dispose()
            while len(self.elements)>1000:
                self.dispose(next(iter(self.elements)))
            return {'fields':rows,'truncated':count>500 or more,'unsupported':{'frames':False,'shadow_roots':'not traversed; field tokens only refer to light DOM','contenteditable':'unsupported'},'effect':'none'}
        finally:
            doc.dispose()

    def dispose(self, token):
        item = self.elements.pop(token)
        for name in ('node','document'):
            try:item[name].dispose()
            except Exception:pass

    def snapshot(self, token, mutation=False, focus=False):
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
        return {'effect':'none','text':text[:limit],'characters':len(text),'truncated':len(text)>limit,
                'caret_offset':value['start'] if value['direction']=='backward' else value['end'],
                'selections':[{'start_offset':value['start'],'end_offset':value['end']}] if value['start']!=value['end'] else [],
                'offset_units':'Unicode code points','provider_offset_units':'UTF-16 code units',
                'plain_text_verification_supported':True,'text_representation':'html_value',
                'composition':value['composition']}

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
        self.effect = 'uncertain'
        # Fixed selection-only operation: never assigns value or model content.
        item['node'].evaluate("""(node,range)=>{const chars=Array.from(node.value);node.setSelectionRange(chars.slice(0,range[0]).join('').length,chars.slice(0,range[1]).join('').length,'forward');}""",[start,end])
        _, after = self.snapshot(token, mutation=True, focus=True)
        if after['text']!=before['text'] or (after['start'],after['end'])!=(start,end):
            raise Refused('SELECTION_UNVERIFIED')
        return {'effect':'verified','start_offset':start,'end_offset':end,'offset_units':'Unicode code points'}

    def type(self, token, text, mode):
        if not isinstance(text,str) or len(text)>MAX_TEXT or '\r' in text or '\x00' in text:
            raise Refused('UNSUPPORTED_TEXT')
        if mode not in ('insert','replace'):
            raise Refused('INVALID_ARGUMENT')
        _, before = self.snapshot(token, mutation=True)
        if before['tag']=='INPUT' and any(c in text for c in ('\n','\t')):
            raise Refused('UNSUPPORTED_TEXT')
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
            self.effect = 'uncertain'
            self.protocol.send('Input.insertText',{'text':text})
        elif start!=end:
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

    def dispatch(self, request):
        self.effect = 'none'
        op=request.get('op')
        if op=='open':return self.open(request)
        if op=='inspect':return self.inspect(request)
        token=request.get('token')
        if op=='read':return self.read(token,request.get('limit',16000))
        if op=='focus':return self.focus(token)
        if op=='select':return self.select(token,request['start_offset'],request['end_offset'])
        if op=='type':return self.type(token,request['text'],request['mode'])
        raise Refused('UNSUPPORTED_ACTION')


def main():
    worker=Worker(sys.argv[1])
    try:
        for raw in sys.stdin.buffer:
            if len(raw)>1024*1024:break
            try:
                result=worker.dispatch(json.loads(raw))
            except Refused as exc:
                result={'error':exc.code,'effect':worker.effect}
            except Exception:
                result={'error':'BROWSER_OPERATION_FAILED','effect':worker.effect}
            data=json.dumps(result,ensure_ascii=False,separators=(',',':'))
            if len(data.encode())>1024*1024:
                data=json.dumps({'error':'VERIFICATION_LIMIT','effect':worker.effect})
            print(data,flush=True)
    finally:
        if worker.context:
            worker.context.close()
        if worker.pw:
            worker.pw.stop()


if __name__=='__main__':
    main()
