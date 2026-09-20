"""Advisory glyph coverage; never a desktop readiness or input gate."""
from contextlib import nullcontext
import errno
import json
from pathlib import Path
import re

from ._font_probe import SAMPLES
from .common import DesktopError, environment_scope, run

SCOPE = 'Fixed sample glyph coverage only; not universal Unicode coverage, typography, or application-specific font validation.'


def unavailable(code):
    return {'available': False, 'status': 'unavailable', 'code': code,
            'scope': SCOPE, 'blocks_input': False,
            'next_step': 'Check system Python/Pango dependencies and account resources. Font coverage was not established; other available desktop capabilities are not blocked by this diagnostic.'}


def font_coverage(environment=None):
    try:
        with environment_scope(environment) if environment is not None else nullcontext():
            raw = run(['/usr/bin/python3', str(Path(__file__).with_name('_font_probe.py'))],
                      timeout=3, max_output_bytes=8192)
    except DesktopError as exc:
        if exc.code == 'CANCELLED':
            raise
        return unavailable('FONT_PROVIDER_UNAVAILABLE' if exc.code == 'BACKEND_ERROR' else exc.code)
    except MemoryError:
        return unavailable('RESOURCE_UNAVAILABLE')
    except OSError as exc:
        return unavailable('RESOURCE_UNAVAILABLE' if exc.errno in (errno.ENOMEM, errno.EMFILE, errno.ENFILE, errno.EAGAIN) else 'FONT_PROVIDER_UNAVAILABLE')
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        if set(result) == {'error'} and result['error'] in ('DEPENDENCY_MISSING', 'RESOURCE_UNAVAILABLE', 'FONT_PROVIDER_UNAVAILABLE'):
            return unavailable(result['error'])
        if set(result) != {'samples', 'pango_version'} or not isinstance(result['pango_version'], str) or not re.fullmatch(r'\d{1,3}\.\d{1,3}\.\d{1,3}', result['pango_version']):
            raise ValueError()
        rows = result['samples']
        if not isinstance(rows, list) or len(rows) != len(SAMPLES):
            raise ValueError()
        for row, (name, _, _) in zip(rows, SAMPLES):
            if not isinstance(row, dict) or set(row) != {'sample', 'unknown_glyphs'} or row['sample'] != name or type(row['unknown_glyphs']) is not int or not 0 <= row['unknown_glyphs'] <= 128:
                raise ValueError()
    except (ValueError, TypeError, KeyError):
        return unavailable('FONT_PROVIDER_UNAVAILABLE')
    missing = [row['sample'] for row in rows if row['unknown_glyphs']]
    return {'available': True, 'status': 'partial' if missing else 'covered',
            'pango_version': result['pango_version'], 'samples': rows,
            'missing_samples': missing, 'scope': SCOPE, 'blocks_input': False,
            'next_step': 'Install the documented Noto fallback packages and reopen affected apps; verify exact text semantically when screenshots contain missing-glyph boxes.' if missing else 'These samples have glyphs; verify the actual application when font rendering matters.'}
