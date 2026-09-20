"""Native RandR allocation/error paths and public-header ABI qualification."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from luda import _randr as r
from luda.common import DesktopError

class RandrAllocations(unittest.TestCase):
    def setUp(self):
        self.resource=r.Resources();self.ids=(C.c_ulong*1)(7)
        self.resource.ncrtc=1;self.resource.crtcs=self.ids
        self.crtc=r.Crtc();self.crtc.width=1280;self.crtc.height=720
        self.transform=r.Transform();self.transform.current[:]=r.IDENTITY
        self.monitors=(r.Monitor*1)();self.monitors[0].width=1280
        self.native=SimpleNamespace(display=1,root=2,lib=SimpleNamespace(XFree=Mock()))
        self.lib=SimpleNamespace(**{name:Mock() for name in ('XRRQueryVersion','XRRGetScreenResourcesCurrent','XRRFreeScreenResources','XRRGetCrtcInfo','XRRFreeCrtcInfo','XRRGetCrtcTransform','XRRGetPanning','XRRFreePanning','XRRGetMonitors','XRRFreeMonitors')})
        def version(display,major,minor):major._obj.value=1;minor._obj.value=5;return 1
        def transform(display,xid,destination):
            C.cast(destination,C.POINTER(C.POINTER(r.Transform)))[0]=C.pointer(self.transform);return 1
        def monitors(display,root,active,count):count._obj.value=1;return self.monitors
        self.lib.XRRQueryVersion.side_effect=version
        self.lib.XRRGetScreenResourcesCurrent.return_value=C.pointer(self.resource)
        self.lib.XRRGetCrtcInfo.return_value=C.pointer(self.crtc)
        self.lib.XRRGetCrtcTransform.side_effect=transform
        self.lib.XRRGetPanning.return_value=None
        self.lib.XRRGetMonitors.side_effect=monitors
    def read(self):
        with patch.object(r.C,'CDLL',return_value=self.lib):return r.read_topology(self.native)
    def test_success_frees_all_allocations_and_preserves_absent_panning(self):
        value=self.read();self.assertIsNone(value['crtcs'][0]['panning'])
        self.assertEqual(value['crtcs'][0]['transform'],r.IDENTITY)
        for name in ('XRRFreeScreenResources','XRRFreeCrtcInfo','XRRFreeMonitors'):getattr(self.lib,name).assert_called_once()
        self.native.lib.XFree.assert_called_once();self.lib.XRRFreePanning.assert_not_called()
    def test_bad_crtc_count_never_dereferences_and_frees_resources(self):
        self.resource.ncrtc=65
        with self.assertRaises(DesktopError) as caught:self.read()
        self.assertEqual(caught.exception.code,'TOPOLOGY_UNAVAILABLE')
        self.lib.XRRGetCrtcInfo.assert_not_called();self.lib.XRRFreeScreenResources.assert_called_once()
    def test_disappearing_crtc_frees_resource(self):
        self.lib.XRRGetCrtcInfo.return_value=None
        with self.assertRaises(DesktopError) as caught:self.read()
        self.assertEqual(caught.exception.code,'DESKTOP_CHANGED')
        self.lib.XRRFreeScreenResources.assert_called_once()
    def test_failed_transform_with_allocation_frees_it_and_resource(self):
        previous=self.lib.XRRGetCrtcTransform.side_effect
        self.lib.XRRGetCrtcTransform.side_effect=lambda *args:previous(*args) and 0
        with self.assertRaises(DesktopError) as caught:self.read()
        self.assertEqual(caught.exception.code,'TOPOLOGY_UNAVAILABLE')
        self.native.lib.XFree.assert_called_once();self.lib.XRRFreeScreenResources.assert_called_once()
    def test_invalid_monitor_output_count_frees_monitor_and_resources(self):
        self.monitors[0].noutput=1
        with self.assertRaises(DesktopError) as caught:self.read()
        self.assertEqual(caught.exception.code,'TOPOLOGY_UNAVAILABLE')
        self.lib.XRRFreeMonitors.assert_called_once();self.lib.XRRFreeScreenResources.assert_called_once()
    def test_absent_extension_is_explicit_and_never_reads_resources(self):
        self.lib.XRRQueryVersion.side_effect=None;self.lib.XRRQueryVersion.return_value=0
        with self.assertRaises(DesktopError) as caught:self.read()
        self.assertEqual(caught.exception.code,'TOPOLOGY_UNAVAILABLE')
        self.lib.XRRGetScreenResourcesCurrent.assert_not_called()

class RandrHeaderABI(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc') and Path('/usr/include/X11/extensions/Xrandr.h').is_file(),'Optional C ABI qualification requires cc and libxrandr-dev headers')
    def test_all_struct_sizes_and_offsets_match_installed_public_header(self):
        classes={r.Resources:'XRRScreenResources',r.Crtc:'XRRCrtcInfo',r.Transform:'XRRCrtcTransformAttributes',r.Panning:'XRRPanning',r.Monitor:'XRRMonitorInfo'}
        statements=[];expected={}
        for cls,ctype in classes.items():
            key=cls.__name__+'.size';expected[key]=C.sizeof(cls)
            statements.append(f'printf("{key}=%zu\\n",sizeof({ctype}));')
            for name,_ in cls._fields_:
                cname={'pending':'pendingTransform','current':'currentTransform'}.get(name,name) if cls is r.Transform else name
                key=cls.__name__+'.'+name;expected[key]=getattr(cls,name).offset
                statements.append(f'printf("{key}=%zu\\n",offsetof({ctype},{cname}));')
        source='#include <X11/extensions/Xrandr.h>\n#include <stddef.h>\n#include <stdio.h>\nint main(void){'+''.join(statements)+'return 0;}'
        with tempfile.TemporaryDirectory(prefix='luda-randr-abi-') as directory:
            path=Path(directory);(path/'abi.c').write_text(source)
            subprocess.run(['cc','-Wall','-Werror',str(path/'abi.c'),'-o',str(path/'abi')],capture_output=True,check=True,timeout=10)
            output=subprocess.check_output([str(path/'abi')],text=True,timeout=3)
        actual={key:int(value) for key,value in (line.split('=') for line in output.splitlines())}
        self.assertEqual(actual,expected)

if __name__=='__main__':unittest.main()
