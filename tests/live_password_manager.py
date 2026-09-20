"""AUTH-03: actual KeePassXC native entry menu with synthetic disposable vault."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from luda.desktop import Desktop
from luda.common import DesktopError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qualification_matrix import private_environment,run_bounded
from qualify import source_fingerprint


def child(out):
    children=[];d=None;checks=[];evidence={}
    def wait(predicate):
        end=time.monotonic()+6
        while time.monotonic()<end:
            value=predicate()
            if value:return value
            time.sleep(.04)
        raise AssertionError('Password manager oracle deadline')
    def record(name,ok):
        checks.append({'case':name,'passed':bool(ok)});assert ok,name
    def clipboard():
        return subprocess.check_output(['xclip','-selection','clipboard','-out'],timeout=3)
    def snapshot(name):
        snap=d.observe();(out/(name+'.png')).write_bytes(base64.b64decode(snap.pop('image_base64')))
        (out/(name+'.json')).write_text(json.dumps(snap,indent=2));return snap
    vault=out/'synthetic.kdbx';master='Luda disposable master 42!'
    try:
        subprocess.run(['keepassxc-cli','db-create','-p','-t','100',str(vault)],input=(master+'\n'+master+'\n').encode(),check=True,capture_output=True,timeout=15)
        subprocess.run(['keepassxc-cli','add','-u','synthetic-user','--url','https://example.invalid','-p',str(vault),'Synthetic login'],input=(master+'\nSyntheticPassword42!\n').encode(),check=True,capture_output=True,timeout=15)
        subprocess.run(['keepassxc-cli','add','-u','wrong-entry-sentinel','--url','https://other.invalid',str(vault),'A different account'],input=(master+'\n').encode(),check=True,capture_output=True,timeout=15)
        original=hashlib.sha256(vault.read_bytes()).hexdigest()
        wm=subprocess.Popen(['xfwm4','--compositor=off']);children.append(wm)
        wait(lambda:subprocess.run(['wmctrl','-m'],capture_output=True).returncode==0)
        decoydir=out/'decoy';decoydir.mkdir()
        decoy=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/keyboard_fixture.py'),str(decoydir)]);children.append(decoy)
        app=subprocess.Popen(['keepassxc','--pw-stdin',str(vault)],stdin=subprocess.PIPE);children.append(app)
        app.stdin.write((master+'\n').encode());app.stdin.close()
        d=Desktop()
        window=wait(lambda:next((w for w in d.list_windows() if w['pid']==app.pid),None));wid=window['window_id']
        other=wait(lambda:next((w for w in d.list_windows() if w['pid']==decoy.pid),None))
        d.activate(wid)
        # Explicit visible search chooses one of two real stored entries. The
        # copied username independently proves which account the menu used.
        d.key(wid,'ctrl+f')
        d.paste(wid,'Synthetic login',shortcut='ctrl_v')
        time.sleep(.3)
        snapshot('selected-entry')
        def nodes():return d.inspect(wid,limit=500,states=['showing'])['nodes']
        def menu():
            node=wait(lambda:next((n for n in nodes() if n['role']=='menu item' and n['name']=='Entries'),None))
            d.element(node['element_id'],'invoke',action='ShowMenu')
            return wait(lambda:next((n for n in nodes() if n['role']=='menu item' and n['name']=='Copy Username'),None))
        sentinel=out/'clipboard.txt';sentinel.write_bytes(b'preserve-existing-clipboard')
        owner=subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in',str(sentinel)]);children.append(owner)
        wait(lambda:clipboard()==sentinel.read_bytes())
        item=menu();snap=snapshot('native-menu');popup=next(p for p in snap['popups'] if p['owner_window_id']==wid)
        record('actual-manager-popup-bound-to-owned-application',popup['pid']==app.pid and item['pid']==app.pid)
        b=popup['image_bounds']
        try:
            d.pointer_popup(other['window_id'],popup['popup_id'],snap['snapshot_id'],b['x']+5,b['y']+5)
        except DesktopError as exc:
            evidence['wrong_owner_error']={'code':exc.code,'effect':exc.effect}
            record('wrong-owner-popup-refused',exc.code=='STALE_TARGET' and exc.effect=='none')
        else:record('wrong-owner-popup-refused',False)
        d.key(wid,'Escape')
        wait(lambda:not d.observe()['popups'])
        record('cancel-preserves-clipboard-and-vault',clipboard()==sentinel.read_bytes() and hashlib.sha256(vault.read_bytes()).hexdigest()==original)
        try:d.element(item['element_id'],'invoke',action='Press')
        except DesktopError as exc:
            evidence['dismissed_menu_error']={'code':exc.code,'effect':exc.effect}
            record('dismissed-menu-action-refused',exc.code=='NOT_INTERACTABLE' and exc.effect=='none')
        else:record('dismissed-menu-action-refused',False)
        record('refusals-have-no-copy-or-decoy-input',clipboard()==sentinel.read_bytes() and json.loads((decoydir/'state.json').read_text())['text']=='')
        fresh=menu();snapshot('explicit-copy-menu')
        result=d.element(fresh['element_id'],'invoke',action='Press')
        wait(lambda:clipboard()==b'synthetic-user')
        record('explicit-observed-username-copy-exact',result['effect']=='dispatched' and clipboard()==b'synthetic-user' and clipboard()!=b'wrong-entry-sentinel')
        record('copy-does-not-submit-edit-or-type-credentials',hashlib.sha256(vault.read_bytes()).hexdigest()==original and json.loads((decoydir/'state.json').read_text())['text']=='')
        evidence['vault_sha256_before_after']=original
    finally:
        if d:d.close()
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        evidence['checks']=checks;(out/'results.json').write_text(json.dumps(evidence,indent=2))


def main():
    if os.geteuid()==0:raise SystemExit('Run as ordinary desktop account')
    if len(sys.argv)==3 and sys.argv[1]=='--child':return child(Path(sys.argv[2]))
    out=ROOT/'artifacts/password-manager'/str(time.time_ns());out.mkdir(parents=True)
    before=source_fingerprint(ROOT)
    with tempfile.TemporaryDirectory(prefix='luda-password-manager-') as directory:
        token=uuid.uuid4().hex;env=private_environment(Path(directory),token)
        with (out/'desktop.log').open('wb') as log:
            result=run_bounded(['xvfb-run','-a','dbus-run-session','--',sys.executable,__file__,'--child',str(out)],env,log,75,token)
    after=source_fingerprint(ROOT);result.update(source=before,source_after=after,source_unchanged=before==after)
    (out/'runner.json').write_text(json.dumps(result,indent=2));print(out,result['status'])
    return 0 if result['status']=='passed' and before==after else 1

if __name__=='__main__':raise SystemExit(main())
