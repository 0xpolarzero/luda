"""Bounded X11 metadata reads isolated from the tool server's process.

No display connection survives a request. A dead or restarted X server cannot
terminate this process through Xlib's fatal I/O handler.
"""
import json
import sys
from .common import DesktopError, run


class X11:
    def __init__(self):
        # Preserve eager availability checking without retaining an Xlib handle.
        self._read('root')

    def _read(self, method, argument=None):
        try:
            raw = run([sys.executable, '-m', 'luda._x11_helper'],
                      data=json.dumps({'method':method,'argument':argument}).encode(), timeout=2,
                      effect='uncertain' if method=='restack_above' else 'none')
        except DesktopError as exc:
            if exc.code == 'BACKEND_ERROR':
                raise DesktopError('DISPLAY_UNAVAILABLE', 'X11 metadata helper exited unexpectedly; reconnect or run doctor.',
                                   details={'backend_code':exc.code}) from exc
            raise
        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict): raise ValueError()
            if 'error' in envelope:
                error = envelope['error']
                if not isinstance(error,dict) or not isinstance(error.get('code'),str) or not isinstance(error.get('message'),str):
                    raise ValueError()
                raise DesktopError(error['code'],error['message'])
            return envelope['result']
        except (ValueError, KeyError, TypeError) as exc:
            raise DesktopError('BACKEND_ERROR','X11 metadata helper returned an invalid response.') from exc

    @staticmethod
    def _xid(window):
        if isinstance(window,bool) or not isinstance(window,int) or not 1 <= window <= 0xffffffff:
            raise DesktopError('INVALID_ARGUMENT','Window XID must be a positive 32-bit integer.')
        return window

    @property
    def root(self):
        return self._read('root')

    def geometry(self, window):
        return self._read('geometry',self._xid(window))

    def topology(self):
        """Current root, server generation, bounded RandR layout and logical workspace context."""
        return self._read('topology')

    def window_metadata(self, windows):
        """Bounded geometry, generation, ownership and optional WM properties."""
        if not isinstance(windows,(list,tuple)) or len(windows)>512:
            raise DesktopError('INVALID_ARGUMENT','Metadata batch must contain at most 512 XIDs.')
        result=self._read('window_metadata',[self._xid(window) for window in windows])
        result['windows']={int(xid):metadata for xid,metadata in result['windows'].items()}
        return result

    def geometries(self, windows):
        if not isinstance(windows,(list,tuple)) or len(windows)>512:
            raise DesktopError('INVALID_ARGUMENT','Geometry batch must contain at most 512 XIDs.')
        result=self._read('geometries',[self._xid(window) for window in windows])
        return {int(xid):bounds for xid,bounds in result.items()}

    def restack_above(self, window, sibling):
        pair=[self._xid(window),self._xid(sibling)]
        if pair[0]==pair[1]:raise DesktopError('INVALID_ARGUMENT','Restacking requires a distinct sibling.')
        return self._read('restack_above',pair)

    def selection_owner(self, selection='CLIPBOARD'):
        if selection not in ('CLIPBOARD','PRIMARY'):
            raise DesktopError('INVALID_ARGUMENT','Selection must be CLIPBOARD or PRIMARY.')
        return self._read('selection_owner',selection)

    def window_tokens(self, windows):
        """Stable across clients/remaps; changes after real X resource destruction.

        Initializes a private X11 property. Not a malicious-client trust boundary.
        """
        if not isinstance(windows,(list,tuple)) or len(windows)>512:
            raise DesktopError('INVALID_ARGUMENT','Window token batch must contain at most 512 XIDs.')
        result=self._read('window_tokens',[self._xid(window) for window in windows])
        return {int(xid):token for xid,token in result.items()}

    def surface_at(self, x, y):
        if any(isinstance(v,bool) or not isinstance(v,int) or not -32768 <= v <= 32767 for v in (x,y)):
            raise DesktopError('INVALID_ARGUMENT','Surface coordinates must be signed 16-bit integers.')
        return self._read('surface_at',[x,y])

    def root_surface(self, window):
        return self._read('root_surface',self._xid(window))

    def transient_for(self, window):
        return self._read('transient_for',self._xid(window))

    def children(self, window):
        return self._read('children',self._xid(window))

    def popup_surfaces(self, limit=256):
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1 <= limit <= 4096:
            raise DesktopError('INVALID_ARGUMENT','Popup enumeration limit must be an integer from 1 to 4096.')
        return self._read('popup_surfaces',limit)

    def close(self):
        """No persistent resources; subsequent reads can reconnect normally."""
