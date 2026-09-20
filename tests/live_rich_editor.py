"""Test-only owned ProseMirror/native-input representation comparison; failures retained."""
import argparse
import functools
import hashlib
import http.server
import json
import os
import re
from pathlib import Path
import subprocess
import threading
import time
from playwright.sync_api import sync_playwright
from luda.desktop import Desktop
from luda.common import DesktopError
from rich_editor_probe import COMPOSITION_MONITOR, Readback, Refused

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/rich-editor'
SAMPLES = [
    ('empty', ''),
    ('unicode', 'plain 日本語 👩🏽\u200d💻 e\u0301'),
    ('two-lines', 'alpha\nbeta'),
    ('mixed-trailing-lines', 'alpha\n\t日本語 👩🏽\u200d💻 e\u0301\n\n'),
    ('edge-spaces', '  leading\n\ntrailing  \n'),
    ('three-trailing-lines', 'one\n\n\n'),
    ('literal-nbsp', 'a\u00a0b  c\u00a0\n'),
    ('tabs', '\tleft\tmiddle\t\n'),
    ('blank-only', '\n\n'),
    ('crlf', 'first\r\nsecond\r\n'),
]


def main(executable):
    if os.getuid() == 0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
        raise RuntimeError('Requires ordinary UID and private matrix desktop.')
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    oracle_lock = threading.Lock()
    oracle = {}
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            if self.path != '/oracle' or not 0 < length < 100000:
                self.send_error(400);return
            value = json.loads(self.rfile.read(length))
            with oracle_lock:
                oracle.clear();oracle.update(value)
                (OUT / 'last-app-oracle.json').write_text(json.dumps(value, ensure_ascii=False, indent=2))
            self.send_response(204);self.end_headers()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT/'tests/fixtures/rich-editor')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    desktop = Desktop()
    environment = {'uid': os.getuid(), 'revision': subprocess.run(['git', '-c', 'safe.directory='+str(ROOT), 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()}
    def record(case, passed, **details):
        rows.append({'case': case, 'passed': bool(passed), **details})
        (OUT/'results.json').write_text(json.dumps({'environment':environment, 'cases':rows}, ensure_ascii=False, indent=2))
        print(json.dumps({'case':case, 'passed':bool(passed)}), flush=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=executable, headless=False, env=dict(os.environ, ACCESSIBILITY_ENABLED='1'),
                args=['--force-renderer-accessibility', '--disable-background-networking', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--window-size=1100,900'])
            try:
                protocol = browser.new_browser_cdp_session()
                info = protocol.send('SystemInfo.getProcessInfo')['processInfo']
                browser_pid = int(next(p['id'] for p in info if p['type'] == 'browser'))
                cmdline = (Path('/proc')/str(browser_pid)/'cmdline').read_bytes().split(b'\0')
                try:
                    protocol_args = protocol.send('Browser.getBrowserCommandLine')['arguments']
                except Exception:
                    protocol_args = []
                flattened = b' '.join(cmdline).decode(errors='replace')
                unix_inodes = {line.split()[6] for line in Path('/proc/net/unix').read_text().splitlines()[1:]}
                fds = {str(fd):os.readlink(f'/proc/{browser_pid}/fd/{fd}') for fd in (3,4)}
                local_transport = all(value.startswith('socket:[') and value[8:-1] in unix_inodes for value in fds.values())
                environment.update(protocol_arguments=protocol_args, proc_arguments=[x.decode(errors='replace') for x in cmdline],
                    pipe_descriptors=fds, local_unix_transport=local_transport,
                    browser_version=browser.version, browser_pid=browser_pid,
                    debugging_pipe=bool(re.search(r'(?:^|\s)--remote-debugging-pipe(?:\s|$)', flattened)),
                    debugging_port=bool(re.search(r'(?:^|\s)--remote-debugging-port(?:=|\s|$)', flattened)))
                record('owned-browser-private-pipe', environment['debugging_pipe'] and not environment['debugging_port'] and local_transport)
                context = browser.new_context(viewport={'width':1000,'height':760}, service_workers='block')
                context.add_init_script(COMPOSITION_MONITOR)
                page = context.new_page()
                origin = f'http://127.0.0.1:{server.server_port}/index.html'
                def load(mode):
                    page.goto(origin+'?mode='+mode)
                    page.wait_for_function('window.ludaRichProbe !== undefined')
                load('prosemirror')
                until = time.monotonic()+5
                while True:
                    windows = [w for w in desktop.list_windows() if w['pid'] == browser_pid]
                    if len(windows) == 1:break
                    if time.monotonic()>until:raise RuntimeError('Owned native window not unique')
                    page.wait_for_timeout(40)
                wid = windows[0]['window_id']
                desktop.activate(wid)
                def focus():
                    until = time.monotonic()+5
                    while True:
                        tree = desktop.inspect(wid, limit=150, name='Observed rich editor')
                        fields = [n for n in tree['nodes'] if n['name']=='Observed rich editor' and n['role'] in ('entry','text')]
                        if len(fields)==1:break
                        if time.monotonic()>until:raise RuntimeError('Editor AX readiness not unique')
                        page.wait_for_timeout(40)
                    desktop.element(fields[0]['element_id'], 'focus')
                def button(name):
                    tree=desktop.inspect(wid, limit=150, name=name)
                    candidates=[n for n in tree['nodes'] if n['name']==name and n['role']=='push button']
                    if len(candidates)!=1:raise RuntimeError('Button AX not unique')
                    action=next((a for a in candidates[0]['actions'] if a in ('click','press')),None)
                    if action is None:raise RuntimeError('Observed button has no supported click/press action')
                    desktop.element(candidates[0]['element_id'], 'invoke', action=action)
                def persisted(actual):
                    until=time.monotonic()+2
                    while True:
                        with oracle_lock:value=dict(oracle)
                        if all(value.get(k)==actual[k] for k in ('documentId','generation','revision','html','model')):return value
                        if time.monotonic()>until:return value
                        page.wait_for_timeout(30)
                for mode in ('prosemirror','generic-normal','generic-prewrap'):
                    for name,payload in SAMPLES:
                        load(mode);desktop.activate(wid);focus()
                        reader=Readback(page,desktop,browser_pid,wid,True)
                        try:
                            reader.before_input()
                            desktop.key(wid,'ctrl+a')
                            reader.before_input()
                            try:
                                dispatched=desktop.paste(wid,payload,'ctrl_v')
                            except DesktopError as exc:
                                actual=reader.read()
                                record(mode+'-'+name+'-preflight-refusal',name=='crlf' and exc.code=='UNSUPPORTED_TEXT' and actual['logicalText']=='',
                                    code=exc.code, input_attempts=0, payload=payload, kind='negative-contract', actual=actual)
                                continue
                            page.wait_for_timeout(150)
                            actual=reader.read()
                            saved=persisted(actual)
                            exact=actual['logicalText']==payload
                            oracle_agrees=all(saved.get(k)==actual[k] for k in ('documentId','generation','revision','html','model'))
                            record(mode+'-'+name, exact and oracle_agrees, payload=payload,
                                representation=actual['representation'], exact_logical=exact,
                                exact_rendered=actual['renderedText']==payload, oracle_agrees=oracle_agrees,
                                response=dispatched, actual=actual, persisted=saved, input_attempts=1)
                        finally:reader.dispose()
                # Formatting remains a separate property from the same plain text.
                load('prosemirror');desktop.activate(wid);focus()
                reader=Readback(page,desktop,browser_pid,wid,True)
                reader.before_input();desktop.key(wid,'ctrl+b');reader.before_input();desktop.paste(wid,'Bold 日本語','ctrl_v');page.wait_for_timeout(150)
                actual=reader.read();saved=persisted(actual)
                marks=[mark['type'] for paragraph in actual['model']['content'] for node in paragraph.get('content',[]) for mark in node.get('marks',[])]
                record('prosemirror-paste-with-bold-stored-marks',actual['logicalText']=='Bold 日本語' and 'strong' in marks and saved.get('model')==actual['model'], actual=actual)
                reader.dispose()
                # A distinct explicit GUI formatting workflow, not a retry of the
                # failed stored-marks assumption above.
                load('prosemirror');desktop.activate(wid);focus()
                reader=Readback(page,desktop,browser_pid,wid,True)
                reader.before_input();desktop.paste(wid,'Bold 日本語','ctrl_v');reader.dispose()
                reader=Readback(page,desktop,browser_pid,wid,True)
                reader.before_input();desktop.key(wid,'ctrl+a');reader.before_input();desktop.key(wid,'ctrl+b');page.wait_for_timeout(150)
                actual=reader.read();saved=persisted(actual)
                marks=[mark['type'] for paragraph in actual['model']['content'] for node in paragraph.get('content',[]) for mark in node.get('marks',[])]
                record('prosemirror-bold-selection-preserves-text',actual['logicalText']=='Bold 日本語' and 'strong' in marks and '<strong>' in actual['html'] and saved.get('model')==actual['model'],actual=actual)
                reader.dispose()
                # Explicit hard-line-break semantics: each LF requests Shift+Return,
                # never paragraph paste. Every case starts in a fresh document.
                for name,payload in SAMPLES:
                    if name=='crlf':continue
                    load('prosemirror');desktop.activate(wid);focus()
                    operations=[]
                    for index,part in enumerate(payload.split('\n')):
                        reader=Readback(page,desktop,browser_pid,wid,True)
                        reader.before_input()
                        if index:
                            desktop.key(wid,'shift+Return');operations.append('hard-line-break')
                            reader.dispose();reader=Readback(page,desktop,browser_pid,wid,True);reader.before_input()
                        if part:
                            desktop.paste(wid,part,'ctrl_v');operations.append('paste-segment')
                        reader.dispose()
                    page.wait_for_timeout(150)
                    reader=Readback(page,desktop,browser_pid,wid,True);actual=reader.read();saved=persisted(actual)
                    exact=actual['logicalText']==payload
                    record('prosemirror-hard-break-'+name,exact and saved.get('model')==actual['model'],payload=payload,actual=actual,persisted=saved,operations=operations,route='explicit-hard-line-breaks',input_attempts=1)
                    reader.dispose()
                    if name=='mixed-trailing-lines' and exact:
                        reader=Readback(page,desktop,browser_pid,wid,True);reader.before_input();desktop.paste(wid,'TAIL','ctrl_v');page.wait_for_timeout(100)
                        actual=reader.read();saved=persisted(actual)
                        record('hard-break-subsequent-caret-insertion',actual['logicalText']==payload+'TAIL' and saved.get('model')==actual['model'],actual=actual)
                        reader.dispose()
                # Distinct paragraph semantics in fresh documents: native Return
                # uses this pinned editor's baseKeymap splitBlock command.
                for name,payload in SAMPLES:
                    if name=='crlf':continue
                    load('prosemirror');desktop.activate(wid);focus()
                    operations=[]
                    for index,part in enumerate(payload.split('\n')):
                        reader=Readback(page,desktop,browser_pid,wid,True);reader.before_input()
                        if index:
                            desktop.key(wid,'Return');operations.append('split-paragraph')
                            reader.dispose();reader=Readback(page,desktop,browser_pid,wid,True);reader.before_input()
                        if part:
                            desktop.paste(wid,part,'ctrl_v');operations.append('paste-segment')
                        reader.dispose()
                    page.wait_for_timeout(150)
                    reader=Readback(page,desktop,browser_pid,wid,True);actual=reader.read();saved=persisted(actual)
                    paragraphs=actual['model'].get('content',[])
                    structure=len(paragraphs)==len(payload.split('\n')) and all(p['type']=='paragraph' for p in paragraphs)
                    exact=actual['logicalText']==payload
                    record('prosemirror-paragraph-'+name,exact and structure and saved.get('model')==actual['model'],payload=payload,actual=actual,persisted=saved,operations=operations,route='explicit-paragraph-separators',exact_structure=structure,input_attempts=1)
                    reader.dispose()
                    if name=='mixed-trailing-lines' and exact:
                        reader=Readback(page,desktop,browser_pid,wid,True);reader.before_input();desktop.paste(wid,'TAIL','ctrl_v');page.wait_for_timeout(100)
                        actual=reader.read();saved=persisted(actual)
                        record('paragraph-subsequent-caret-insertion',actual['logicalText']==payload+'TAIL' and saved.get('model')==actual['model'],actual=actual)
                        reader.dispose()
                # Fresh documents isolate negative attempts; no failed mutation retries.
                for case,label,expected in (
                    ('replaced-node','Replace editor node','NODE_REPLACED'),
                    ('navigation','Reload document','DOCUMENT_CHANGED'),
                    ('pending-composition','Synthetic pending composition','COMPOSITION_PENDING'),
                    ('embedded-model','Insert image model node','MODEL_EMBED_UNSUPPORTED')):
                    load('prosemirror');desktop.activate(wid);focus()
                    reader=Readback(page,desktop,browser_pid,wid,True)
                    button(label);page.wait_for_timeout(200)
                    try:
                        reader.before_input()
                        refused=None
                    except Refused as exc:refused=str(exc)
                    record('guard-'+case,refused==expected, refused=refused, input_attempts=0,
                        synthetic_composition_event=case=='pending-composition', actual=page.evaluate('window.ludaRichProbe.snapshot()'))
                    reader.dispose()
                load('prosemirror');desktop.activate(wid);focus()
                try:
                    reader=Readback(page,desktop,browser_pid,wid,False)
                    reader.dispose();refused=None
                except Refused as exc:refused=str(exc)
                record('guard-late-attach-composition-unknown',refused=='COMPOSITION_UNKNOWN',refused=refused,input_attempts=0)
            finally:browser.close()
    except Exception as exc:
        record('harness-failure',False,error=type(exc).__name__,message=str(exc))
    finally:
        desktop.close();server.shutdown();server.server_close()
    return 0 if rows and all(row['passed'] for row in rows) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True)
    raise SystemExit(main(parser.parse_args().executable))
