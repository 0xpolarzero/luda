"""Characterize real Mousepad semantic replacement undo using saved-byte oracles."""
import json
import os
from pathlib import Path
import tempfile
import time
import live_file_workflows as files

ROOT=Path(__file__).resolve().parents[1]

def main():
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':
        raise RuntimeError('Ordinary UID and isolated display required')
    out=ROOT/'artifacts/undo';out.mkdir(parents=True,exist_ok=True)
    files.OUT=out
    records=[]
    with tempfile.TemporaryDirectory(prefix='luda-undo-') as directory:
        path=Path(directory)/'document.txt'
        original='Original 日本語\nSecond line\n'
        replacement='Replacement שלום 👩🏽‍💻\n\tFinal line\n'
        path.write_text(original)
        editor=files.Editor(path)
        try:
            def field():
                return files.until(lambda:next((n for n in editor.nodes(editor.wid) if 'EditableText' in n['interfaces'] and 'multi-line' in n['states']),None))
            node=field()
            result=files.d.type_text(node['element_id'],replacement,mode='replace')
            assert result['effect']=='verified',result
            files.d.element(field()['element_id'],'focus')
            files.d.key(editor.wid,'ctrl+s')
            files.until(lambda:path.read_text()==replacement)
            records.append({'action':'semantic-replace-and-save','stored':path.read_text()})
            # Save provides an independent file oracle for each observed state;
            # no fixed undo grouping is assumed across editor/provider versions.
            for chord in ('ctrl+z','ctrl+z','ctrl+shift+z','ctrl+shift+z'):
                files.d.key(editor.wid,chord)
                time.sleep(.15)
                observed=files.d.element(field()['element_id'],'read')['text']
                files.d.key(editor.wid,'ctrl+s')
                files.until(lambda:path.read_text()==observed)
                records.append({'action':chord,'stored':path.read_text(),'public_read_matches_file':True})
            assert records[-1]['stored']==replacement,records
        finally:
            editor.cleanup();files.d.close()
    evidence={'uid':os.getuid(),'trace':records,'original':original,'replacement':replacement,
              'first_undo_restores_original':records[1]['stored']==original,
              'second_undo_restores_original':records[2]['stored']==original}
    (out/'results.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(evidence,ensure_ascii=False))

if __name__=='__main__':main()
