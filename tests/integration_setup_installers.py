"""Exercise the bundled upstream installers in an explicitly disposable account.

No agent login, model, desktop or installed client executable is needed. The
caller provisions a managed runtime and an empty test account; never use a real
user profile. Actual client discovery is a separate pinned Codex CI contract.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = {
    'codex': ('.codex/config.toml', 'mcp_servers'),
    'claude-code': ('.claude.json', 'mcpServers'),
    'cursor': ('.cursor/mcp.json', 'mcpServers'),
    'gemini-cli': ('.gemini/settings.json', 'mcpServers'),
    'opencode': ('.config/opencode/opencode.jsonc', 'mcp'),
    'copilot-cli': ('.copilot/mcp-config.json', 'mcpServers'),
    'vscode': ('.config/Code/User/mcp.json', 'servers'),
}
SKILLS = ('.agents/skills', '.claude/skills')


def read_config(path):
    text = path.read_text()
    if path.suffix == '.toml':
        return tomllib.loads(text)
    # Test fixtures have no comments in strings; upstream JSONC may add comments.
    text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else ' ', text)
    return json.loads(re.sub(r',\s*([}\]])', r'\1', text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True, type=Path)
    parser.add_argument('--user', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    account = pwd.getpwnam(args.user)
    home = Path(account.pw_dir)
    if account.pw_uid == 0:
        parser.error('Select a disposable nonroot account, not root.')
    if os.getuid() not in (0, account.pw_uid):
        parser.error('Run as root or the selected disposable account.')
    for relative, _ in CONFIGS.values():
        if (home / relative).exists():
            parser.error('Test requires an empty agent profile: ' + str(home / relative))
    for relative in SKILLS:
        if (home / relative).exists():
            parser.error('Test requires empty skill directories: ' + str(home / relative))
    args.output.mkdir(parents=True, exist_ok=False)
    runtime = args.prefix / 'current/.venv/bin/luda'
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'USER': args.user,
           'LOGNAME': args.user, 'LANG': 'C.UTF-8', 'TMPDIR': str(home)}
    identity = ({'user': account.pw_uid, 'group': account.pw_gid,
                 'extra_groups': os.getgrouplist(args.user, account.pw_gid)}
                if os.getuid() == 0 else {})
    checks = []

    def run(label, *options, success=True, overrides=None):
        result = subprocess.run([str(runtime), 'setup', '--prefix', str(args.prefix),
                                 '--user', args.user, '--yes', *options],
                                cwd=home, env={**env, **(overrides or {})}, capture_output=True, text=True,
                                timeout=180, **identity)
        (args.output / (label + '.log')).write_text(result.stdout + result.stderr)
        assert (result.returncode == 0) == success, (label, result.returncode, result.stderr)
        checks.append(label)
        return result

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        if os.getuid() == 0:
            os.chown(path, account.pw_uid, account.pw_gid)
            for parent in path.parents:
                if parent == home:
                    break
                os.chown(parent, account.pw_uid, account.pw_gid)

    run('absent-agents', '--agent', 'all')
    expected_skill = {str(p.relative_to(ROOT / 'skills/luda')): p.read_bytes()
                      for p in (ROOT / 'skills/luda').rglob('*') if p.is_file()}
    baseline = {}
    for name, (relative, key) in CONFIGS.items():
        path = home / relative
        config = read_config(path)
        baseline[name] = config[key]['luda']
        assert str(args.prefix) in json.dumps(baseline[name]), (name, config)
        assert path.stat().st_uid == account.pw_uid
        # An unrelated server and unrelated root setting must survive upgrades.
        if name == 'codex':
            write(path, 'model = "fixture-model"\n\n' + path.read_text() +
                  '\n[mcp_servers.unrelated]\ncommand = "/usr/bin/true"\n')
        else:
            config['fixture_setting'] = {'keep': True}
            config[key]['unrelated'] = {'command': '/usr/bin/true'}
            config[key]['luda'] = {'command': 'previous-luda'}
            write(path, json.dumps(config))
    for relative in SKILLS:
        skill = home / relative / 'luda'
        assert {str(p.relative_to(skill)): p.read_bytes() for p in skill.rglob('*') if p.is_file()} == expected_skill, relative
        write(skill / 'stale.md', 'old Luda asset')
        write(skill.parent / 'unrelated/SKILL.md', 'unrelated skill: preserve')
    legacy = home / '.gemini/skills/luda'
    write(legacy / 'SKILL.md', 'old managed skill')
    edited = home / '.cursor/skills/luda'
    write(edited / 'SKILL.md', 'user edited skill')
    write(home / '.local/state/luda/setup.json', json.dumps({'version': 1, 'skills': {
        str(legacy): {'SKILL.md': hashlib.sha256(b'old managed skill').hexdigest()},
        str(edited): {'SKILL.md': hashlib.sha256(b'old managed skill').hexdigest()},
    }}))
    # Existing files are independent of whether the agent executable exists.
    run('existing-and-leftover-configs', '--agent', 'all')
    assert not legacy.exists()
    assert (edited / 'SKILL.md').read_text() == 'user edited skill'
    for name, (relative, key) in CONFIGS.items():
        config = read_config(home / relative)
        assert config[key]['luda'] == baseline[name], (name, config)
        assert config[key]['unrelated']['command'] == '/usr/bin/true'
        if name == 'codex':
            assert config.get('model') == 'fixture-model'
        else:
            assert config['fixture_setting'] == {'keep': True}
    for relative in SKILLS:
        skill = home / relative / 'luda'
        assert not (skill / 'stale.md').exists()
        assert (skill.parent / 'unrelated/SKILL.md').read_text() == 'unrelated skill: preserve'
        assert {str(p.relative_to(skill)): p.read_bytes() for p in skill.rglob('*') if p.is_file()} == expected_skill
    before = {n: read_config(home / p) for n, (p, _) in CONFIGS.items()}
    run('repeat', '--agent', 'all')
    assert before == {n: read_config(home / p) for n, (p, _) in CONFIGS.items()}
    project = home / 'project with spaces'
    project.mkdir()
    if os.getuid() == 0:
        os.chown(project, account.pw_uid, account.pw_gid)
    run('project', '--agent', 'claude-code', '--agent', 'codex', '--scope', 'project', '--project', str(project))
    assert read_config(project / '.mcp.json')['mcpServers']['luda']
    assert read_config(project / '.codex/config.toml')['mcp_servers']['luda']
    assert (project / '.claude/skills/luda/SKILL.md').read_bytes() == expected_skill['SKILL.md']
    assert (project / '.agents/skills/luda/SKILL.md').read_bytes() == expected_skill['SKILL.md']
    assert before == {n: read_config(home / p) for n, (p, _) in CONFIGS.items()}
    custom = home / 'custom-codex-profile'
    run('custom-profile', '--agent', 'codex', overrides={'CODEX_HOME': str(custom)})
    assert read_config(custom / 'config.toml')['mcp_servers']['luda'] == baseline['codex']
    export = home / 'exported-plugin'
    run('export', '--export', str(export))
    assert (export / 'skills/luda/SKILL.md').read_bytes() == expected_skill['SKILL.md']
    assert read_config(export / 'mcp.json')['mcpServers']['luda']['command']
    # Failures must not be reported as successful registrations or alter configs.
    for name, (relative, _) in CONFIGS.items():
        broken = home / relative
        write(broken, '{malformed')
        run('malformed-' + name, '--agent', name, success=False)
        assert broken.read_text() == '{malformed', name
    result = {'passed': True, 'checks': checks, 'agents': list(CONFIGS),
              'skill_files': len(expected_skill), 'uid': account.pw_uid,
              'skill_sha256': hashlib.sha256(expected_skill['SKILL.md']).hexdigest(),
              'scope': 'Real bundled skills/add-mcp CLI writes and independent file assertions; no client login or desktop-action claim.'}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
