"""Contract tests for the bounded evaluation fixture, not benchmark passes."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('skill_effect_fixture', ROOT / 'scripts/evaluation/skill_effect_fixture.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def states():
    """Metadata-only unit doubles. No generated image is presented as a capture."""
    entries = []
    for selected, applied in [('Greybird', 'Greybird'), ('Greybird-dark', 'Greybird'),
                              ('Greybird-dark', 'Greybird-dark'), (None, None), ('target.txt', None)]:
        file_case = applied is None
        names = ['target.txt'] if file_case else ['Greybird', 'Greybird-dark']
        entries.append(dict(selected=selected, applied=applied, opened=False,
                            image_base64=None, observe={'image_size': {'width': 1000, 'height': 700}},
                            windows={'windows': [{'window_id': 'window'}]}, doctor={'ready': True},
                            inspect={'window_id': 'window', 'nodes': [dict(element_id=name, parent_element_id=None,
                                     name=name, role='list item', actions=['activate'],
                                     states=['selected'] if name == selected else []) for name in names]},
                            click_targets={names[-1]: {'x': 10, 'y': 20, 'width': 100, 'height': 25}}))
    return entries


def call(fixture, name, **args):
    response = asyncio.run(fixture.call(name, args))
    return json.loads(response.content[0].text)


def target(fixture):
    result = call(fixture, 'desktop_inspect', window_id='window')
    return result['nodes'][-1]['element_id']


class Transitions(unittest.TestCase):
    def test_clean_selection_and_reselection_do_not_apply(self):
        fixture = f.Fixture('theme-clean', states())
        element = target(fixture)
        for expected in (True, False):
            result = call(fixture, 'desktop_choose', element_id=element)
            self.assertEqual(result['changed'], expected)
            self.assertEqual(result['verification_scope'], 'selection')
            self.assertEqual(fixture.selected, 'Greybird-dark')
            self.assertEqual(fixture.applied, 'Greybird')

    def test_advertised_activation_applies(self):
        fixture = f.Fixture('theme', states())
        result = call(fixture, 'desktop_invoke', element_id=target(fixture))
        self.assertEqual(result['effect'], 'dispatched')
        self.assertEqual(fixture.applied, 'Greybird-dark')
        self.assertIsNone(fixture.last_observation)

    def test_activation_no_effect_remains_light(self):
        fixture = f.Fixture('activation-no-effect', states())
        result = call(fixture, 'desktop_invoke', element_id=target(fixture), action='activate')
        self.assertTrue(result['accepted'])
        self.assertEqual(fixture.applied, 'Greybird')
        self.assertEqual(fixture.frame()['applied'], 'Greybird')

    def test_immediate_selection_applies(self):
        fixture = f.Fixture('instant-clean', states())
        call(fixture, 'desktop_choose', element_id=target(fixture))
        self.assertEqual(fixture.applied, 'Greybird-dark')

    def test_selection_does_not_open(self):
        for case in ('select-only', 'select-already'):
            fixture = f.Fixture(case, states())
            call(fixture, 'desktop_choose', element_id=target(fixture))
            self.assertEqual(fixture.selected, 'target.txt')
            self.assertFalse(fixture.opened)
            self.assertFalse(fixture.forbidden_open_attempt)

    def test_forbidden_open_attempt_remains_recorded(self):
        fixture = f.Fixture('select-already', states())
        call(fixture, 'desktop_invoke', element_id=target(fixture))
        self.assertTrue(fixture.opened)
        self.assertTrue(fixture.forbidden_open_attempt)
        result = call(fixture, 'desktop_observe')
        self.assertEqual(result['code'], 'FIXTURE_UNSUPPORTED')
        self.assertEqual(len(fixture.history), 3)

    def test_invalid_schema_never_mutates(self):
        fixture = f.Fixture('theme', states())
        before = fixture.state()
        result = call(fixture, 'desktop_choose', element_id=target(fixture), invented=True)
        self.assertEqual(result['code'], 'INVALID_ARGUMENT')
        self.assertEqual(fixture.state(), before)

    def test_unknown_action_never_applies(self):
        fixture = f.Fixture('theme', states())
        result = call(fixture, 'desktop_invoke', element_id=target(fixture), action='invented')
        self.assertEqual(result['code'], 'UNSUPPORTED_ACTION')
        self.assertEqual(fixture.applied, 'Greybird')

    def test_stale_element_refusal_and_recovery_preserved(self):
        now = [0]
        fixture = f.Fixture('theme', states(), clock=lambda: now[0])
        element = target(fixture)
        now[0] = 60
        result = call(fixture, 'desktop_invoke', element_id=element)
        self.assertEqual(result['code'], 'STALE_TARGET')
        call(fixture, 'desktop_invoke', element_id=target(fixture))
        self.assertEqual(fixture.applied, 'Greybird-dark')
        self.assertEqual(fixture.history[1]['response']['code'], 'STALE_TARGET')

    def test_fresh_grounded_click_selects_or_opens(self):
        for count in (1, 2):
            fixture = f.Fixture('select-only', states())
            snapshot = call(fixture, 'desktop_observe')['snapshot_id']
            call(fixture, 'desktop_click', window_id='window', snapshot_id=snapshot, x=20, y=30, count=count)
            self.assertEqual(fixture.selected, 'target.txt')
            self.assertEqual(fixture.opened, count == 2)
            self.assertEqual(fixture.forbidden_open_attempt, count == 2)

    def test_expired_snapshot_refuses_click(self):
        now = [0]
        fixture = f.Fixture('theme', states(), clock=lambda: now[0])
        snapshot = call(fixture, 'desktop_observe')['snapshot_id']
        now[0] = 15
        result = call(fixture, 'desktop_click', window_id='window', snapshot_id=snapshot, x=20, y=30)
        self.assertEqual(result['code'], 'STALE_SNAPSHOT')
        self.assertEqual(fixture.applied, 'Greybird')

    def test_history_is_saved_after_error_and_success(self):
        fixture = f.Fixture('theme', states())
        with tempfile.TemporaryDirectory() as directory:
            fixture.history_path = Path(directory) / 'history.json'
            fixture.persist()
            self.assertEqual(json.loads(fixture.history_path.read_text())['history'], [])
            call(fixture, 'desktop_activate', window_id='window')
            call(fixture, 'desktop_invoke', element_id=target(fixture))
            saved = json.loads(fixture.history_path.read_text())
            self.assertEqual(saved['state']['applied'], 'Greybird-dark')
            self.assertEqual(saved['history'][0]['response']['code'], 'FIXTURE_UNSUPPORTED')
            self.assertFalse(fixture.history_path.with_suffix('.json.tmp').exists())

    def test_other_advertised_actions_do_not_activate(self):
        captures = states()
        for entry in captures:
            for node in entry['inspect']['nodes']:
                node['actions'] = ['edit', 'activate']
        fixture = f.Fixture('theme', captures)
        element = target(fixture)
        result = call(fixture, 'desktop_invoke', element_id=element)
        self.assertEqual(result['code'], 'UNSUPPORTED_ACTION')
        result = call(fixture, 'desktop_invoke', element_id=element, action='edit')
        self.assertEqual(result['code'], 'FIXTURE_UNSUPPORTED')
        self.assertEqual(fixture.applied, 'Greybird')

    def test_missing_capture_and_unsupported_path_never_pass(self):
        fixture = f.Fixture('theme', states())
        result = call(fixture, 'desktop_press_keys', window_id='window', keys='Return')
        self.assertEqual(result['code'], 'INVALID_ARGUMENT')
        result = call(fixture, 'desktop_activate', window_id='window')
        self.assertEqual(result['code'], 'FIXTURE_UNSUPPORTED')
        self.assertTrue(fixture.evidence()['unsupported_paths'])
        self.assertEqual(fixture.evidence()['final_claim_grade'], 'requires independent adjudication')
        with self.assertRaises(f.Unsupported):
            f.Fixture('theme', [])

    def test_no_unreviewed_or_missing_screenshot_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            path.write_text(json.dumps({'schema_version': 1, 'states': []}))
            with self.assertRaises(ValueError):
                f.Fixture.from_manifest('theme', path)
            path.write_text(json.dumps({'schema_version': 1, 'independently_reviewed': True,
                                       'states': [{'screenshot': 'missing.png'}]}))
            with self.assertRaises(FileNotFoundError):
                f.Fixture.from_manifest('theme', path)


class RealCaptures(unittest.TestCase):
    def test_checked_real_images_follow_independent_state(self):
        manifest = ROOT / 'tests/fixtures/skill-outcomes/manifest.json'
        for case in f.CASES:
            fixture = f.Fixture.from_manifest(case, manifest)
            before = fixture.frame()['image_base64']
            window = fixture.frame()['inspect']['window_id']
            result = call(fixture, 'desktop_inspect', window_id=window)
            expected = 'target.txt' if fixture.file_case else 'Greybird-dark'
            node = next(n for n in result['nodes'] if n.get('name', '').split('\n')[0] == expected)
            call(fixture, 'desktop_choose', element_id=node['element_id'])
            selected = fixture.frame()['image_base64']
            if case == 'theme-clean':
                self.assertNotEqual(before, selected)
                self.assertEqual(fixture.applied, 'Greybird')
            if not fixture.file_case:
                call(fixture, 'desktop_invoke', element_id=node['element_id'], action='activate')
                after = fixture.frame()['image_base64']
                self.assertEqual(selected == after, case in ('activation-no-effect', 'instant-clean'))
            response = asyncio.run(fixture.call('desktop_observe', {}))
            self.assertEqual(response.content[1].type, 'image')
            self.assertEqual(response.content[1].data, fixture.frame()['image_base64'])
            self.assertEqual(fixture.last_observation, fixture.state())
            self.assertTrue(fixture.history[-1]['observed'])

    def test_reviewed_png_digest_is_checked(self):
        manifest = ROOT / 'tests/fixtures/skill-outcomes/manifest.json'
        data = json.loads(manifest.read_text())
        for entry in data['states']:
            entry['screenshot'] = str(manifest.parent / entry['screenshot'])
        data['states'][0]['sha256'] = 'wrong'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'digest'):
                f.Fixture.from_manifest('theme', path)


class Protocol(unittest.TestCase):
    def test_real_mcp_initialize_list_call_and_error(self):
        async def exercise():
            fixture = f.Fixture('theme', states())
            server = f.make_server(fixture)
            async with create_client_server_memory_streams() as (client, backend):
                async with anyio.create_task_group() as group:
                    group.start_soon(server.run, backend[0], backend[1], server.create_initialization_options())
                    async with ClientSession(*client) as session:
                        initialized = await session.initialize()
                        self.assertEqual(initialized.serverInfo.name, 'luda-skill-effect-fixture')
                        declarations = await session.list_tools()
                        real = await f.real_mcp.list_tools()
                        self.assertEqual([t.model_dump() for t in declarations.tools], [t.model_dump() for t in real])
                        result = await session.call_tool('desktop_inspect', {'window_id': 'window'})
                        element = json.loads(result.content[0].text)['nodes'][-1]['element_id']
                        result = await session.call_tool('desktop_choose', {'element_id': element})
                        self.assertFalse(result.isError)
                        result = await session.call_tool('desktop_activate', {'window_id': 'window'})
                        self.assertTrue(result.isError)
                    group.cancel_scope.cancel()
        anyio.run(exercise)


if __name__ == '__main__':
    unittest.main()
