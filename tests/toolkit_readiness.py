"""Read-only startup precondition; never retries a toolkit mutation."""
import time
from luda.common import DesktopError


def wait_for_accessibility(inspect, *, timeout=4, clock=time.monotonic, sleep=time.sleep, evidence=None):
    evidence = evidence if evidence is not None else []
    began = clock()
    while True:
        try:
            tree = inspect()
            if tree.get('available') and any(node.get('name') == 'Toolkit text' for node in tree.get('nodes', [])):
                evidence.append({'elapsed': round(clock() - began, 3), 'ready': True})
                return tree
            error = DesktopError('ACCESSIBILITY_UNAVAILABLE', 'Toolkit editor is not yet exposed by accessibility.')
        except DesktopError as exc:
            if exc.code != 'ACCESSIBILITY_UNAVAILABLE':
                raise
            error = exc
        evidence.append({'elapsed': round(clock() - began, 3), 'ready': False, 'code': error.code})
        if clock() - began >= timeout:
            raise error
        sleep(min(.1, max(0, timeout - (clock() - began))))
