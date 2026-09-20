"""Fixed-sample Pango coverage in a short-lived system-Python process."""
import errno
import json

SAMPLES = (
    ('Japanese', 'ja', '日本語の表示'),
    ('Simplified Chinese', 'zh-cn', '简体中文显示'),
    ('Traditional Chinese', 'zh-tw', '繁體中文顯示'),
    ('Korean', 'ko', '한글 표시'),
    ('Emoji ZWJ and skin tone', 'en', '👩🏽\u200d💻 👨\u200d👩\u200d👧\u200d👦'),
    ('Combining marks', 'en', 'e\u0301 a\u0308 o\u0302'),
    ('Arabic', 'ar', 'السلام عليكم'),
    ('Devanagari', 'hi', 'नमस्ते दुनिया'),
)


def probe():
    try:
        import gi
        gi.require_version('Pango', '1.0')
        gi.require_version('PangoCairo', '1.0')
        from gi.repository import Pango, PangoCairo
    except (ImportError, ValueError):
        return {'error': 'DEPENDENCY_MISSING'}
    # PangoCairo supplies the default font map; no drawing surface, screenshot,
    # image, application text, user-supplied sample, or persistent file is used.
    fontmap = PangoCairo.FontMap.new()
    context = fontmap.create_context()
    rows = []
    for name, language, text in SAMPLES:
        context.set_language(Pango.Language.from_string(language))
        layout = Pango.Layout.new(context)
        layout.set_font_description(Pango.FontDescription('Sans 24'))
        layout.set_text(text, -1)
        rows.append({'sample': name, 'unknown_glyphs': layout.get_unknown_glyphs_count()})
    return {'pango_version': Pango.version_string(), 'samples': rows}


def main():
    try:
        result = probe()
    except (MemoryError, OSError) as exc:
        resource = isinstance(exc, MemoryError) or exc.errno in (errno.ENOMEM, errno.EMFILE, errno.ENFILE, errno.EAGAIN)
        result = {'error': 'RESOURCE_UNAVAILABLE' if resource else 'FONT_PROVIDER_UNAVAILABLE'}
    except Exception:
        result = {'error': 'FONT_PROVIDER_UNAVAILABLE'}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
