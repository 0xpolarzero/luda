#!/usr/bin/env python3
"""Record fresh Codex decisions; semantic grading is a separate evaluator step.

Only the public case file is read. No rubric is loaded or copied into sessions.
Outputs intentionally retain synthetic prompts and model responses for evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
MODEL = 'gpt-5.6-sol'
REFERENCE_NAMES = {'setup.md', 'targeting.md', 'text.md', 'workflows.md', 'optional.md', 'controls.md', 'recovery.md'}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if set(data) != {'schema_version', 'cases'} or data['schema_version'] != 1:
        raise ValueError('Expected public cases schema version 1')
    seen = set()
    for case in data['cases']:
        if (set(case) != {'id', 'public_prompt'} or not re.fullmatch(r'case-\d{2}', case['id'])
                or not isinstance(case['public_prompt'], str) or not case['public_prompt']
                or case['id'] in seen):
            raise ValueError('Invalid public case or private criteria included')
        seen.add(case['id'])
    if not seen:
        raise ValueError('No public cases')
    return data['cases']


def skill_files(skill: Path) -> list[Path]:
    refs = sorted((skill / 'references').glob('*.md'))
    if {p.name for p in refs} != REFERENCE_NAMES or not (skill / 'SKILL.md').is_file():
        raise ValueError('Expected entry skill and seven reference guides')
    return [skill / 'SKILL.md', *refs]


def context_text(skill: Path) -> str:
    return '\n\n'.join(f'--- {p.relative_to(skill)} ---\n{p.read_text(encoding="utf-8")}'
                       for p in skill_files(skill))


def inspect_events(path: Path) -> dict:
    threads, errors, tool_events = [], [], []
    complete = False
    invalid_lines = 0
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            invalid_lines += 1
            continue
        if not isinstance(event, dict):
            invalid_lines += 1
            continue
        if event.get('type') == 'thread.started':
            threads.append(event.get('thread_id'))
        if event.get('type') == 'turn.completed':
            complete = True
        if event.get('type') in ('error', 'turn.failed'):
            errors.append(event)
        item = event.get('item') or {}
        if not isinstance(item, dict):
            invalid_lines += 1
            continue
        if item.get('type') in ('command_execution', 'mcp_tool_call', 'web_search', 'file_change', 'tool_call'):
            tool_events.append(event)
    return dict(thread_ids=threads, turn_completed=complete, errors=errors,
                tool_events=tool_events, invalid_event_lines=invalid_lines)


def stop_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_case(case: dict, skill: Path, output: Path, codex: str, timeout: float,
             auth_home: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    prompt = case['public_prompt']
    (output / 'prompt.txt').write_text(prompt, encoding='utf-8')
    result = dict(case_id=case['id'], model=MODEL, reasoning_override=None,
                  timeout=False, status='not_started', semantic_grade='ungraded',
                  session_nonce=uuid.uuid4().hex)
    # Temporary home prevents inherited skills, instructions, plugins, MCP, and history.
    # Authentication remains local and is never copied into retained artifacts.
    with tempfile.TemporaryDirectory(prefix='luda-decision-') as directory:
        base = Path(directory)
        home, workspace, config = base / 'home', base / 'workspace', base / 'codex'
        for path in (home, workspace, config):
            path.mkdir(mode=0o700)
        if (auth_home / 'auth.json').is_file():
            (config / 'auth.json').symlink_to((auth_home / 'auth.json').resolve())
        supplied = workspace / 'luda'
        supplied.mkdir()
        for source in skill_files(skill):
            target = supplied / source.relative_to(skill)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        instructions = context_text(supplied)
        (output / 'supplied-context.txt').write_text(instructions, encoding='utf-8')
        cmd = [codex, 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
               '--skip-git-repo-check', '--json', '--sandbox', 'read-only',
               '--model', MODEL, '-C', str(workspace), '-c', 'approval_policy="never"',
               '-c', 'features.shell_tool=false', '-c', 'features.multi_agent=false',
               '-c', 'developer_instructions=' + json.dumps(instructions),
               '--output-last-message', str(output / 'final.txt'), '-']
        result['argv'] = cmd
        env = {k: v for k, v in os.environ.items()
               if k in ('PATH', 'LANG', 'LC_ALL', 'TERM', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
                        'HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'NO_PROXY',
                        'OPENAI_API_KEY', 'CODEX_API_KEY')}
        env.update(HOME=str(home), CODEX_HOME=str(config), XDG_CONFIG_HOME=str(home / '.config'))
        start = time.monotonic()
        with (output / 'events.jsonl').open('wb') as events, (output / 'stderr.log').open('wb') as errors:
            try:
                process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=events,
                                           stderr=errors, env=env, start_new_session=True)
                try:
                    process.communicate(prompt.encode('utf-8'), timeout=timeout)
                except subprocess.TimeoutExpired:
                    result['timeout'] = True
                    stop_group(process)
                except BaseException:
                    stop_group(process)
                    raise
                result['returncode'] = process.returncode
            except OSError as exc:
                result['launch_error'] = str(exc)
        result['seconds'] = round(time.monotonic() - start, 3)
    result.update(inspect_events(output / 'events.jsonl'))
    final = output / 'final.txt'
    result['status'] = ('timeout' if result['timeout'] else 'recorded'
                        if result.get('returncode') == 0 and result['turn_completed']
                        and final.is_file() and final.read_text().strip() and not result['errors']
                        and not result['tool_events'] and not result['invalid_event_lines']
                        and len(result['thread_ids']) == 1 else 'unassessable')
    result['artifact_hashes'] = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    write_json(output / 'result.json', result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=ROOT / 'tests/fixtures/skill-outcomes/public-cases.json')
    parser.add_argument('--skill', type=Path, default=ROOT / 'skills/luda')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/skill-decisions')
    parser.add_argument('--case', action='append', dest='selected')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--codex', default=shutil.which('codex') or 'codex')
    parser.add_argument('--auth-home', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')))
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    cases = load_cases(args.cases)
    if args.selected:
        if set(args.selected) - {c['id'] for c in cases}:
            parser.error('Unknown case ID')
        cases = [c for c in cases if c['id'] in args.selected]
    files = skill_files(args.skill)
    out = args.output.resolve() / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex)
    out.mkdir(parents=True, mode=0o700)
    try:
        version = subprocess.run([args.codex, '--version'], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        write_json(out / 'batch.json', {'status': 'blocked', 'reason': str(exc)})
        print(out)
        return 1
    manifest = dict(schema_version=1, model=MODEL, cli_version=version, reasoning_override=None,
                    runner_sha256=digest(Path(__file__)), public_cases_sha256=digest(args.cases),
                    skill_hashes={str(p.relative_to(args.skill)): digest(p) for p in files},
                    grading='Human semantic grading required; recorded is not passed', cases=[])
    write_json(out / 'batch.json', manifest)
    for case in cases:
        result = run_case(case, args.skill, out / case['id'], args.codex, args.timeout, args.auth_home)
        manifest['cases'].append(result)
        write_json(out / 'batch.json', manifest)
    print(out)
    return 0 if all(c['status'] == 'recorded' for c in manifest['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
