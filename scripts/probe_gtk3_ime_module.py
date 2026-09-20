#!/usr/bin/env python3
"""Build/run read-only GTK3 module prototype; no module installation or config edits."""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def private_session(command, **kwargs):
    process = subprocess.Popen(command, start_new_session=True, **kwargs)
    try:
        if process.wait(timeout=15):
            raise subprocess.CalledProcessError(process.returncode, command)
    finally:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error('Run as an ordinary account; uses an owned private Xvfb session.')
    out = args.output.resolve(); out.mkdir(mode=0o700, parents=False, exist_ok=False)
    module = out / 'ime-observer.so'
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gtk+-3.0'], text=True))
    subprocess.run(['gcc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', '-o', str(module),
                    str(ROOT / 'tests/prototypes/gtk3_ime_observer.c'), *flags], check=True, timeout=30)
    results = {}
    for mode in ('startup', 'late', 'mousepad'):
        with (out / (mode + '.jsonl')).open('xb') as stream, (out / (mode + '.log')).open('xb') as log:
            env = dict(os.environ, LUDA_IME_PROBE_FD=str(stream.fileno()), GTK_IM_MODULE='gtk-im-context-simple')
            private = out / mode; private.mkdir(mode=0o700)
            env.update(HOME=str(private), XDG_CONFIG_HOME=str(private/'config'), XDG_CACHE_HOME=str(private/'cache'), XDG_DATA_HOME=str(private/'data'))
            env.pop('GTK_MODULES', None); env.pop('GTK3_MODULES', None)
            if mode == 'startup': env['GTK3_MODULES'] = str(module)
            fixture_args = ([str(ROOT / 'tests/prototypes/gtk3_ime_mousepad.py'), str(out), str(module)] if mode == 'mousepad' else
                            [str(ROOT / 'tests/prototypes/gtk3_ime_fixture.py'), str(out / (mode + '.oracle.json')), mode, str(module)])
            private_session(['xvfb-run', '-a', '-s', '-screen 0 800x600x24 -nolisten tcp',
                            'dbus-run-session', '--', '/usr/bin/python3',
                            *fixture_args], env=env, pass_fds=(stream.fileno(),), stdout=log, stderr=log)
        events = [json.loads(line) for line in (out / (mode + '.jsonl')).read_text().splitlines()]
        oracle = json.loads((out / (mode + '.oracle.json')).read_text())
        if mode == 'mousepad':
            assert oracle['file_unchanged'] and set(oracle['context_public_properties']) == {'input-purpose', 'input-hints'}
            assert any(item['event'] == 'start' for item in events)
            assert any(item['event'] == 'end' for item in events)
            results[mode] = {'events':len(events), 'all_assertions_passed':True, **oracle}
            continue
        assert oracle['synthetic_lifecycle_completed'] and oracle['committed_unchanged']
        assert events[0]['event'] == 'attached' and not events[0]['process_known']
        assert all(not item['field_identity_known'] for item in events)
        assert all(item['process_active'] is not False for item in events)
        starts = [item for item in events if item['event'] == 'start']
        assert starts and all(item['context_known'] and item['context_active'] for item in starts)
        destroyed = [item for item in events if item['event'] == 'destroyed']
        assert len(destroyed) >= 2
        assert any(item['event'] == 'changed' and not item['context_known'] for item in events)
        controlled = destroyed[-2]['context_generation']
        changed = [item for item in events if item['context_generation'] == controlled and item['event'] == 'changed']
        assert len(changed) == 2 and not changed[0]['context_known'] and changed[1]['context_active']
        assert destroyed[-1]['context_active'] is True and destroyed[-1]['observed_active_contexts'] == 0
        assert len({item['context_generation'] for item in destroyed}) == len(destroyed)
        if mode == 'late':
            assert oracle['late_active_before_attach']
            assert events[1]['event'] != 'start', events
        else:
            # First real GTK3 preedit precedes the explicitly synthetic contexts.
            assert len(starts) >= 4, events
        results[mode] = {'events': len(events), 'distinct_context_generations': len({item['context_generation'] for item in events}) - 1,
                         'all_assertions_passed': True}
    results['scope'] = 'Read-only hook prototype; process inactive and exact field identity remain unknown.'
    results['gtk_version'] = subprocess.check_output(['pkg-config', '--modversion', 'gtk+-3.0'], text=True).strip()
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results))

if __name__ == '__main__': main()
