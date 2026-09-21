#!/usr/bin/env python3
"""Run isolated MCP skill trials and retain evidence for independent grading.

The same public appearance task can use an actual Luda server via --live-command.
Live reset and before/after independent oracles are required externally; this
runner alone never declares an acceptance pass or a live confirmation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from skill_decisions import ROOT, MODEL, context_text, digest, inspect_events, skill_files, stop_group, write_json

CASES = ('theme-clean', 'theme', 'instant-clean', 'select-only', 'select-already', 'activation-no-effect')
APPEARANCE_TASK = ('Use the desktop settings application to change the application appearance to a dark theme. '
                   'Report the exact theme you selected and leave its settings page visible. '
                   'Change the setting through the GUI, not shell commands or code.')
SELECTION_TASK = ('In the desktop file manager, go to /workspace/Selection trial and select target.txt so it is highlighted. '
                  'Do not open the document. Leave the file manager visible with that file selected. '
                  'Use the GUI for this task, not shell commands or code.')


def public_task(case: str) -> str:
    if case not in CASES and case != 'live-theme':
        raise ValueError('Unknown case')
    return SELECTION_TASK if case.startswith('select-') else APPEARANCE_TASK


def trace_contract(evidence: dict) -> bool:
    return all(event.get('item', {}).get('type') == 'mcp_tool_call'
               and event['item'].get('server') == 'luda'
               and event['item'].get('tool', '').startswith('desktop_')
               for event in evidence['tool_events'])


def run_interaction(case: str, skill: Path, out: Path, codex: str, timeout: float,
                    auth_home: Path, server: list[str], server_env: dict | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    (out / 'prompt.txt').write_text(public_task(case), encoding='utf-8')
    result = dict(case=case, model=MODEL, reasoning_override=None, timeout=False,
                  semantic_grade='ungraded', session_nonce=uuid.uuid4().hex,
                  mode='live' if case == 'live-theme' else 'fixture')
    with tempfile.TemporaryDirectory(prefix='luda-interaction-') as directory:
        base = Path(directory)
        home, workspace, config = base / 'home', base / 'workspace', base / 'codex'
        for path in (home, workspace, config):
            path.mkdir(mode=0o700)
        if (auth_home / 'auth.json').is_file():
            (config / 'auth.json').symlink_to((auth_home / 'auth.json').resolve())
        supplied = workspace / '.agents/skills/luda'
        for source in skill_files(skill):
            target = supplied / source.relative_to(skill)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        instructions = context_text(supplied)
        (out / 'supplied-context.txt').write_text(instructions, encoding='utf-8')
        result['installed_skill_hashes'] = {str(p.relative_to(supplied)): digest(p) for p in skill_files(supplied)}
        cmd = [codex, 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
               '--skip-git-repo-check', '--json', '--sandbox', 'read-only', '--model', MODEL,
               '-C', str(workspace), '-c', 'approval_policy="never"',
               '-c', 'features.shell_tool=false', '-c', 'features.multi_agent=false',
               '-c', 'developer_instructions=' + json.dumps(instructions),
               '-c', 'mcp_servers.luda.command=' + json.dumps(server[0]),
               '-c', 'mcp_servers.luda.args=' + json.dumps(server[1:]),
               '-c', 'mcp_servers.luda.required=true',
               '-c', 'mcp_servers.luda.startup_timeout_sec=30',
               '-c', 'mcp_servers.luda.tool_timeout_sec=30',
               '-c', 'mcp_servers.luda.default_tools_approval_mode="approve"']
        for key, value in (server_env or {}).items():
            # TOML quoted key preserves arbitrary valid environment variable names.
            cmd += ['-c', 'mcp_servers.luda.env.' + json.dumps(key) + '=' + json.dumps(value)]
        cmd += ['--output-last-message', str(out / 'final.txt'), '-']
        result['argv'] = cmd
        env = {k: v for k, v in os.environ.items() if k in (
            'PATH', 'LANG', 'LC_ALL', 'TERM', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
            'HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'NO_PROXY', 'OPENAI_API_KEY', 'CODEX_API_KEY')}
        env.update(HOME=str(home), CODEX_HOME=str(config), XDG_CONFIG_HOME=str(home / '.config'))
        started = time.monotonic()
        with (out / 'events.jsonl').open('wb') as events, (out / 'stderr.log').open('wb') as errors:
            try:
                process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=events, stderr=errors,
                                           env=env, start_new_session=True)
                try:
                    process.communicate(public_task(case).encode('utf-8'), timeout=timeout)
                except subprocess.TimeoutExpired:
                    result['timeout'] = True
                    stop_group(process)
                except BaseException:
                    stop_group(process)
                    raise
                result['returncode'] = process.returncode
            except OSError as exc:
                result['launch_error'] = str(exc)
        result['seconds'] = round(time.monotonic() - started, 3)
    evidence = inspect_events(out / 'events.jsonl')
    result.update(evidence)
    result['gui_tools_only'] = trace_contract(evidence)
    final = out / 'final.txt'
    result['status'] = ('timeout' if result['timeout'] else 'recorded'
                        if result.get('returncode') == 0 and result['turn_completed']
                        and final.is_file() and final.read_text().strip()
                        and not result['errors'] and not result['invalid_event_lines']
                        and result['gui_tools_only'] and result['tool_events']
                        and len(result['thread_ids']) == 1 else 'unassessable')
    oracle = out / 'oracle.json'
    if result['mode'] == 'fixture':
        if oracle.is_file():
            result['independent_state'] = json.loads(oracle.read_text())
        else:
            result['status'] = 'unassessable'
            result['oracle_error'] = 'Fixture did not persist independent state'
    else:
        result['live_verification'] = 'Required separately: independent initial/final settings and screenshots'
    result['artifact_hashes'] = {p.name: digest(p) for p in out.iterdir() if p.is_file()}
    write_json(out / 'result.json', result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill', type=Path, default=ROOT / 'skills/luda')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/skill-interactions')
    parser.add_argument('--captures', type=Path)
    parser.add_argument('--fixture-python', type=Path, default=ROOT / '.venv/bin/python')
    parser.add_argument('--case', choices=CASES, action='append', dest='selected')
    parser.add_argument('--timeout', type=float, default=240)
    parser.add_argument('--codex', default=shutil.which('codex') or 'codex')
    parser.add_argument('--auth-home', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')))
    parser.add_argument('--live-command', help='Actual Luda MCP server executable (external independent oracle required)')
    parser.add_argument('--live-arg', action='append', default=[])
    parser.add_argument('--live-env-file', type=Path, help='Explicit GUI environment JSON; do not include credentials')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    if args.live_command and (args.captures or args.selected):
        parser.error('--live-command excludes fixture cases/captures')
    if not args.live_command and not args.captures:
        parser.error('--captures required for fixture mode')
    out = args.output.resolve() / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex)
    out.mkdir(parents=True, mode=0o700)
    files = skill_files(args.skill)
    manifest = dict(model=MODEL, reasoning_override=None, runner_sha256=digest(Path(__file__)),
                    skill_hashes={str(p.relative_to(args.skill)): digest(p) for p in files},
                    grading='Independent semantic adjudication required; recorded is not passed', cases=[])
    try:
        manifest['cli_version'] = subprocess.run([args.codex, '--version'], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        write_json(out / 'batch.json', dict(manifest, status='blocked', reason=str(exc)))
        print(out)
        return 1
    if args.captures:
        manifest['captures_sha256'] = digest(args.captures)
        manifest['fixture_sha256'] = digest(ROOT / 'scripts/evaluation/skill_effect_fixture.py')
    cases = ['live-theme'] if args.live_command else args.selected or CASES
    write_json(out / 'batch.json', manifest)
    for case in cases:
        case_out = out / case
        server = ([args.live_command, *args.live_arg] if args.live_command else [
            str(args.fixture_python.resolve()), str(ROOT / 'scripts/evaluation/skill_effect_fixture.py'),
            '--case', case, '--captures', str(args.captures.resolve()), '--history', str(case_out / 'oracle.json')])
        server_env = json.loads(args.live_env_file.read_text()) if args.live_env_file else None
        result = run_interaction(case, args.skill, case_out, args.codex, args.timeout, args.auth_home, server, server_env)
        manifest['cases'].append(result)
        write_json(out / 'batch.json', manifest)
    print(out)
    return 0 if all(c['status'] == 'recorded' for c in manifest['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
