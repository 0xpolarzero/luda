import unittest
from unittest.mock import patch
from luda.diagnostics import capability_summary
from luda.keyboard import keyboard_capabilities


class DiagnosticCapabilities(unittest.TestCase):
    def report(self):
        return dict(dependencies=dict(scrot=True,xdotool=True,xclip=True,wmctrl=True),display_available=True,topology_available=True,
                    session_state={'input_ready':None},control={'available':True,'paused':False},
                    keyboard={'available':True},accessibility_available=True)
    def test_unavailable_accessibility_keeps_screenshot_fallback_available(self):
        report=self.report();report['accessibility_available']=False
        state=capability_summary(report)
        self.assertEqual(state['screen_observation'],'backend_available')
        self.assertEqual(state['pointer_input'],'backend_available')
        self.assertEqual(state['verified_text_editing'],'unavailable')
    def test_pause_and_unknown_control_block_mutations_but_not_observation(self):
        for control in ({'available':True,'paused':True},{'available':False}):
            report=self.report();report['control']=control;state=capability_summary(report)
            self.assertEqual(state['screen_observation'],'backend_available')
            self.assertEqual(state['accessibility_read'],'backend_available')
            for key in ('pointer_input','keyboard_input','clipboard_paste','verified_text_editing'):
                self.assertEqual(state[key],'blocked')
    def test_display_loss_and_missing_keyboard_have_distinct_capabilities(self):
        report=self.report();report['keyboard']['available']=False
        self.assertEqual(capability_summary(report)['keyboard_input'],'unavailable')
        self.assertEqual(capability_summary(report)['pointer_input'],'backend_available')
        report['display_available']=False
        self.assertEqual(capability_summary(report)['screen_observation'],'unavailable')
    def test_provider_success_does_not_claim_every_editor_supported(self):
        self.assertEqual(capability_summary(self.report())['verified_text_editing'],'application_dependent')
    def test_missing_topology_disables_snapshot_pointer_but_not_semantics(self):
        report=self.report();report['topology_available']=False
        result=capability_summary(report)
        self.assertEqual(result['screen_observation'],'unavailable')
        self.assertEqual(result['pointer_input'],'unavailable')
        self.assertEqual(result['accessibility_read'],'backend_available')
    def test_invalid_native_probe_is_not_a_capability(self):
        for value in (b'1',b'[]',b'null'):
            with patch('luda.keyboard.run',return_value=value):
                self.assertEqual(keyboard_capabilities(),{'available':False,'reason':'invalid_response'})

    def test_missing_window_enumerator_disables_targeted_capabilities(self):
        for missing in (False,None):
            report=self.report()
            if missing is None:report['dependencies'].pop('wmctrl')
            else:report['dependencies']['wmctrl']=missing
            state=capability_summary(report)
            for key in ('screen_observation','pointer_input','keyboard_input','clipboard_paste','accessibility_read','verified_text_editing'):
                with self.subTest(missing=missing,capability=key):
                    self.assertEqual(state[key],'unavailable')

    def test_missing_focus_proof_preserves_only_readonly_fallback(self):
        report=self.report();report['dependencies']['xdotool']=False
        state=capability_summary(report)
        for key in ('screen_observation','accessibility_read'):
            self.assertEqual(state[key],'backend_available')
        for key in ('pointer_input','keyboard_input','clipboard_paste','verified_text_editing'):
            self.assertEqual(state[key],'unavailable')
