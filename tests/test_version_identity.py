"""Identities track actual discoverable schemas and artifact bytes, not locations."""
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from luda import server
from luda.identity import bundled_skill_identity, version_identity


class VersionIdentity(unittest.IsolatedAsyncioTestCase):
    async def test_public_doctor_identifies_actual_discovery_and_preserves_health(self):
        backend = Mock()
        backend.transaction.side_effect = nullcontext
        backend.doctor.return_value = {'ready': False, 'display_available': False, 'version': '0.1.0'}
        with patch.object(server, 'get_backend', return_value=backend):
            result = await server.mcp.call_tool('desktop_doctor', {})
        self.assertFalse(result.isError)
        payload = json.loads(result.content[0].text)
        self.assertFalse(payload['ready'])
        tools = [t.model_dump(mode='json', exclude_none=True) for t in await server.mcp.list_tools()]
        versions = payload['versions']
        self.assertEqual(versions, version_identity(tools))
        self.assertEqual(versions, version_identity(list(reversed(tools))))
        tools[0]['inputSchema']['properties']['new_option'] = {'type': 'boolean'}
        self.assertNotEqual(versions['tool_schema']['sha256'], version_identity(tools)['tool_schema']['sha256'])
        self.assertEqual(versions['driver_version'], server.version('luda'))

    def test_installed_and_editable_skill_bytes_and_unavailable_are_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);path = root/'skills/luda/SKILL.md';path.parent.mkdir(parents=True)
            content = '---\nname: luda\n---\n日本語 guidance\n'.encode();path.write_bytes(content)
            dist = Mock();dist.read_text.return_value = json.dumps({'url':root.as_uri(),'dir_info':{'editable':True}})
            editable = bundled_skill_identity(dist)
            self.assertEqual(editable['sha256'], hashlib.sha256(content).hexdigest())
            self.assertIn('does not identify', editable['scope'])
            dist.read_text.return_value = None;dist.files = [Path('../../../share/luda/skills/luda/SKILL.md')];dist.locate_file.return_value = path
            self.assertEqual(bundled_skill_identity(dist), editable)
            path.write_bytes(content+b'changed')
            self.assertNotEqual(bundled_skill_identity(dist)['sha256'], editable['sha256'])
            path.unlink()
            missing = bundled_skill_identity(dist)
            self.assertEqual(missing['status'], 'unavailable');self.assertNotIn(directory, json.dumps(missing))
            path.write_bytes(b'x'*262145)
            self.assertEqual(bundled_skill_identity(dist)['reason'], 'artifact_size_limit')


class CLIVersionIdentity(unittest.TestCase):
    def test_cli_and_public_doctor_share_identity_path_and_exit_contract(self):
        import asyncio
        from contextlib import redirect_stdout
        import io
        backend = Mock();backend.transaction.side_effect = nullcontext
        backend.doctor.side_effect = lambda: {'ready': True, 'version': server.version('luda')}
        with patch.object(server, 'get_backend', return_value=backend):
            public = json.loads(asyncio.run(server.desktop_doctor()).content[0].text)
            output = io.StringIO()
            with patch('sys.argv', ['luda', 'doctor']), redirect_stdout(output), self.assertRaises(SystemExit) as exit_result:
                server.main()
        self.assertEqual(exit_result.exception.code, 0)
        cli = json.loads(output.getvalue())
        self.assertEqual(cli['versions'], public['versions'])
        self.assertTrue(cli['ready'])

    def test_real_distribution_record_locates_installed_skill(self):
        from importlib.metadata import Distribution
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);info = root/'luda-0.1.0.dist-info';info.mkdir()
            (info/'METADATA').write_text('Metadata-Version: 2.1\nName: luda\nVersion: 0.1.0\n')
            (info/'RECORD').write_text('share/luda/skills/luda/SKILL.md,,\n')
            skill = root/'share/luda/skills/luda/SKILL.md';skill.parent.mkdir(parents=True)
            skill.write_bytes(b'installed artifact\n')
            dist = Distribution.at(info)
            self.assertEqual(bundled_skill_identity(dist)['sha256'], hashlib.sha256(skill.read_bytes()).hexdigest())
            for bad in ('[]', '{', '{"dir_info":true}', '{"url":123}'):
                (info/'direct_url.json').write_text(bad)
                self.assertEqual(bundled_skill_identity(dist)['status'], 'unavailable')

    def test_malformed_distribution_does_not_remove_ready_doctor(self):
        import asyncio
        backend = Mock();backend.transaction.side_effect = nullcontext
        backend.doctor.return_value = {'ready': True}
        broken = Mock();broken.version = None;broken.read_text.return_value = '[null]'
        with patch.object(server, 'get_backend', return_value=backend), patch('luda.identity.distribution', return_value=broken):
            result = asyncio.run(server.desktop_doctor())
        payload = json.loads(result.content[0].text)
        self.assertFalse(result.isError);self.assertTrue(payload['ready'])
        self.assertIsNone(payload['versions']['driver_version'])
        self.assertEqual(payload['versions']['bundled_skill']['status'], 'unavailable')
