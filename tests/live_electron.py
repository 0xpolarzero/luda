"""Official Electron fixture; UI input through Luda, independent app-written oracle."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from luda.desktop import Desktop
from luda.common import DesktopError, stop_process

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/electron'

def wait(fn, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError('Independent oracle or UI condition did not arrive')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True)
    args = parser.parse_args()
    if os.getuid() == 0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
        parser.error('Use an ordinary account in the private qualification runner')
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    def check(case, okay, detail=None):
        results.append({'case':case,'passed':bool(okay),'detail':detail})
        assert okay, (case,detail)
    try:
        with tempfile.TemporaryDirectory(prefix='luda-electron-') as temp:
            base = Path(temp); oracle = base / 'state.json'
            env = dict(os.environ, ACCESSIBILITY_ENABLED='1', LUDA_ELECTRON_PROFILE=str(base/'profile'), LUDA_ELECTRON_ORACLE=str(oracle))
            command = [args.executable, '--no-sandbox', str(ROOT/'tests/fixtures/electron/main.js')]
            with (OUT/'application.log').open('w') as log:
                child = subprocess.Popen(command, env=env, stdout=log, stderr=log, start_new_session=True)
                d = None
                try:
                    d = Desktop()
                    def state():
                        return json.loads(oracle.read_text()) if oracle.exists() else {}
                    initial = wait(state)
                    (OUT/'environment.json').write_text(json.dumps({'command':command,'versions':initial['versions'],'accessibility':initial['accessibility'],'uid':os.getuid()},indent=2))
                    w = wait(lambda: next((w for w in d.list_windows() if w['title']=='Luda Electron Fixture'),None))
                    d.activate(w['window_id'])
                    def nodes(): return d.inspect(w['window_id'],500)['nodes']
                    def target(name): return wait(lambda: next((n for n in nodes() if (n['name']==name or (name=='Electron secret' and n.get('protected'))) and n['role'] in ('entry','text','password text','push button','check box')),None))['element_id']
                    tree=nodes();(OUT/'tree.json').write_text(json.dumps(tree,indent=2))
                    check('electron-accessibility-discovery',initial['accessibility'] and bool(target('Electron entry')))
                    for name,key in [('Electron entry','entry'),('Electron multiline','multiline')]:
                        bmp='日本語 é'
                        response=d.type_text(target(name),bmp,mode='replace')
                        wait(lambda:state().get(key)==bmp)
                        check(key+'-bmp-exact',response.get('exact_match') is True,response)
                        response=d.type_text(target(name),'',mode='replace')
                        wait(lambda:state().get(key)=='')
                        check(key+'-bmp-empty-replace',response.get('exact_match') is True,response)
                    for name,key,text in [('Electron entry','entry','日本語 é 👩🏽‍💻'),('Electron multiline','multiline','first\n日本語\t👩🏽‍💻\nlast\n')]:
                        response=d.type_text(target(name),text,mode='replace')
                        wait(lambda:state().get(key)==text)
                        check(key+'-exact',response.get('exact_match') is True and state()[key]==text,response)
                    before=d.element(target('Electron multiline'),'read')
                    try:
                        response=d.type_text(target('Electron multiline'),'',mode='replace')
                    except DesktopError as exc:
                        results.append({'case':'empty-replace-exact','passed':False,'detail':{'code':exc.code,'effect':exc.effect,'before':before,'oracle':state()}})
                        check('failed-replacement-preserves-text',state()['multiline']==before['text'])
                    else:
                        wait(lambda:state()['multiline']=='')
                        check('empty-replace-exact',response.get('exact_match') is True,response)
                    # Separate explicit GUI workflow; the semantic replacement
                    # failure above remains failing and is never retried silently.
                    if state()['multiline']=='':
                        d.type_text(target('Electron multiline'),before['text'])
                        wait(lambda:state()['multiline']==before['text'])
                    sentinel=state()['entry']
                    focused=d.element(target('Electron multiline'),'focus')
                    check('native-clear-field-focus',focused.get('effect')=='verified',focused)
                    selected=d.key(w['window_id'],'ctrl+a')
                    expected_end=len(before['text'].encode('utf-16-le'))//2
                    wait(lambda:state()['selection']=={'start':0,'end':expected_end})
                    check('native-clear-whole-field-selection',state()['multiline']==before['text'] and state()['entry']==sentinel,
                          {'dispatch':selected,'selection':state()['selection'],'utf16_length':expected_end})
                    cleared=d.key(w['window_id'],'BackSpace')
                    wait(lambda:state()['multiline']=='')
                    readback=d.element(target('Electron multiline'),'read')
                    check('native-clear-nonbmp-exact',readback['text']=='' and state()['entry']==sentinel,
                          {'dispatch':cleared,'readback':readback,'oracle':state(),
                           'scope':'Explicit full-field GUI clear, not semantic replacement or arbitrary selection verification.'})
                    secret=target('Electron secret')
                    for case,action in [('protected-type-refused',lambda:d.type_text(secret,'synthetic')),('protected-read-refused',lambda:d.element(secret,'read'))]:
                        try: action()
                        except DesktopError as exc: check(case,exc.code=='PROTECTED_FIELD' and state()['secretLength']==0,exc.code)
                        else:check(case,False)
                    try:
                        response=d.element(secret,'secret',text='synthetic')
                    except DesktopError as exc:
                        check('secret-capability-explicit',exc.code in ('UNSUPPORTED',) and state()['secretLength']==0,{'code':exc.code,'qualified_secret_write':False})
                    else:
                        wait(lambda:state()['secretLength']==9);check('secret-write',state()['secretLength']==9,response)
                    d.element(target('Electron button'),'invoke',action='press')
                    wait(lambda:state()['clicks']==1);check('button-independent-counter',True)
                    try:
                        d.element(target('Electron checkbox'),'check',checked=True)
                    except DesktopError as exc:
                        results.append({'case':'checkbox-independent-state','passed':False,'detail':exc.code})
                    else:
                        wait(lambda:state()['checked']);check('checkbox-independent-state',True)
                        d.element(target('Electron checkbox'),'check',checked=False)
                        wait(lambda:not state()['checked']);check('checkbox-uncheck-independent-state',True)
                finally:
                    try:
                        if d is not None:
                            d.close()
                    finally:
                        stop_process(child)
            # New process and profile: disabling renderer accessibility must not
            # masquerade as a usable input tree merely because native menus exist.
            oracle.unlink()
            env.update(LUDA_ELECTRON_ACCESSIBILITY='0', ACCESSIBILITY_ENABLED='0', LUDA_ELECTRON_PROFILE=str(base/'disabled-profile'))
            with (OUT/'disabled-application.log').open('w') as log:
                child=subprocess.Popen(command,env=env,stdout=log,stderr=log,start_new_session=True)
                d = None
                try:
                    d = Desktop()
                    wait(state)
                    w=wait(lambda:next((w for w in d.list_windows() if w['title']=='Luda Electron Fixture'),None))
                    d.activate(w['window_id'])
                    try:
                        tree=d.inspect(w['window_id'],500)
                    except DesktopError as exc:
                        check('disabled-accessibility-explicit',exc.code=='ACCESSIBILITY_UNAVAILABLE',exc.code)
                    else:
                        exposed=any(n['name']=='Electron entry' and n['role'] in ('entry','text') for n in tree['nodes'])
                        check('disabled-renderer-controls-absent',not exposed,{'nodes':len(tree['nodes']),'scope':'Native Electron menus can remain accessible; renderer controls are absent.'})
                finally:
                    try:
                        if d is not None:
                            d.close()
                    finally:
                        stop_process(child)
    finally:
        (OUT/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
        print(json.dumps({'cases':len(results),'passed':sum(x['passed'] for x in results)}))

    if not all(row['passed'] for row in results):
        raise SystemExit(1)

if __name__=='__main__': main()
