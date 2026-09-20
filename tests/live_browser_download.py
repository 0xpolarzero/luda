"""Local HTTP download driven through Chromium GUI; disk and server oracles."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

from luda.desktop import Desktop
from luda.common import DesktopError

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/browser-download'
PAYLOAD = ('synthetic download 日本語 👩🏽‍💻\n' * 32768).encode()


def until(fn, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            result = fn()
        except DesktopError as exc:
            if exc.code != 'ACCESSIBILITY_UNAVAILABLE':
                raise
            result = None
        if result:
            return result
        time.sleep(.08)
    raise AssertionError('fixture condition timed out')


def main(executable):
    if os.geteuid() == 0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
        raise SystemExit('Use an ordinary UID and private X11/D-Bus/XDG session.')
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    release = threading.Event()
    started = threading.Event()
    sent = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.path == '/download':
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', 'attachment; filename="synthetic-file.txt"')
                self.send_header('Content-Length', str(len(PAYLOAD)))
                self.end_headers()
                self.wfile.write(PAYLOAD[:65536]); self.wfile.flush(); started.set()
                if release.wait(30):
                    self.wfile.write(PAYLOAD[65536:]); self.wfile.flush(); sent.set()
            else:
                body=b'<title>Luda Local Download Fixture</title><h1>Owned download fixture</h1><a href="/download">Download synthetic file</a>'
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    desktop = Desktop()
    browser = None
    def record(case, passed, **details):
        records.append({'case':case,'passed':bool(passed),**details})
        assert passed, case
    try:
        with tempfile.TemporaryDirectory(prefix='luda-download-') as directory:
            private=Path(directory); profile=private/'profile'; (profile/'Default').mkdir(parents=True)
            downloads=private/'downloads';downloads.mkdir()
            (profile/'Default/Preferences').write_text(json.dumps({'download':{'default_directory':str(downloads),'prompt_for_download':True,'directory_upgrade':True},'safebrowsing':{'enabled':False}}))
            url=f'http://127.0.0.1:{server.server_port}/'
            browser=subprocess.Popen([executable,'--no-sandbox','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1','--force-renderer-accessibility','--user-data-dir='+str(profile),'--window-size=1100,900',url],env=dict(os.environ,ACCESSIBILITY_ENABLED='1'),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            def windows():return [w for w in desktop.list_windows() if w['pid']==browser.pid]
            wid=until(lambda:next((w['window_id'] for w in windows() if 'Luda Local Download Fixture' in w['title']),None))
            desktop.activate(wid)
            def active():return until(lambda:next((w['window_id'] for w in windows() if w['active']),None))
            def nodes(window=None):
                target=window or active()
                try:
                    tree=desktop.inspect(target,limit=500)
                except DesktopError as exc:
                    with (OUT/'inspection-errors.jsonl').open('a') as log:log.write(json.dumps({'target':target,'code':exc.code})+'\n')
                    raise
                (OUT/'last-tree.json').write_text(json.dumps(tree,indent=2))
                return tree['nodes']
            def find(predicate):return until(lambda:next((n for n in nodes() if predicate(n) and 'showing' in n['states']),None))
            link=find(lambda n:n['role']=='link' and n['name']=='Download synthetic file')
            desktop.element(link['element_id'],'invoke',action=link['actions'][0])
            until(lambda:active()!=wid)
            dialog=active()
            (OUT/'dialog-windows.json').write_text(json.dumps(windows(),indent=2))
            probe="""import sys,json;sys.path.insert(0,sys.argv[1]);import ax_worker as w
rows=[]
for node,depth in w.candidates(int(sys.argv[2]),limit=200,depth=1):
 if depth!=1:continue
 row={'name':node.get_name(),'path':node.path,'interfaces':node.get_interfaces()}
 if 'Component' in row['interfaces']:
  r=node.get_component_iface().get_extents(w.Atspi.CoordType.SCREEN);row['bounds']=[r.x,r.y,r.width,r.height]
 rows.append(row)
print(json.dumps(rows))
"""
            raw=subprocess.run(['/usr/bin/python3','-c',probe,str(ROOT/'src/luda'),str(browser.pid)],capture_output=True,text=True,timeout=5)
            (OUT/'dialog-provider.json').write_text(raw.stdout)
            try:
                dialog_nodes=nodes(dialog)
                semantic={'available':True,'root_names':[n['name'] for n in dialog_nodes if n.get('parent_path') is None]}
            except DesktopError as exc:
                semantic={'available':False,'code':exc.code}
            (OUT/'dialog-semantic.json').write_text(json.dumps(semantic,indent=2))
            # Observed GTK Save File dialog starts with its Name field focused.
            # Use the visible native keyboard workflow when no semantic field exists.
            import base64
            (OUT/'save-dialog.png').write_bytes(base64.b64decode(desktop.observe()['image_base64']))
            destination=downloads/'chosen 日本語.txt'
            desktop.key(dialog,'ctrl+a')
            desktop.paste(dialog,str(destination))
            snapshot=desktop.observe()
            bounds=next(w['bounds'] for w in windows() if w['window_id']==dialog)
            x=(bounds['x']+bounds['width']-52)*snapshot['image_size']['width']/snapshot['desktop_size']['width']
            y=(bounds['y']+bounds['height']-24)*snapshot['image_size']['height']/snapshot['desktop_size']['height']
            desktop.pointer(dialog,snapshot['snapshot_id'],x,y)
            until(lambda:started.is_set())
            until(lambda:list(downloads.glob('*.crdownload')))
            record('incomplete-download-is-not-final-file',not destination.exists() and not sent.is_set())
            until(lambda:active()==wid)
            desktop.key(wid,'ctrl+j')
            incomplete=until(lambda: (lambda rows: rows if any('download in progress' in n['name'] for n in rows) else None)(nodes(wid)))
            (OUT/'incomplete-tree.json').write_text(json.dumps(incomplete,indent=2))
            record('download-progress-visible-before-completion',any('download in progress' in n['name'] for n in incomplete))
            release.set()
            until(lambda:destination.exists() and destination.read_bytes()==PAYLOAD and not list(downloads.glob('*.crdownload')))
            complete=until(lambda:[n for n in nodes(wid) if 'Show in folder' in n['name']])
            record('visible-completion-and-exact-file-agree',bool(complete) and sent.is_set(),filename=destination.name,bytes=len(PAYLOAD),sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
            record('chosen-destination-no-default-name',not (downloads/'synthetic-file.txt').exists())
    except Exception as exc:
        records.append({'case':'suite-completion','passed':False,'error_type':type(exc).__name__})
        (OUT/'failure-windows.json').write_text(json.dumps(desktop.list_windows(),indent=2))
        import base64
        (OUT/'failure.png').write_bytes(base64.b64decode(desktop.observe()['image_base64']))
        raise
    finally:
        release.set();desktop.close()
        if browser is not None:
            from signal import SIGTERM,SIGKILL
            try:os.killpg(browser.pid,SIGTERM)
            except ProcessLookupError:pass
            try:browser.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(browser.pid,SIGKILL);browser.wait(timeout=4)
        server.shutdown();server.server_close()
        (OUT/'results.json').write_text(json.dumps(records,indent=2)+'\n')
        print(json.dumps(records),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--executable',required=True)
    main(parser.parse_args().executable)
