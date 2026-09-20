"""Exercise generated setup files through the actual pinned client, offline."""
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time
import unittest

from luda.setup import apply_changes, plan_setup

ROOT = Path(__file__).resolve().parents[3]


class SetupDiscoveryTests(unittest.TestCase):
    def test_real_cli_reads_generated_tools_and_discovers_complete_skill(self):
        executable = shutil.which('codex')
        self.assertIsNotNone(executable, 'The pinned runner must provide the Codex CLI')
        with tempfile.TemporaryDirectory(prefix='luda-setup-discovery-') as directory:
            home = Path(directory)
            config = home / '.codex'
            config.mkdir()
            # Literal paths are deliberate: discovery must not execute the server.
            command = ['/opt/luda/current/.venv/bin/luda-session', '--user', 'desktop-fixture', '--', '/opt/luda/current/.venv/bin/luda']
            changes, destinations = plan_setup(['codex'], home, ROOT / 'skills/luda', command, environ={})
            apply_changes(changes)
            # Do not inherit credentials, profile overrides, or a real user HOME.
            env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR') if key in os.environ}
            env.update(HOME=str(home), CODEX_HOME=str(config), USER='luda-test', LOGNAME='luda-test')
            result = subprocess.run([executable, 'mcp', 'get', 'luda', '--json'], env=env, cwd=home,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            server = json.loads(result.stdout)
            self.assertTrue(server['enabled'])
            self.assertEqual(server['transport']['command'], command[0])
            self.assertEqual(server['transport']['args'], command[1:])
            skill = destinations[0][2] / 'SKILL.md'
            with tempfile.TemporaryFile() as stderr:
                process = subprocess.Popen([executable, 'app-server'], env=env, cwd=home,
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
                selector = selectors.DefaultSelector()
                selector.register(process.stdout, selectors.EVENT_READ)
                buffer = b''
                def send(message):
                    process.stdin.write((json.dumps(message) + '\n').encode())
                    process.stdin.flush()
                def receive(identifier):
                    nonlocal buffer
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            if not line.strip():
                                continue
                            message = json.loads(line)
                            if message.get('id') == identifier:
                                self.assertNotIn('error', message, message)
                                return message['result']
                        if not selector.select(max(0, deadline - time.monotonic())):
                            break
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk:
                            stderr.seek(0)
                            self.fail('Codex app-server exited before response: ' + stderr.read().decode(errors='replace'))
                        buffer += chunk
                    self.fail(f'Codex app-server response {identifier} timed out')
                try:
                    send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'luda_setup_tests', 'version': '1'}, 'capabilities': {'experimentalApi': True}}})
                    receive(1)
                    send({'method': 'initialized', 'params': {}})
                    send({'id': 2, 'method': 'skills/list', 'params': {'cwds': [str(home)], 'forceReload': True}})
                    listing = receive(2)
                    entries = [entry for group in listing['data'] for entry in group['skills'] if entry['name'] == 'luda']
                    self.assertEqual(len(entries), 1, listing)
                    self.assertEqual(Path(entries[0]['path']), skill)
                    self.assertEqual(entries[0]['scope'], 'user')
                    self.assertTrue(entries[0]['enabled'])
                    self.assertEqual(skill.read_bytes(), (ROOT / 'skills/luda/SKILL.md').read_bytes())
                    self.assertTrue((skill.parent / 'references').is_dir())
                finally:
                    selector.close()
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                    process.stdin.close()
                    process.stdout.close()


if __name__ == '__main__':
    unittest.main()
