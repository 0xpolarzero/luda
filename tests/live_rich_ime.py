"""Native GTK simple composition in an owned ProseMirror document."""
import argparse
from rich_editor_probe import Readback, Refused


def exercise(page, desktop, browser_pid, wid, load, focus, persisted, record):
    def actual():
        return page.evaluate('({snapshot:window.ludaRichProbe.snapshot(),monitor:window.__ludaRichComposition})')
    for intent in ('commit', 'cancel'):
        load('prosemirror');desktop.activate(wid);focus()
        reader=Readback(page,desktop,browser_pid,wid,True)
        reader.before_input();desktop.paste(wid,'BASE','ctrl_v');reader.dispose()
        reader=Readback(page,desktop,browser_pid,wid,True)
        reader.before_input();desktop.key(wid,'ctrl+shift+u')
        for key in ('3','0','6','b'):desktop.key(wid,key)
        page.wait_for_timeout(150)
        before=actual()
        try:
            reader.before_input()
            refused=None
        except Refused as exc:refused=str(exc)
        after=actual()
        preserved=all(before['snapshot'][k]==after['snapshot'][k] for k in ('model','html','revision','selection'))
        trusted=any(e['type']=='compositionstart' and e['trusted'] for e in before['snapshot']['events'])
        record('native-ime-'+intent+'-pending-refused',before['monitor']['active'] and trusted and refused=='COMPOSITION_PENDING' and preserved,
               before=before,after=after,refused=refused,conflicting_input_attempts=0,model_and_preedit_preserved=preserved)
        # A separate explicit user intent, not a retry of the refused operation.
        desktop.key(wid,'Return' if intent=='commit' else 'Escape')
        page.wait_for_timeout(150)
        completed=actual();saved=persisted(completed['snapshot'])
        expected='BASEに' if intent=='commit' else 'BASE'
        record('native-ime-explicit-'+intent+'-model',completed['snapshot']['modelText']==expected and saved.get('model')==completed['snapshot']['model'],
               actual=completed,persisted=saved,expected=expected)
        record('native-ime-explicit-'+intent+'-monitor-recovery',not completed['monitor']['active'] and completed['monitor']['trustedEnds']>0,actual=completed['monitor'])
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
