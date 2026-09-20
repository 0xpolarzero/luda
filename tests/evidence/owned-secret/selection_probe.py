import os,subprocess,json,tempfile,time
from playwright.sync_api import sync_playwright
assert os.getuid()!=0
rows=[];old='old-synthetic-password';new='new-synthetic-password'
with sync_playwright() as p,tempfile.TemporaryDirectory(prefix='secret-selection-') as profile:
 context=p.chromium.launch_persistent_context(profile,headless=False,chromium_sandbox=True,executable_path='/workspace/silo-desktop-research/browsers/chromium-1243/chrome-linux-arm64/chrome',args=['--force-renderer-accessibility'])
 try:
  page=context.pages[0];protocol=context.new_cdp_session(page);protocol.send('Emulation.setFocusEmulationEnabled',{'enabled':False})
  for method in ('virtual_ctrl_a','dom_range','dom_select'):
   page.set_content('<input id="password" type="password" value="'+old+'">');page.bring_to_front();node=page.query_selector('input');node.focus()
   owner=subprocess.Popen(['xclip','-quiet','-selection','primary'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    owner.stdin.write(b'primary-fixture-marker');owner.stdin.close();time.sleep(.1)
    before=subprocess.check_output(['xclip','-selection','primary','-out'])
    if method=='virtual_ctrl_a':
     protocol.send('Input.dispatchKeyEvent',{'type':'keyDown','key':'a','code':'KeyA','windowsVirtualKeyCode':65,'modifiers':2});protocol.send('Input.dispatchKeyEvent',{'type':'keyUp','key':'a','code':'KeyA','windowsVirtualKeyCode':65,'modifiers':0})
    elif method=='dom_range':node.evaluate('node=>node.setSelectionRange(0,node.value.length)')
    else:node.evaluate('node=>node.select()')
    time.sleep(.1);selected=subprocess.check_output(['xclip','-selection','primary','-out'])
    protocol.send('Input.insertText',{'text':new});time.sleep(.1);after=subprocess.check_output(['xclip','-selection','primary','-out'])
    rows.append({'method':method,'before_marker':before==b'primary-fixture-marker','selected_unchanged':selected==before,'selected_old_secret':selected==old.encode(),'selected_bytes':len(selected),'after_old_secret':after==old.encode(),'after_new_secret':after==new.encode(),'after_bytes':len(after),'value_matches_new':node.evaluate('(node,value)=>node.value===value',new)})
   finally:
    if owner.poll() is None:owner.terminate()
    owner.wait(timeout=3)
 finally:context.close()
print(json.dumps(rows,indent=2))
