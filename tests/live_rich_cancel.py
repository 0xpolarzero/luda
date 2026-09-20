"""Explicit native IME cancel candidate; no automatic recovery or text inference."""
import argparse
from rich_editor_probe import Refused
from rich_cancel_probe import CancelReadback


def exercise(page, desktop, browser_pid, wid, load, focus, persisted, record, button):
    def actual():return page.evaluate('({snapshot:window.ludaRichProbe.snapshot(),monitor:window.__ludaRichComposition})')
    def new():
        load('prosemirror');desktop.activate(wid);focus()
        reader=CancelReadback(page,desktop,browser_pid,wid,True)
        reader.before_input();desktop.paste(wid,'BASE','ctrl_v');reader.dispose()
        return CancelReadback(page,desktop,browser_pid,wid,True)
    def start():
        desktop.key(wid,'ctrl+shift+u')
        for key in ('3','0','6','b'):desktop.key(wid,key)
        page.wait_for_timeout(100)
    def result(fn):
        try:return {'value':fn()}
        except Refused as exc:return {'refused':str(exc)}
    reader=new();start();before=actual();ticket=reader.arm_cancel()
    desktop.key(wid,'Escape');page.wait_for_timeout(100)
    recovered=result(lambda:reader.finish_cancel(ticket));after=actual()
    record('explicit-native-cancel-correlated', 'value' in recovered and after['snapshot']['modelText']=='BASE',before=before,after=after,response=recovered)
    if 'value' in recovered:
        replay=result(lambda:reader.finish_cancel(ticket))
        record('cancel-correlation-consumed-once',replay.get('refused')=='CANCEL_UNCONFIRMED',response=replay)
        reader.dispose();reader=CancelReadback(page,desktop,browser_pid,wid,True)
        reader.before_input();desktop.paste(wid,'RESUMED','ctrl_v');page.wait_for_timeout(100)
        after=actual();saved=persisted(after['snapshot'])
        record('explicit-cancel-then-native-resume',after['snapshot']['modelText']=='BASERESUMED' and saved.get('model')==after['snapshot']['model'],actual=after,persisted=saved)
    reader.dispose()
    reader=new();before=actual();reply=result(reader.arm_cancel);after=actual()
    record('cancel-without-active-refused',reply.get('refused')=='NO_COMPOSITION_ACTIVE' and before['snapshot']==after['snapshot'],response=reply,input_attempts=0)
    reader.dispose()
    reader=new();start();ticket=reader.arm_cancel()
    # No Escape was dispatched: absence of an event must not prove cancellation.
    page.wait_for_timeout(1600);reply=result(lambda:reader.finish_cancel(ticket));after=actual()
    record('missing-escape-events-refused',reply.get('refused')=='CANCEL_UNCONFIRMED' and after['monitor']['active'],response=reply,actual=after)
    desktop.key(wid,'Escape');reader.dispose()
    for key in ('3', 'a', 'shift+a'):
        reader=new();start();before=actual();ticket=reader.arm_cancel()
        desktop.key(wid,key);page.wait_for_timeout(100)
        reply=result(lambda:reader.finish_cancel(ticket));after=actual()
        record('unrelated-native-key-'+key+'-cannot-recover',reply.get('refused')=='CANCEL_UNCONFIRMED' and after['monitor']['active'],before=before,response=reply,actual=after)
        desktop.key(wid,'Escape');reader.dispose()
    load('prosemirror');desktop.activate(wid)
    button('Arm synthetic Escape during next composition');focus()
    reader=CancelReadback(page,desktop,browser_pid,wid,True)
    reader.before_input();desktop.paste(wid,'BASE','ctrl_v');reader.dispose()
    reader=CancelReadback(page,desktop,browser_pid,wid,True);start();ticket=reader.arm_cancel();before=actual()
    page.wait_for_timeout(1100);reply=result(lambda:reader.finish_cancel(ticket));after=actual()
    fake=any(e['type']=='keyup' and e['code']=='Escape' and not e['trusted'] for e in after['monitor']['events'])
    record('synthetic-escape-cannot-recover',before['monitor']['pending'] and fake and reply.get('refused')=='CANCEL_UNCONFIRMED' and after['monitor']['active'] and before['snapshot']['model']==after['snapshot']['model'],before=before,response=reply,actual=after)
    desktop.key(wid,'Escape');reader.dispose()
    reader=new();start();ticket=reader.arm_cancel();desktop.key(wid,'Escape')
    tree=desktop.inspect(wid,limit=150,name='Replace editor node')
    targets=[n for n in tree['nodes'] if n['name']=='Replace editor node' and n['role']=='push button']
    if len(targets)!=1:raise RuntimeError('Focus target not unique')
    desktop.element(targets[0]['element_id'],'focus')
    page.wait_for_function("document.activeElement.id === 'replace'")
    focus_observed=page.evaluate('document.activeElement.id')
    reply=result(lambda:reader.finish_cancel(ticket))
    record('focus-change-invalidates-recovery',reply.get('refused')=='FOCUS_CHANGED',response=reply,focused_element=focus_observed)
    focus();reply=result(lambda:reader.finish_cancel(ticket))
    record('refocus-does-not-revive-cancel-ticket',reply.get('refused')=='CANCEL_UNCONFIRMED',response=reply)
    reader.dispose()
    reader=new();start();ticket=reader.arm_cancel();desktop.key(wid,'Escape');button('Reload document');page.wait_for_timeout(200)
    reply=result(lambda:reader.finish_cancel(ticket))
    record('navigation-invalidates-recovery',reply.get('refused')=='DOCUMENT_CHANGED',response=reply)
    reader.dispose()
    reader=new();start();ticket=reader.arm_cancel();desktop.key(wid,'Escape');start()
    reply=result(lambda:reader.finish_cancel(ticket));after=actual()
    record('new-composition-invalidates-cancel-ticket',reply.get('refused')=='CANCEL_UNCONFIRMED' and after['monitor']['generation']>ticket['generation'] and after['monitor']['active'],response=reply,ticket=ticket,actual=after)
    desktop.key(wid,'Escape');reader.dispose()
    # Separate explicit request after native commit: the conservative monitor
    # is stale-active. Escape may affect application UI; only postdispatch
    # uncertainty can be reported, never a no-effect preflight claim.
    reader=new();start();desktop.key(wid,'Return');page.wait_for_timeout(150)
    before=actual();ticket=reader.arm_cancel();desktop.key(wid,'Escape');page.wait_for_timeout(100)
    reply=result(lambda:reader.finish_cancel(ticket));after=actual()
    record('stale-active-after-commit-cancel-unconfirmed',before['snapshot']['modelText']=='BASEに' and before['monitor']['active'] and reply.get('refused')=='CANCEL_UNCONFIRMED',
           kind='unsupported-recovery-diagnostic',workflow_verified=False,response=reply,effect='uncertain',possible_application_effect=True,
           before=before,after=after,cancel_input_attempts=1,automatic_retry=False)
    reader.dispose()
    # A genuinely unmonitored fresh browser context, not just an unknown flag
    # on a realm that was monitored from birth.
    context=page.context.browser.new_context(viewport={'width':1000,'height':760})
    unmonitored=context.new_page();unmonitored.goto(page.url)
    unmonitored.wait_for_function('window.ludaRichProbe !== undefined');page.close()
    unmonitored.wait_for_timeout(200)
    windows=[w for w in desktop.list_windows() if w['pid']==browser_pid]
    if len(windows)!=1:raise RuntimeError('Unmonitored native window not unique')
    new_wid=windows[0]['window_id'];desktop.activate(new_wid)
    tree=desktop.inspect(new_wid,limit=150,name='Observed rich editor')
    fields=[n for n in tree['nodes'] if n['name']=='Observed rich editor' and n['role'] in ('entry','text')]
    if len(fields)!=1:raise RuntimeError('Unmonitored editor AX not unique')
    desktop.element(fields[0]['element_id'],'focus');desktop.key(new_wid,'ctrl+shift+u')
    for key in ('3','0','6','b'):desktop.key(new_wid,key)
    before=unmonitored.evaluate('window.ludaRichProbe.snapshot()')
    reply=result(lambda:CancelReadback(unmonitored,desktop,browser_pid,new_wid,False))
    after=unmonitored.evaluate('window.ludaRichProbe.snapshot()')
    record('actual-unmonitored-late-attach-refused',reply.get('refused')=='COMPOSITION_UNKNOWN' and before['model']==after['model'],response=reply,before=before,after=after,cancel_input_attempts=0)
    desktop.key(new_wid,'Escape');context.close()


if __name__=='__main__':
    from live_rich_editor import main
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True)
    raise SystemExit(main(parser.parse_args().executable,native_composition_only='cancel'))
