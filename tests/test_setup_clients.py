"""Public IDs remain stable while upstream owns configuration formats."""
import unittest
from luda.setup_clients import CLIENTS


class ClientTests(unittest.TestCase):
    def test_seven_public_clients_map_to_upstream_installers(self):
        self.assertEqual(set(CLIENTS), {'codex', 'claude-code', 'cursor', 'gemini-cli', 'opencode', 'vscode', 'copilot-cli'})
        self.assertEqual(CLIENTS['vscode'].skills_agent, 'github-copilot')
        self.assertEqual(CLIENTS['vscode'].mcp_agent, 'vscode')
        self.assertEqual(CLIENTS['copilot-cli'].skills_agent, 'github-copilot')
        self.assertEqual(CLIENTS['copilot-cli'].mcp_agent, 'github-copilot-cli')
        for client in CLIENTS.values():
            self.assertTrue(client.label)
            self.assertTrue(client.executable)


if __name__ == '__main__':
    unittest.main()
