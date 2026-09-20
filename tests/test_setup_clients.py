import json
import tomllib
import unittest

from luda.setup_clients import CLIENTS, _clean_json, render_config


class SetupClientTests(unittest.TestCase):
    def render(self, name, original=None, **kwargs):
        return render_config(CLIENTS[name], original, '/opt/luda/current/.venv/bin/luda-session', ['--user', 'alice', '--', '/opt/luda/current/.venv/bin/luda'], **kwargs)

    def parse(self, name, content):
        return tomllib.loads(content.decode()) if name == 'codex' else json.loads(_clean_json(content.decode(), True))

    def test_all_client_configs_are_idempotent_and_have_correct_commands(self):
        for name, client in CLIENTS.items():
            with self.subTest(client=name):
                content = self.render(name)
                self.assertEqual(content, self.render(name, content))
                entry = self.parse(name, content)[client.server_key]['luda']
                if name == 'opencode':
                    self.assertEqual(entry['command'][1:3], ['--user', 'alice'])
                    self.assertEqual(entry['type'], 'local')
                else:
                    self.assertEqual(entry['args'][:2], ['--user', 'alice'])
                self.assertTrue(client.project_config)
                self.assertTrue(client.project_skill)

    def test_conflicting_registration_is_not_overwritten(self):
        for name in CLIENTS:
            with self.subTest(client=name):
                content = self.render(name)
                with self.assertRaisesRegex(ValueError, 'different luda'):
                    render_config(CLIENTS[name], content, 'other', [])

    def test_toml_preserves_comments_and_other_server(self):
        original = b'# user comment\nmodel = "example"\n[mcp_servers.other]\ncommand = "other"\n'
        result = self.render('codex', original)
        self.assertTrue(result.startswith(original))
        self.assertEqual(self.parse('codex', result)['model'], 'example')
        self.assertEqual(self.parse('codex', result)['mcp_servers']['other'], {'command': 'other'})

    def test_toml_inline_table_refused_without_reserializing(self):
        with self.assertRaisesRegex(ValueError, 'safely merge'):
            self.render('codex', b'mcp_servers = {}\n')

    def test_json_preserves_existing_data_and_whitespace(self):
        original = b'{"projects":{"/some/path":{"allowedTools":["x"]}}, "mcpServers": { "other": {"command":"existing"} }}\n'
        result = self.render('claude-code', original)
        self.assertIn(b'"projects":{"/some/path":{"allowedTools":["x"]}}', result)
        self.assertIn(b'"other": {"command":"existing"}', result)
        self.assertEqual(self.parse('claude-code', result)['projects']['/some/path']['allowedTools'], ['x'])

    def test_jsonc_nested_and_root_insertion_preserves_comments(self):
        for original in (
            b'{ // title\n "servers": { "other": {"command":"hello"}, /* keep */ },\n "inputs": [],\n}\n',
            b'{"inputs": [], // keep root\n}\n',
            b'{/* empty */}',
            b'{"servers": {/* empty */}}',
            b'{"servers": {"other": {"args":["//not comment", "/*string*/", "\\\"}"]}}}',
        ):
            with self.subTest(original=original):
                result = self.render('vscode', original)
                self.assertEqual(self.render('vscode', result), result)
                for comment in (b'// title', b'/* keep */', b'// keep root', b'/* empty */'):
                    if comment in original:
                        self.assertIn(comment, result)
                before = self.parse('vscode', original)
                after = self.parse('vscode', result)
                after.get('servers', {}).pop('luda')
                if 'servers' not in before:
                    after.pop('servers')
                self.assertEqual(before, after)

    def test_malformed_duplicate_and_wrong_types_refused(self):
        for content in (b'[]', b'{', b'{"mcpServers":null}', b'{"mcpServers":[]}', b'{"x":1,"x":2}', b'{"mcpServers":{"luda":1,"luda":2}}'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.render('cursor', content)

    def test_json_does_not_silently_accept_jsonc(self):
        with self.assertRaises(ValueError):
            self.render('cursor', b'{/* comment */}')

    def test_string_values_are_encoded_without_shell_interpretation(self):
        for name in CLIENTS:
            result = render_config(CLIENTS[name], None, '/a path/$(false)', ['a"b', 'a\nb', '雪😀'], {'KEY': 'quoted"\ntext'})
            entry = self.parse(name, result)[CLIENTS[name].server_key]['luda']
            self.assertEqual(entry['environment' if name == 'opencode' else 'env']['KEY'], 'quoted"\ntext')
            self.assertEqual(entry['command'][0] if name == 'opencode' else entry['command'], '/a path/$(false)')

    def test_shared_claude_copilot_project_config_is_compatible(self):
        result = self.render('claude-code')
        self.assertEqual(result, self.render('copilot-cli', result))

    def test_copilot_bare_map_requires_manual_setup(self):
        with self.assertRaisesRegex(ValueError, 'bare server map'):
            self.render('copilot-cli', b'{"other": {"command": "keep"}}')

    def test_toml_trailing_blank_lines_preserved(self):
        original = b'# preserve exactly\n\n\n'
        self.assertTrue(self.render('codex', original).startswith(original))

    def test_nul_and_bad_command_values_refused(self):
        for command, args in (('', []), ('x\0', []), ('x', ['\0']), ('x', [1])):
            with self.assertRaises(ValueError):
                render_config(CLIENTS['codex'], None, command, args)


if __name__ == '__main__':
    unittest.main()
