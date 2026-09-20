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
