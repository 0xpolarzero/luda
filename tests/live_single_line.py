"""Single-line GTK/Qt/Chromium newline handling with independent storage oracles."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from luda.common import DesktopError
from luda.desktop import Desktop

ROOT=Path(__file__).resolve().parents[1]

def wait(predicate):
    end=time.monotonic()+4
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.03)
    raise AssertionError('Single-line fixture oracle timed out')

def main(executable):
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':
        raise RuntimeError('Ordinary user and private display required')
    output=ROOT/'artifacts/single-line';output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for kind in ('gtk','qt'):
        with tempfile.TemporaryDirectory(prefix='luda-single-line-') as directory:
            state=Path(directory)/'state.json'
            app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/control_fixture.py'),kind,directory],
                env=dict(os.environ,QT_ACCESSIBILITY='1',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1'))
            desktop=Desktop()
            try:
                window=wait(lambda:next((w for w in desktop.list_windows() if w['pid']==app.pid),None))
                desktop.activate(window['window_id'])
                node=wait(lambda:next((n for n in desktop.inspect(window['window_id'])['nodes'] if n['name']=='Control normal'),None))
                wait(state.exists)
                initial=json.loads(state.read_text())
                before=initial['normal']
                assert initial['normal_widget_type']=={'gtk':'Entry','qt':'QLineEdit'}[kind]
                payload='First 日本語\nSecond שלום 👩🏽‍💻\n'
                try:
                    response=desktop.type_text(node['element_id'],payload,mode='replace')
                    wait(lambda:json.loads(state.read_text())['normal']==payload)
                    actual=json.loads(state.read_text())['normal']
                    assert response['effect']=='verified' and actual==payload
                    outcome='exact_storage'
                except DesktopError as error:
                    # Never turn a generic provider/harness error into a pass.
                    time.sleep(.15)
                    actual=json.loads(state.read_text())['normal']
                    assert error.code=='TEXT_MISMATCH' and error.effect=='uncertain' and actual!=payload,(error.code,error.effect,actual)
                    response={'code':error.code,'effect':error.effect}
                    outcome='application_transformation_detected'
                rows.append({'toolkit':kind,'widget_type':initial['normal_widget_type'],'single_line_state_observed':'single-line' in node['states'],
                             'outcome':outcome,'before':before,'requested':payload,'stored':actual,'response':response})
            finally:
                desktop.close()
                app.terminate();app.wait(timeout=3)
                (output/'results.json').write_text(json.dumps({'uid':os.getuid(),'cases':rows},indent=2,ensure_ascii=False)+'\n')
    assert len(rows)==2
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=executable,headless=False,env=dict(os.environ,ACCESSIBILITY_ENABLED='1'),
            args=['--no-sandbox','--force-renderer-accessibility','--disable-background-networking'])
        desktop=Desktop()
        try:
            page=browser.new_page()
            page.set_content('<title>Luda single-line browser</title><form><input aria-label="Single-line input"><button>Submit</button></form><script>window.submissions=0;document.querySelector("form").onsubmit=e=>{e.preventDefault();window.submissions++}</script>')
            window=wait(lambda:next((w for w in desktop.list_windows() if 'Luda single-line browser' in w['title']),None))
            desktop.activate(window['window_id'])
            def field():
                try:
                    tree=desktop.inspect(window['window_id'],name='Single-line input')
                    (output/'browser-tree.json').write_text(json.dumps(tree,indent=2))
                    return next((n for n in tree['nodes'] if n['name']=='Single-line input' and n['role'] in ('entry','text')),None)
                except DesktopError as error:
                    if error.code=='ACCESSIBILITY_UNAVAILABLE':return None
                    raise
            node=wait(field)
            try:
                response=desktop.type_text(node['element_id'],payload,mode='replace')
                raise AssertionError(('Browser newline transformation was silently verified',response))
            except DesktopError as error:
                actual=page.locator('input').input_value()
                assert error.code=='TEXT_MISMATCH' and error.effect=='uncertain' and actual and actual!=payload,(error.code,error.effect,actual)
                assert page.evaluate('submissions')==0
                rows.append({'toolkit':'Chromium','version':browser.version,'outcome':'application_transformation_detected',
                    'requested':payload,'stored':actual,'code':error.code,'effect':error.effect,'implicit_submissions':0})
        finally:
            desktop.close();browser.close()
            (output/'results.json').write_text(json.dumps({'uid':os.getuid(),'cases':rows},indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(rows,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True)
    main(parser.parse_args().executable)
