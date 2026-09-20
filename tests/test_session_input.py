from contextlib import contextmanager
import json
from unittest.mock import Mock,patch
import unittest
from luda import server
from luda.common import DesktopError,environment_scope,subprocess_environment
from luda.session_state import require_session_input

class SessionInput(unittest.TestCase):
    def backend(self):
        backend=Mock(environment={'DISPLAY':':37'})
        @contextmanager
        def transaction():
            with environment_scope(backend.environment):yield
        backend.transaction=transaction
        backend.key.return_value={'effect':'dispatched'}
        backend.observe.return_value={'windows':[]}
        return backend
    def test_blocking_hints_refuse_without_touching_mutation(self):
        for state in ('locked','screensaver_active'):
            backend=self.backend()
            with patch.object(server,'get_backend',return_value=backend),patch('luda.session_state.session_state',return_value={'input_ready':False,'state':state}):
                result=json.loads(server.execute('key','window','Return').content[0].text)
            self.assertEqual((result['code'],result['effect']),('SESSION_BLOCKED','none'))
            backend.key.assert_not_called()
    def test_observation_and_recovery_do_not_query_or_unlock(self):
        backend=self.backend()
        with patch.object(server,'get_backend',return_value=backend),patch.object(server,'require_session_input') as guard,patch.object(server,'recover_keyboard_input',return_value={'effect':'none','pending_count':0}):
            self.assertFalse(server.execute('observe').isError)
            self.assertFalse(server.execute('recover_input').isError)
            guard.assert_not_called()
    def test_query_uses_selected_backend_environment(self):
        backend=self.backend()
        def query():
            self.assertEqual(subprocess_environment()['DISPLAY'],':37')
            return {'input_ready':None,'state':'unknown'}
        with patch.object(server,'get_backend',return_value=backend),patch('luda.session_state.session_state',side_effect=query):
            self.assertFalse(server.execute('key','window','Return').isError)
        backend.key.assert_called_once_with('window','Return')
    def test_unknown_and_inactive_are_not_claimed_unlocked_or_blocked(self):
        for state in ('unknown','inactive'):
            with patch('luda.session_state.session_state',return_value={'input_ready':None,'state':state}):require_session_input()
    def test_probe_timeout_prevents_dispatch(self):
        backend=self.backend()
        with patch.object(server,'get_backend',return_value=backend),patch('luda.session_state.session_state',side_effect=DesktopError('TIMEOUT','probe deadline')):
            result=json.loads(server.execute('key','window','Return').content[0].text)
        self.assertEqual((result['code'],result['effect']),('TIMEOUT','none'));backend.key.assert_not_called()
