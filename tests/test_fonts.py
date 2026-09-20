"""Font coverage is bounded, honest and advisory under provider failure."""
import errno
from contextlib import redirect_stdout
import io
import json
import os
import unittest
from unittest.mock import Mock,patch
from luda import fonts, _font_probe
from luda.common import DesktopError,subprocess_environment
from luda.desktop import Desktop

class FontCoverage(unittest.TestCase):
    def response(self):return {'pango_version':'1.52.1','samples':[{'sample':name,'unknown_glyphs':0} for name,_,_ in fonts.SAMPLES]}
    def test_missing_samples_are_explicit_and_do_not_block_input(self):
        value=self.response();value['samples'][0]['unknown_glyphs']=6
        with patch.object(fonts,'run',return_value=json.dumps(value).encode()) as run:result=fonts.font_coverage()
        self.assertEqual(result['status'],'partial');self.assertEqual(result['missing_samples'],['Japanese']);self.assertFalse(result['blocks_input'])
        self.assertEqual(run.call_args.kwargs['timeout'],3);self.assertEqual(run.call_args.kwargs['max_output_bytes'],8192)
        self.assertNotIn('data',run.call_args.kwargs)
    def test_complete_samples_are_not_universal_coverage(self):
        with patch.object(fonts,'run',return_value=json.dumps(self.response()).encode()):result=fonts.font_coverage()
        self.assertEqual(result['status'],'covered');self.assertEqual(result['missing_samples'],[]);self.assertIn('not universal',result['scope'])
    def test_malformed_provider_output_is_redacted(self):
        cases=[b'private provider text',b'null',b'[]',b'{}',b'{"error":"private provider text"}']
        for field,value in [('sample','private provider text'),('unknown_glyphs',True),('unknown_glyphs',-1),('unknown_glyphs',129)]:
            result=self.response();result['samples'][0][field]=value;cases.append(json.dumps(result).encode())
        result=self.response();result['samples'].pop();cases.append(json.dumps(result).encode())
        for output in cases:
            with self.subTest(output=output),patch.object(fonts,'run',return_value=output):
                result=fonts.font_coverage();self.assertEqual(result['status'],'unavailable');self.assertNotIn('private provider text',str(result))
    def test_timeout_crash_and_resource_failures_are_unavailable(self):
        for code in ('TIMEOUT','BACKEND_ERROR','RESOURCE_UNAVAILABLE','OUTPUT_LIMIT','DEPENDENCY_MISSING'):
            with patch.object(fonts,'run',side_effect=DesktopError(code,'private detail')):
                result=fonts.font_coverage();self.assertFalse(result['available']);self.assertFalse(result['blocks_input']);self.assertNotIn('private detail',str(result))
        with patch.object(fonts,'run',side_effect=OSError(errno.EMFILE,'private path')):
            self.assertEqual(fonts.font_coverage()['code'],'RESOURCE_UNAVAILABLE')
    def test_helper_provider_and_resource_failures_are_redacted(self):
        for error,code in ((MemoryError('private'),'RESOURCE_UNAVAILABLE'),(OSError(errno.EMFILE,'private'),'RESOURCE_UNAVAILABLE'),(RuntimeError('private'),'FONT_PROVIDER_UNAVAILABLE')):
            output=io.StringIO()
            with patch.object(_font_probe,'probe',side_effect=error),redirect_stdout(output):_font_probe.main()
            self.assertEqual(json.loads(output.getvalue()),{'error':code})
    def test_cancel_propagates(self):
        with patch.object(fonts,'run',side_effect=DesktopError('CANCELLED','cancelled')),self.assertRaises(DesktopError):fonts.font_coverage()
    def test_selected_font_environment_is_scoped_and_restored(self):
        seen=[]
        def run(*args,**kwargs):seen.append(dict(subprocess_environment()));return json.dumps(self.response()).encode()
        before=subprocess_environment()
        with patch.object(fonts,'run',side_effect=run):fonts.font_coverage({'FONTCONFIG_FILE':'/private/config','HOME':'/selected'})
        self.assertEqual(seen,[{'FONTCONFIG_FILE':'/private/config','HOME':'/selected'}]);self.assertEqual(subprocess_environment(),before)
    def test_doctor_ready_and_capabilities_do_not_depend_on_font_coverage(self):
        d=Desktop(dict(os.environ,DBUS_SESSION_BUS_ADDRESS='fixture'));self.addCleanup(d.close);d.x=Mock();d.x.root=1;d.x.geometry.return_value={'width':100,'height':100}
        d.x.topology.return_value={'root':d.x.geometry.return_value,'randr':{'version':[1,6],'monitors':[],'crtcs':[]}}
        for coverage in ({'available':True,'status':'partial','missing_samples':['Japanese']},{'available':False,'status':'unavailable'}):
            with patch('luda.desktop.font_coverage',return_value=coverage) as probe,patch('luda.desktop.shutil.which',return_value='/bin/true'),patch('luda.desktop.run',return_value=b'1'),patch('luda.desktop.session_state',return_value={'input_ready':True}),patch('luda.desktop.keyboard_capabilities',return_value={'available':True}):
                report=d.doctor();self.assertTrue(report['ready']);self.assertEqual(report['font_coverage'],coverage)
                self.assertEqual(report['capabilities']['screen_observation'],'backend_available');self.assertEqual(report['capabilities']['verified_text_editing'],'application_dependent')
                probe.assert_called_once_with(d.environment)

if __name__=='__main__':unittest.main()
