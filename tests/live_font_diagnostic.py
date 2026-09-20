"""Real Pango helper with normal and deliberately restricted private fallback."""
import json
import os
from pathlib import Path
import shutil
import tempfile
from xml.sax.saxutils import escape
from luda.fonts import font_coverage

ROOT=Path(__file__).resolve().parents[1]

def main():
    complete=font_coverage();assert complete['status']=='covered',complete
    original=dict(os.environ)
    with tempfile.TemporaryDirectory(prefix='luda-font-probe-') as directory:
        base=Path(directory);fonts=base/'fonts';fonts.mkdir();cache=base/'cache';cache.mkdir()
        shutil.copyfile('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',fonts/'fallback.ttf')
        config=base/'fonts.conf'
        config.write_text('<fontconfig><dir>'+escape(str(fonts))+'</dir><cachedir>'+escape(str(cache))+'</cachedir></fontconfig>')
        restricted=dict(os.environ,FONTCONFIG_FILE=str(config),FONTCONFIG_PATH=str(base),XDG_CACHE_HOME=str(cache))
        partial=font_coverage(restricted)
        assert partial['status']=='partial' and not partial['blocks_input'],partial
        assert 'Japanese' in partial['missing_samples'] and 'Emoji ZWJ and skin tone' in partial['missing_samples']
        combining=next(row for row in partial['samples'] if row['sample']=='Combining marks')
        assert combining['unknown_glyphs']==0
    assert dict(os.environ)==original,'Diagnostic changed caller font configuration'
    output=ROOT/'artifacts/font-diagnostic';output.mkdir(parents=True,exist_ok=True)
    evidence={'uid':os.getuid(),'complete':complete,'restricted_private_font_config':partial,'caller_environment_unchanged':True}
    (output/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence))

if __name__=='__main__':main()
