"""Pure, non-destructive configuration adapters for standard Linux agent profiles.

These adapters describe configuration formats, not end-to-end client qualification.
No client executable, JavaScript runtime, network request, or filesystem mutation is
needed to render a setup plan. Custom profiles are resolved by the setup caller.
"""
from dataclasses import dataclass
import json
import re
import tomllib


@dataclass(frozen=True)
class Client:
    name: str
    label: str
    config: str
    skill: str
    format: str = 'json'
    server_key: str = 'mcpServers'
    executable: str = ''
    project_config: str | None = None
    project_skill: str | None = None


CLIENTS = {c.name: c for c in (
    Client('codex', 'Codex', '.codex/config.toml', '.agents/skills', 'toml', 'mcp_servers', 'codex', '.codex/config.toml', '.agents/skills'),
    Client('claude-code', 'Claude Code', '.claude.json', '.claude/skills', executable='claude', project_config='.mcp.json', project_skill='.claude/skills'),
    Client('cursor', 'Cursor', '.cursor/mcp.json', '.cursor/skills', executable='cursor', project_config='.cursor/mcp.json', project_skill='.cursor/skills'),
    Client('gemini-cli', 'Gemini CLI', '.gemini/settings.json', '.gemini/skills', executable='gemini', project_config='.gemini/settings.json', project_skill='.gemini/skills'),
    Client('opencode', 'OpenCode', '.config/opencode/opencode.json', '.config/opencode/skills', 'jsonc', 'mcp', 'opencode', 'opencode.json', '.opencode/skills'),
    Client('vscode', 'VS Code (default local Linux profile)', '.config/Code/User/mcp.json', '.copilot/skills', 'jsonc', 'servers', 'code', '.vscode/mcp.json', '.github/skills'),
    Client('copilot-cli', 'GitHub Copilot CLI', '.copilot/mcp-config.json', '.copilot/skills', executable='copilot', project_config='.mcp.json', project_skill='.github/skills'),
)}

ALIASES = {'claude': 'claude-code', 'gemini': 'gemini-cli', 'copilot': 'copilot-cli'}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Configuration contains duplicate keys; resolve them before setup.')
        result[key] = value
    return result


def _clean_json(text: str, comments: bool) -> str:
    """Blank comments/trailing commas without changing string or character offsets."""
    if not comments:
        return text
    pattern = re.compile(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/')
    clean = pattern.sub(lambda m: m[0] if m[0].startswith('"') else ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)
    return re.sub(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])', lambda m: ' ' if m[0] == ',' else m[0], clean)


def _members(clean: str, start: int):
    """Return object closing offset and members' value spans in validated JSON."""
    decoder = json.JSONDecoder()
    pos = start + 1
    members = {}
    while True:
        while clean[pos].isspace() or clean[pos] == ',':
            pos += 1
        if clean[pos] == '}':
            return pos, members
        key, pos = decoder.raw_decode(clean, pos)
        while clean[pos].isspace() or clean[pos] == ':':
            pos += 1
        begin = pos
        _, pos = decoder.raw_decode(clean, pos)
        members[key] = (begin, pos)


def _insert_member(text: str, clean: str, start: int, key: str, value) -> str:
    close, members = _members(clean, start)
    entry = json.dumps(key) + ': ' + json.dumps(value, indent=2, ensure_ascii=True)
    # Insert before the final brace, preserving all original comments and bytes.
    # An existing JSONC trailing comma already separates the new entry.
    if members:
        end = list(members.values())[-1][1]
        tail = _clean_json(text[end:close], True)
        has_comma = ',' in tail
        if not has_comma:
            text = text[:end] + ',' + text[end:]
            close += 1
    return text[:close] + '\n' + entry + '\n' + text[close:]


def render_config(client: Client, original: bytes | None, command: str,
                  args: list[str], env: dict[str, str] | None = None) -> bytes:
    """Add Luda only when absent; identical setup preserves exact original bytes.

    Existing differing registrations, malformed documents, duplicate keys and
    unsupported TOML inline layouts fail closed. No configuration is overwritten.
    """
    if not command or not isinstance(command, str) or '\x00' in command:
        raise ValueError('A nonempty executable is required.')
    if not isinstance(args, list) or any(not isinstance(a, str) or '\x00' in a for a in args):
        raise ValueError('Arguments must be strings without NUL bytes.')
    if env is not None and (not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str) or '\x00' in k + v for k, v in env.items())):
        raise ValueError('Environment must map strings to strings without NUL bytes.')
    entry = {'command': command, 'args': args}
    if client.name == 'opencode':
        entry = {'type': 'local', 'command': [command, *args], 'enabled': True}
    elif client.name in ('claude-code', 'vscode', 'copilot-cli'):
        entry['type'] = 'stdio'
    if env:
        entry['environment' if client.name == 'opencode' else 'env'] = env
    text = (original or b'').decode('utf-8')
    try:
        if client.format == 'toml':
            data = tomllib.loads(text)
        else:
            clean = _clean_json(text or '{}', client.format == 'jsonc')
            data = json.loads(clean, object_pairs_hook=_unique)
        if not isinstance(data, dict):
            raise ValueError('Configuration must be an object.')
        if client.name == 'copilot-cli' and client.server_key not in data and any(isinstance(v, dict) and ('command' in v or 'url' in v) for v in data.values()):
            raise ValueError('Existing Copilot bare server map requires manual setup; do not mix configuration formats.')
        servers = data.get(client.server_key, {})
        if not isinstance(servers, dict):
            raise ValueError('MCP server configuration must be an object.')
        if 'luda' in servers:
            if servers['luda'] == entry:
                return original or b''
            raise ValueError('A different luda registration already exists; review it before setup.')
        if client.format == 'toml':
            block = '\n[mcp_servers.luda]\n' + '\n'.join(f'{k} = {json.dumps(v, ensure_ascii=False)}' for k, v in entry.items() if k != 'env') + '\n'
            if env:
                block += '\n[mcp_servers.luda.env]\n' + '\n'.join(f'{json.dumps(k, ensure_ascii=False)} = {json.dumps(v, ensure_ascii=False)}' for k, v in env.items()) + '\n'
            result = text + ('\n' if text and not text.endswith('\n') else '') + block
            # Detect sealed inline parent tables and any unsupported TOML layout.
            parsed = tomllib.loads(result)
        else:
            text = text or '{}\n'
            clean = _clean_json(text, client.format == 'jsonc')
            start = len(clean) - len(clean.lstrip())
            _, members = _members(clean, start)
            if client.server_key in members:
                result = _insert_member(text, clean, members[client.server_key][0], 'luda', entry)
            else:
                result = _insert_member(text, clean, start, client.server_key, {'luda': entry})
            parsed = json.loads(_clean_json(result, client.format == 'jsonc'), object_pairs_hook=_unique)
        expected = dict(data)
        expected[client.server_key] = {**servers, 'luda': entry}
        if parsed != expected:
            raise ValueError('Configuration merge did not preserve existing settings.')
        return result.encode('utf-8')
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError('Cannot safely merge this configuration; correct its syntax or use manual setup.') from exc
