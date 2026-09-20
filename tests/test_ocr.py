from contextlib import nullcontext
import asyncio
import threading
import os
import time
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from luda import ocr, server
from luda.common import DesktopError, operation_scope
from luda.desktop import Desktop

HEADER='\t'.join(ocr.HEADER)+'\n'
WORD='5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t92.5\tOrbit\n'

class OCRTests(unittest.TestCase):
    def test_parser_coordinates_score_and_truncation(self):
        result=ocr.parse_tsv((HEADER+WORD+WORD).encode(),100,100,1)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['candidates'],[{'text':'Orbit','image_bounds':{'x':10,'y':20,'width':30,'height':10},'engine_confidence':92.5}])
        self.assertEqual(ocr.parse_tsv(HEADER.encode(),100,100,1),{'candidates':[],'truncated':False})
    def test_malformed_numeric_utf8_bounds_and_rows_are_not_echoed(self):
        for raw in (b'SENSITIVE',b'\xff',(HEADER+WORD.replace('92.5','nan')).encode(),(HEADER+WORD.replace('\t30\t10\t','\t300\t10\t')).encode(),(HEADER+WORD.replace('\t92.5\t','\t-1\t')).encode(),(HEADER+'\n'*20001).encode()):
            with self.subTest(raw=raw[:20]),self.assertRaises(DesktopError) as caught:ocr.parse_tsv(raw,100,100,1)
            self.assertEqual(caught.exception.code,'OCR_INVALID_OUTPUT');self.assertNotIn('SENSITIVE',str(caught.exception))
    def test_missing_engine_language_and_invalid_input_are_explicit(self):
        with patch.object(ocr.shutil,'which',return_value=None),self.assertRaises(DesktopError) as caught:ocr.recognize(b'png',(100,100),'eng',1,{})
        self.assertEqual(caught.exception.code,'OCR_UNAVAILABLE')
        with patch.object(ocr.shutil,'which',return_value='/usr/bin/tesseract'),patch.object(ocr,'run',return_value=b'List of available languages (1):\neng\n') as run,self.assertRaises(DesktopError) as caught:ocr.recognize(b'png',(100,100),'fra',1,{})
        self.assertEqual(caught.exception.code,'OCR_LANGUAGE_UNAVAILABLE');self.assertEqual(run.call_count,1)
        for language,limit,image in [('../eng',1,(100,100)),('eng',True,(100,100)),('eng',1001,(100,100)),('eng',1,(10000,10000))]:
            with patch.object(ocr,'run') as run,self.assertRaises(DesktopError):ocr.recognize(b'png',image,language,limit,{})
            run.assert_not_called()
    def test_engine_uses_stdin_stdout_fixed_flags_and_bounds(self):
        with patch.object(ocr.shutil,'which',return_value='/usr/bin/tesseract'),patch.object(ocr,'run',side_effect=[b'eng\n',(HEADER+WORD).encode()]) as run:
            value=ocr.recognize(b'exact screenshot',(100,100),'eng',1,{})
        self.assertEqual(run.call_args.args[0],['/usr/bin/tesseract','stdin','stdout','-l','eng','--psm','11','tsv'])
        self.assertEqual(run.call_args.kwargs,{'data':b'exact screenshot','timeout':5,'max_output_bytes':1048576})
        self.assertEqual(value['candidates'][0]['text'],'Orbit')
    def test_engine_failure_sanitized_but_cancellation_and_limits_preserved(self):
        for code in ('BACKEND_ERROR','TIMEOUT','CANCELLED','OUTPUT_LIMIT'):
            with patch.object(ocr.shutil,'which',return_value='/usr/bin/tesseract'),patch.object(ocr,'run',side_effect=DesktopError(code,'SENSITIVE')),self.assertRaises(DesktopError) as caught:ocr.recognize(b'png',(100,100),'eng',1,{})
            self.assertEqual(caught.exception.code,'OCR_UNAVAILABLE' if code=='BACKEND_ERROR' else code)
            if code=='BACKEND_ERROR':self.assertNotIn('SENSITIVE',str(caught.exception))
    def test_actual_engine_child_cancellation_stops_late_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);engine=root/'engine';started=root/'started';late=root/'late'
            engine.write_text('#!/usr/bin/python3\nimport sys,time,os\nfrom pathlib import Path\nif "--list-langs" in sys.argv:print("eng")\nelse:\n Path('+repr(str(started))+').write_text(str(os.getpid()))\n time.sleep(2)\n Path('+repr(str(late))+').touch()\n')
            engine.chmod(0o700);cancelled=threading.Event()
            def cancel_after_start():
                deadline=time.monotonic()+2
                while not started.exists() and time.monotonic()<deadline:time.sleep(.005)
                cancelled.set()
            watcher=threading.Thread(target=cancel_after_start);watcher.start()
            try:
                with patch.object(ocr.shutil,'which',return_value=str(engine)),operation_scope(timeout=3,cancelled=cancelled),self.assertRaises(DesktopError) as caught:
                    ocr.recognize(b'png',(100,100),'eng',1,{})
                self.assertEqual(caught.exception.code,'CANCELLED')
                self.assertFalse(late.exists());self.assertTrue(started.exists())
                with self.assertRaises(ProcessLookupError):os.kill(int(started.read_text()),0)
            finally:watcher.join(timeout=3)

    def test_snapshot_byte_budget_and_oversize_preserve_pointer_metadata(self):
        snapshots={}
        with patch.object(ocr,'MAX_CACHE_BYTES',10):
            ocr.retain_snapshot(snapshots,'one',{'png':b'123456'})
            ocr.retain_snapshot(snapshots,'two',{'png':b'123456'})
            self.assertEqual(list(snapshots),['two'])
            ocr.retain_snapshot(snapshots,'huge',{'png':b'x'*11,'image':(10,10)})
            self.assertEqual(snapshots['huge'],{'image':(10,10)})
    def driver(self):
        d=Desktop();self.addCleanup(d.close);d.x=Mock();d.x.topology.return_value={'id':1}
        d.list_windows=Mock(return_value=[]);d.observe_popups=Mock(return_value=[])
        from luda.timing import elapsed_time
        d.snapshots['owned']={'time':elapsed_time(),'png':b'exact','image':(100,100),'signature':d.signature([]),'popups':[],'topology':{'id':1}}
        return d
    def test_exact_snapshot_no_capture_and_stale_layout_preflight(self):
        d=self.driver()
        with patch('luda.desktop.recognize',return_value={'candidates':[],'truncated':False}) as recognize:
            value=d.ocr('owned');self.assertEqual(recognize.call_args.args[0],b'exact')
            self.assertEqual(value['effect'],'none');self.assertIn('historical',value['source'])
            d.x.topology.return_value={'id':2}
            with self.assertRaises(DesktopError) as caught:d.ocr('owned')
            self.assertEqual(caught.exception.code,'STALE_OBSERVATION');self.assertEqual(recognize.call_count,1)
    def test_layout_changed_during_ocr_and_expired_snapshot_refused(self):
        d=self.driver()
        def changed(*args):d.x.topology.return_value={'id':2};return {'candidates':[]}
        with patch('luda.desktop.recognize',side_effect=changed),self.assertRaises(DesktopError):d.ocr('owned')
        d.snapshots['owned']['time']-=20
        with patch('luda.desktop.recognize') as recognize,self.assertRaises(DesktopError):d.ocr('owned')
        recognize.assert_not_called();self.assertNotIn('owned',d.snapshots)
    def test_optional_engine_absence_does_not_change_backend_readiness(self):
        d=self.driver();d.x.geometry.return_value={'width':100,'height':100}
        d.environment={'PATH':'/usr/bin','DISPLAY':':77','DBUS_SESSION_BUS_ADDRESS':'owned'}
        with patch('luda.desktop.shutil.which',side_effect=lambda name,**kw:None if name=='tesseract' else '/usr/bin/'+name),patch('luda.desktop.run',return_value=b'0'),patch('luda.desktop.topology_summary',return_value={}),patch('luda.desktop.font_coverage',return_value={}),patch('luda.desktop.session_state',return_value={'input_ready':True}),patch('luda.desktop.keyboard_capabilities',return_value={'available':True}),patch.object(Desktop,'input_scope',return_value=nullcontext()),patch('luda.desktop.composition_capability',return_value={}),patch.object(d.control,'status',return_value={'paused':False}):
            result=d.doctor()
        self.assertFalse(result['ocr']['available']);self.assertTrue(result['ready'])

    def test_public_schema_is_read_only(self):
        tool=next(t for t in asyncio.run(server.mcp.list_tools()) if t.name=='desktop_ocr')
        self.assertTrue(tool.annotations.readOnlyHint);self.assertEqual(tool.inputSchema['required'],['snapshot_id'])
