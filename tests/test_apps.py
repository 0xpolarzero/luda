import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from luda.apps import launch_application,list_applications
from luda._app_helper import AppError,uri_for
from luda.common import DesktopError

class AppTests(unittest.TestCase):
    @patch('luda.apps._call')
    def test_invalid_discovery_is_not_dispatched(self,call):
        for args in ({'query':'\0'},{'query':'\ud800'},{'limit':True},{'limit':0},{'limit':201},{'query':None}):
            with self.subTest(args=args),self.assertRaises(DesktopError):list_applications(**args)
        call.assert_not_called()
    @patch('luda.apps._call')
    def test_commands_paths_and_invalid_inputs_not_dispatched(self,call):
        for identity in ('sh -c echo','/tmp/a.desktop','../a.desktop','a\\b.desktop','a.desktop\n'):
            with self.subTest(identity=identity),self.assertRaises(DesktopError):launch_application(identity)
        for values in ('file',[],[None],[''],['\ud800'],['x'*8193],['x']*129):
            if values==[]:continue
            with self.subTest(values=values),self.assertRaises(DesktopError):launch_application('valid.desktop',values)
        call.assert_not_called()
    @patch('luda.apps._call')
    def test_unicode_desktop_id_passed_literally(self,call):
        launch_application('日本語 app.desktop',['https://example.invalid/a'])
        self.assertEqual(call.call_args.args[1]['application_id'],'日本語 app.desktop')
    def test_absolute_unicode_paths_and_file_uris(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'日本語 space.txt';path.write_text('data')
            self.assertEqual(uri_for(str(path)),(path.as_uri(),True))
            self.assertEqual(uri_for(path.as_uri()),(path.as_uri(),True))
    def test_missing_paths_and_unsupported_uri_shapes(self):
        for value in ('relative.txt','/this/path/does/not/exist','file://otherhost/tmp/file','https:///empty','https://exa mple.invalid','https://example.invalid/%GG'):
            with self.subTest(value=value),self.assertRaises(AppError):uri_for(value)
    def test_remote_and_custom_uris_retained(self):
        for value in ('https://example.invalid/a?x=1','mailto:user@example.invalid','custom-app:日本語'):
            self.assertEqual(uri_for(value),(value,False))

class HelperFailureTests(unittest.TestCase):
    @patch('luda.apps.run',side_effect=DesktopError('TIMEOUT','test'))
    def test_timeout_preserved(self,run):
        with self.assertRaises(DesktopError) as exc:launch_application('valid.desktop')
        self.assertEqual(exc.exception.code,'TIMEOUT')
    @patch('luda.apps.run',side_effect=DesktopError('BACKEND_ERROR','private-uri-secret',effect='uncertain'))
    def test_helper_stderr_is_not_exposed(self,run):
        with self.assertRaises(DesktopError) as exc:launch_application('valid.desktop')
        self.assertNotIn('private-uri-secret',str(exc.exception))
        self.assertEqual(exc.exception.effect,'uncertain')
    @patch('luda.apps.run',return_value=b'not JSON')
    def test_malformed_helper_response(self,run):
        with self.assertRaises(DesktopError) as exc:list_applications()
        self.assertEqual(exc.exception.code,'BACKEND_ERROR')
    @patch('luda.apps.run',return_value=b'{"error":{"code":"APPLICATION_NOT_FOUND","message":"missing","effect":"none"}}')
    def test_helper_error_keeps_no_effect(self,run):
        with self.assertRaises(DesktopError) as exc:launch_application('missing.desktop')
        self.assertEqual(exc.exception.code,'APPLICATION_NOT_FOUND');self.assertEqual(exc.exception.effect,'none')

if __name__=='__main__':unittest.main()
