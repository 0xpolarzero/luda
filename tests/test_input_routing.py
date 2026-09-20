import json
import types
import unittest
from unittest.mock import Mock, patch
from luda.common import DesktopError
from luda.input_routing import prefers_private_input
from test_semantic import load_worker


class InputRoutingTests(unittest.TestCase):
    window = {'pid': 42, 'start': '123', 'window_id': 'unique'}

    def test_only_identified_gtk3_uses_private_input(self):
        for toolkit, version, expected in [('gtk', '3.24.41', True), ('GTK', '3.24', True),
                                          ('gtk', '4.18', False), ('gtk', '2.24', False),
                                          ('Chromium', '153', False), ('Qt', '6.8', False),
                                          ('', '', False), ('gtk', None, False),
                                          ('gtk', 'unknown', False)]:
            with self.subTest(toolkit=toolkit, version=version), patch('luda.input_routing.run', return_value=json.dumps({'toolkit': toolkit, 'toolkit_version': version}).encode()):
                self.assertEqual(prefers_private_input(self.window), expected)

    def test_lookup_is_read_only_bounded_and_process_scoped(self):
        with patch('luda.input_routing.run', return_value=b'{}') as run:
            self.assertFalse(prefers_private_input(self.window))
        self.assertEqual(json.loads(run.call_args.kwargs['data']), {'op': 'toolkit', 'pid': 42, 'start': '123'})
        self.assertEqual(run.call_args.kwargs['timeout'], .8)
        self.assertEqual(run.call_args.kwargs['max_output_bytes'], 4096)

    def test_missing_identity_does_not_query_provider(self):
        with patch('luda.input_routing.run') as run:
            for window in ({}, {'pid': True, 'start': '123'}, {'pid': 42}, {'pid': 42, 'start': ''}):
                self.assertFalse(prefers_private_input(window))
        run.assert_not_called()

    def test_invalid_provider_replies_use_compatible_route(self):
        for reply in (b'no json', b'[]', b'null', b'{"error":"ACCESSIBILITY_ERROR"}'):
            with patch('luda.input_routing.run', return_value=reply):
                self.assertFalse(prefers_private_input(self.window))

    def test_local_timeout_or_provider_failure_uses_compatible_route(self):
        for code in ('TIMEOUT', 'DEPENDENCY_MISSING', 'BACKEND_ERROR'):
            with patch('luda.input_routing.run', side_effect=DesktopError(code, 'provider failed')), patch('luda.input_routing.checkpoint') as checkpoint:
                self.assertFalse(prefers_private_input(self.window))
                checkpoint.assert_called_once()

    def test_cancellation_never_selects_fallback(self):
        with patch('luda.input_routing.run', side_effect=DesktopError('CANCELLED', 'cancelled')):
            with self.assertRaises(DesktopError) as caught:
                prefers_private_input(self.window)
        self.assertEqual(caught.exception.code, 'CANCELLED')

    def test_exhausted_action_deadline_never_selects_fallback(self):
        with patch('luda.input_routing.run', side_effect=DesktopError('TIMEOUT', 'provider timeout')), patch('luda.input_routing.checkpoint', side_effect=DesktopError('TIMEOUT', 'action timeout')):
            with self.assertRaises(DesktopError) as caught:
                prefers_private_input(self.window)
        self.assertEqual(caught.exception.code, 'TIMEOUT')


class ToolkitQueryTests(unittest.TestCase):
    def setUp(self):
        self.worker = load_worker()
        self.app = Mock()
        self.app.get_process_id.return_value = 42
        self.app.get_toolkit_name.return_value = 'gtk'
        self.app.get_toolkit_version.return_value = '3.24.41'
        self.desktop = Mock()
        self.desktop.get_child_count.return_value = 1
        self.desktop.get_child_at_index.return_value = self.app
        self.worker.Atspi = types.SimpleNamespace(get_desktop=Mock(return_value=self.desktop))
        self.worker.identity = Mock(return_value='123')
        self.request = {'op': 'toolkit', 'pid': 42, 'start': '123'}

    def test_reads_unique_application_metadata_without_mutation(self):
        self.assertEqual(self.worker.dispatch(self.request), {'toolkit': 'gtk', 'toolkit_version': '3.24.41'})
        self.assertEqual(self.worker.identity.call_count, 2)
        self.assertEqual([call[0] for call in self.app.mock_calls], ['get_process_id', 'get_toolkit_name', 'get_toolkit_version'])

    def test_missing_or_ambiguous_application_is_not_identified(self):
        for count in (0, 2, 257):
            self.desktop.get_child_count.return_value = count
            self.assertEqual(self.worker.dispatch(self.request)['error'], 'ACCESSIBILITY_UNAVAILABLE')

    def test_provider_exception_is_read_only_failure(self):
        self.app.get_toolkit_version.side_effect = RuntimeError('private application contents')
        result = self.worker.dispatch(self.request)
        self.assertEqual(result['effect'], 'none')
        self.assertNotIn('private application', json.dumps(result))

    def test_process_replacement_is_not_identified(self):
        self.worker.identity.side_effect = ['123', '456']
        self.assertEqual(self.worker.dispatch(self.request)['error'], 'STALE_TARGET')

    def test_invalid_process_identity_is_not_queried(self):
        result = self.worker.dispatch({**self.request, 'start': None})
        self.assertEqual(result['error'], 'INVALID_ARGUMENT')
        self.worker.Atspi.get_desktop.assert_not_called()

    def test_scan_timeout_never_uses_partial_match(self):
        with patch.object(self.worker.time, 'monotonic', side_effect=[0, 1]):
            result = self.worker.dispatch(self.request)
        self.assertEqual(result['error'], 'ACCESSIBILITY_UNAVAILABLE')
        self.app.get_toolkit_name.assert_not_called()
