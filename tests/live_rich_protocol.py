"""Owned browser-native Input.insertText, distinct from clipboard and DOM setters."""
import argparse
from rich_editor_probe import Readback


def exercise(page, desktop, browser_pid, wid, load, focus, persisted, record, button):
    from live_rich_editor import SAMPLES
    protocol=page.context.new_cdp_session(page)
    def reader():return Readback(page,desktop,browser_pid,wid,True)
    def run(mode,name,payload,bold=False):
        load(mode);desktop.activate(wid);focus()
        if bold:
            r=reader();r.before_input();desktop.key(wid,'ctrl+b');r.dispose()
        expected='';steps=[];matched=True
        for index,part in enumerate(payload.split('\n')):
            if index:
                r=reader();r.before_input();desktop.key(wid,'Return');r.dispose()
                expected+='\n';page.wait_for_timeout(60)
                r=reader();actual=r.read();r.dispose()
                matched=actual['logicalText']==expected
                steps.append({'input':'native-Return','exact':matched,'actual':actual})
                if not matched:break
            if part:
                r=reader();r.before_input()
                protocol.send('Input.insertText',{'text':part});r.dispose()
                expected+=part;page.wait_for_timeout(60)
                r=reader();actual=r.read();r.dispose()
                matched=actual['logicalText']==expected
                steps.append({'input':'browser-native-Input.insertText','exact':matched,'actual':actual})
                if not matched:break
        r=reader();actual=r.read();r.dispose();saved=persisted(actual)
        exact=matched and actual['logicalText']==payload
        paragraphs=actual['model'].get('content',[]) if actual['model'] else []
        structure=(len(paragraphs)==len(payload.split('\n')) and all(p['type']=='paragraph' for p in paragraphs)) if mode=='prosemirror' else True
        nodes=[n for p in paragraphs for n in p.get('content',[]) if n['type']=='text']
        strong=bool(nodes) and all(any(m['type']=='strong' for m in n.get('marks',[])) for n in nodes)
        oracle=all(saved.get(k)==actual[k] for k in ('documentId','generation','revision','html','model','fieldValue'))
        record('protocol-'+mode+'-'+name,exact and structure and oracle and (not bold or strong),
               payload=payload,route='browser-native-Input.insertText-plus-native-paragraph-Return',
               exact=exact,structure=structure,all_text_strong=strong,expected_bold=bold,
               steps=steps,actual=actual,persisted=saved,automatic_retry=False)
    for name,payload in SAMPLES:
        if name!='crlf':run('prosemirror',name,payload)
    run('prosemirror','stored-bold-single-line','Bold 日本語 👩🏽‍💻',True)
    run('prosemirror','stored-bold-paragraphs','Bold 日本語\nsecond 👩🏽‍💻\n',True)
    for mode in ('textarea','generic-prewrap'):
        run(mode,'mixed-trailing-lines','alpha\n\t日本語 👩🏽‍💻 é\n\n')
    protocol.detach()


if __name__=='__main__':
    from live_rich_editor import main
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True)
    raise SystemExit(main(parser.parse_args().executable,native_composition_only='protocol'))
