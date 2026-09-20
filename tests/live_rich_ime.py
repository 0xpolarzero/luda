"""Native GTK simple composition in an owned browser, before application handlers."""
import argparse
from rich_editor_probe import Readback, Refused


def exercise(page, desktop, browser_pid, wid, load, focus, persisted, record, button):
    def actual():
        return page.evaluate('({snapshot:window.ludaRichProbe.snapshot(),monitor:window.__ludaRichComposition})')
    def guard(reader):
        try:
            reader.before_input()
            return None
        except Refused as exc:
            return str(exc)
    def unchanged(before, after):
        return all(before['snapshot'][k]==after['snapshot'][k]
                   for k in ('model','html','fieldValue','revision','selection'))
    for mode in ('prosemirror', 'generic-prewrap', 'textarea'):
        for intent in ('commit', 'cancel'):
            load(mode);desktop.activate(wid);focus()
            reader=Readback(page,desktop,browser_pid,wid,True)
            reader.before_input();desktop.paste(wid,'BASE','ctrl_v');reader.dispose()
            reader=Readback(page,desktop,browser_pid,wid,True)
            reader.before_input();desktop.key(wid,'ctrl+shift+u')
            for key in ('3','0','6','b'):desktop.key(wid,key)
            page.wait_for_timeout(150)
            before=actual();refused=guard(reader);after=actual()
            preserved=unchanged(before,after)
            trusted=any(e['type']=='compositionstart' and e['trusted'] for e in before['monitor']['events'])
            prefix=mode+'-native-ime-'+intent
            record(prefix+'-pending-refused',before['monitor']['active'] and trusted and refused=='COMPOSITION_PENDING' and preserved,
                   before=before,after=after,refused=refused,conflicting_input_attempts=0,model_and_preedit_preserved=preserved)
            # Separate explicit user intent, never a retry of the refused route.
            desktop.key(wid,'Return' if intent=='commit' else 'Escape')
            page.wait_for_timeout(150)
            completed=actual();saved=persisted(completed['snapshot'])
            expected='BASEに' if intent=='commit' else 'BASE'
            key='modelText' if mode=='prosemirror' else 'fieldValue' if mode=='textarea' else 'renderedText'
            record(prefix+'-value',completed['snapshot'][key]==expected and saved.get(key)==expected,
                   actual=completed,persisted=saved,expected=expected)
            record(prefix+'-monitor-recovery',not completed['monitor']['active'] and completed['monitor']['trustedEnds']>0,
                   actual=completed['monitor'])
            reader.dispose()
    # The app schedules an untrusted end event after the next native start.
    # Arming happens before editor focus/preedit; no focus-changing action is
    # sent once composition is pending.
    load('prosemirror');desktop.activate(wid)
    button('Arm synthetic end during next composition');focus()
    reader=Readback(page,desktop,browser_pid,wid,True)
    reader.before_input();desktop.paste(wid,'BASE','ctrl_v');reader.dispose()
    reader=Readback(page,desktop,browser_pid,wid,True);reader.before_input()
    desktop.key(wid,'ctrl+shift+u')
    for key in ('3','0','6','b'):desktop.key(wid,key)
    before=actual();page.wait_for_timeout(1700);spoofed=actual()
    refused=guard(reader);after=actual()
    record('synthetic-end-during-native-preedit-refused',before['monitor']['active'] and spoofed['monitor']['active'] and spoofed['monitor']['ignored']>0 and refused=='COMPOSITION_PENDING' and unchanged(spoofed,after),
           before=before,spoofed=spoofed,after=after,refused=refused,conflicting_input_attempts=0)
    desktop.key(wid,'Escape');page.wait_for_timeout(150)
    record('synthetic-end-probe-explicit-cancel-value',actual()['snapshot']['modelText']=='BASE',actual=actual())
    reader.dispose()
    load('prosemirror');desktop.activate(wid);focus()
    try:
        reader=Readback(page,desktop,browser_pid,wid,False)
        reader.dispose();refused=None
    except Refused as exc:refused=str(exc)
    record('native-monitor-unknown-provenance',refused=='COMPOSITION_UNKNOWN',refused=refused,input_attempts=0)


if __name__=='__main__':
    from live_rich_editor import main
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True)
    raise SystemExit(main(parser.parse_args().executable,native_composition_only=True))
