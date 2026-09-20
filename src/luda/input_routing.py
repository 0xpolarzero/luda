"""Choose the compatible input path without changing the public tool contract."""
import json
from pathlib import Path
from .common import DesktopError, checkpoint, run


def prefers_private_input(window):
    """Use independent input only for the positively identified GTK3 provider.

    Other providers keep the working foreground input path. This bounded query
    does not focus, launch, or mutate the application. Callers may cache positive
    results for the exact window/process generation, never for a bare PID.
    """
    pid, start = window.get('pid'), window.get('start')
    if (type(pid) is not int or pid <= 0 or not isinstance(start, str)
            or not start.isdecimal() or len(start) > 64):
        return False
    try:
        raw = run(['/usr/bin/python3', str(Path(__file__).with_name('ax_worker.py'))],
                  data=json.dumps({'op': 'toolkit', 'pid': pid, 'start': start}).encode(),
                  timeout=.8, max_output_bytes=4096)
        reply = json.loads(raw)
    except DesktopError as exc:
        if exc.code == 'CANCELLED':
            raise
        # A local provider timeout may use the compatible route. An exhausted
        # action deadline must still stop the action rather than dispatch input.
        checkpoint()
        return False
    except (ValueError, TypeError):
        return False
    if not isinstance(reply, dict) or 'error' in reply:
        return False
    toolkit, version = reply.get('toolkit'), reply.get('toolkit_version')
    return (isinstance(toolkit, str) and toolkit.casefold() == 'gtk'
            and isinstance(version, str) and version.split('.', 1)[0] == '3')
