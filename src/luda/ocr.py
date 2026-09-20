"""Optional local OCR over bounded, explicitly retained screenshot bytes."""
import math
import os
import re
import shutil
from .common import DesktopError, run

MAX_CACHE_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 2560 * 2560
HEADER = 'level page_num block_num par_num line_num word_num left top width height conf text'.split()
LANGUAGE = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,31}(?:/[A-Za-z][A-Za-z0-9_]{0,31})?\Z')


def retain_snapshot(snapshots, token, snapshot):
    if len(snapshot.get('png', b'')) > MAX_CACHE_BYTES:
        snapshot.pop('png', None)
    snapshots[token] = snapshot
    while len(snapshots) > 16 or sum(len(item.get('png', b'')) for item in snapshots.values()) > MAX_CACHE_BYTES:
        snapshots.pop(next(iter(snapshots)))


def parse_tsv(raw, width, height, limit):
    try:
        lines = raw.decode('utf-8').splitlines()
        if not lines or lines[0].split('\t') != HEADER or len(lines) > 20001:
            raise ValueError()
        candidates = []
        count = 0
        for line in lines[1:]:
            fields = line.split('\t', 11)
            if len(fields) != 12:
                raise ValueError()
            level, page, block, paragraph, row, word, x, y, w, h = map(int, fields[:10])
            confidence = float(fields[10])
            if (not 1 <= level <= 5 or page != 1 or min(block, paragraph, row, word, x, y, w, h) < 0
                    or x+w > width or y+h > height or not math.isfinite(confidence)
                    or not -1 <= confidence <= 100):
                raise ValueError()
            if level != 5 or not fields[11].strip():
                continue
            if confidence < 0 or w == 0 or h == 0 or len(fields[11]) > 2048:
                raise ValueError()
            count += 1
            if len(candidates) < limit:
                candidates.append({'text': fields[11], 'image_bounds': {'x': x, 'y': y, 'width': w, 'height': h},
                                   'engine_confidence': confidence})
        return {'candidates': candidates, 'truncated': count > limit}
    except (ValueError, UnicodeError, OverflowError) as exc:
        raise DesktopError('OCR_INVALID_OUTPUT', 'Local OCR returned malformed or out-of-bounds candidates; no candidates returned.') from exc


def recognize(png, image, language, limit, environment):
    if not isinstance(language, str) or not LANGUAGE.fullmatch(language) or type(limit) is not int or not 1 <= limit <= 1000:
        raise DesktopError('INVALID_ARGUMENT', 'Choose one installed OCR language and a candidate limit of 1–1000.')
    width, height = image
    if not isinstance(png, bytes) or len(png) > MAX_CACHE_BYTES or width <= 0 or height <= 0 or width*height > MAX_PIXELS:
        raise DesktopError('OCR_LIMIT', 'Screenshot exceeds local OCR byte or pixel limits.')
    executable = shutil.which('tesseract', path=environment.get('PATH', os.defpath))
    if executable is None:
        raise DesktopError('OCR_UNAVAILABLE', 'Optional local Tesseract is not installed; other desktop tools remain available.')
    try:
        raw = run([executable, '--list-langs'], timeout=2, max_output_bytes=16384)
        languages = [line.strip() for line in raw.decode('utf-8').splitlines() if LANGUAGE.fullmatch(line.strip())]
        if len(languages) > 256:
            raise DesktopError('OCR_LIMIT', 'Local OCR language inventory exceeds its bounded limit.')
        if language not in languages:
            raise DesktopError('OCR_LANGUAGE_UNAVAILABLE', 'Requested local OCR language is not installed.', details={'available_languages': languages})
        raw = run([executable, 'stdin', 'stdout', '-l', language, '--psm', '11', 'tsv'], data=png, timeout=5, max_output_bytes=1048576)
    except UnicodeError as exc:
        raise DesktopError('OCR_INVALID_OUTPUT', 'Local OCR language inventory is malformed.') from exc
    except DesktopError as exc:
        if exc.code in ('BACKEND_ERROR', 'DEPENDENCY_MISSING'):
            raise DesktopError('OCR_UNAVAILABLE', 'Local OCR engine could not process this screenshot; no candidates returned.') from exc
        raise
    return parse_tsv(raw, width, height, limit)
