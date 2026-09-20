"""Read-only session lock hints; unavailable providers never mean unlocked."""
import json
from pathlib import Path
from .common import DesktopError, run


def summarize(providers):
    locked=[p for p in providers if p.get('kind')=='lock_hint' and p.get('active') is True]
    savers=[p for p in providers if p.get('kind')=='screensaver' and p.get('active') is True]
    known=[p for p in providers if isinstance(p.get('active'),bool)]
    return {'state':'locked' if locked else 'screensaver_active' if savers else 'inactive' if known else 'unknown',
            'input_ready':False if locked or savers else None,
            'providers':providers,
            'verification':'Reported desktop-service hints only; inactive or unavailable providers do not prove the display is unlocked.'}


def session_state():
    try:
        raw=run(['/usr/bin/python3',str(Path(__file__).with_name('_session_state.py'))],timeout=3,max_output_bytes=16384)
        providers=json.loads(raw)
        if not isinstance(providers,list) or any(not isinstance(p,dict) for p in providers):raise ValueError()
        return summarize(providers)
    except DesktopError as exc:
        if exc.code in ('CANCELLED','TIMEOUT'):raise
        return summarize([{'provider':'query','available':False,'reason':exc.code}])
    except (ValueError,TypeError):
        return summarize([{'provider':'query','available':False,'reason':'invalid_response'}])


def require_session_input():
    """Sample registered lock hints before a mutation, never wake or unlock."""
    state = session_state()
    if state['input_ready'] is False:
        raise DesktopError('SESSION_BLOCKED',
            'The desktop reports a lock or active screensaver. Resume the intended desktop through the human viewer, then observe again. No input sent.',
            details={'session_state':state['state']})
