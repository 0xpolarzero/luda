"""Independent Pango default-font coverage and Cairo rendering oracle."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import cairo
import gi
gi.require_version('Pango','1.0')
gi.require_version('PangoCairo','1.0')
from gi.repository import Pango,PangoCairo

SAMPLES=[('Japanese','ja','日本語の表示'),('Simplified Chinese','zh-cn','简体中文显示'),('Traditional Chinese','zh-tw','繁體中文顯示'),('Korean','ko','한글 표시'),('Emoji ZWJ and skin tone','en','👩🏽\u200d💻 👨\u200d👩\u200d👧\u200d👦'),('Combining marks','en','e\u0301 a\u0308 o\u0302'),('Arabic','ar','السلام عليكم'),('Devanagari','hi','नमस्ते दुनिया')]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New evidence directory; existing output is refused.')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    fontmap=PangoCairo.FontMap.new();context=fontmap.create_context()
    surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,1000,80*len(SAMPLES))
    drawing=cairo.Context(surface);drawing.set_source_rgb(1,1,1);drawing.paint()
    rows=[]
    for index,(name,language,text) in enumerate(SAMPLES):
        context.set_language(Pango.Language.from_string(language))
        layout=Pango.Layout.new(context)
        layout.set_font_description(Pango.FontDescription('Sans 24'))
        layout.set_text(text,-1)
        unknown=layout.get_unknown_glyphs_count();width,height=layout.get_pixel_size()
        rows.append({'sample':name,'language':language,'text':text,'unknown_glyphs':unknown,'pixel_size':[width,height],'coverage_verified':unknown==0 and width>0 and height>0})
        drawing.move_to(20,index*80+8);drawing.set_source_rgb(0,0,0);PangoCairo.show_layout(drawing,layout)
    additional=[]
    for label,text in [('Thai','ภาษาไทย'),('Tamil','தமிழ்'),('Bengali','বাংলা'),('Hebrew','עברית'),('Ethiopic','አማርኛ'),('U+105C0','\U000105c0'),('U+1E4D0','\U0001e4d0'),('U+31350','\U00031350')]:
        context.set_language(Pango.Language.from_string('en'))
        layout=Pango.Layout.new(context);layout.set_font_description(Pango.FontDescription('Sans 24'));layout.set_text(text,-1)
        additional.append({'sample':label,'text':text,'unknown_glyphs':layout.get_unknown_glyphs_count(),'required_for_basic_coverage':False})
    surface.write_to_png(str(args.output/'rendered.png'))
    packages=subprocess.run(['dpkg-query','-W','-f=${Package} ${Version}\n','fonts-noto-core','fonts-noto-cjk','fonts-noto-color-emoji'],capture_output=True,text=True,timeout=3)
    result={'uid':os.getuid(),'architecture':platform.machine(),'pango':Pango.version_string(),'cairo':cairo.cairo_version_string(),'font_packages':packages.stdout.splitlines(),'font_family_requested':'Sans; automatic system fallback, no custom font configuration','qualified':all(r['coverage_verified'] for r in rows),'scope':'Glyph coverage for these samples only; no claim of universal script coverage or typographic correctness.','samples':rows,'additional_probes':additional}
    (args.output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['qualified'] else 1

if __name__=='__main__':sys.exit(main())
