"""Ten-minute private ordinary-user MCP soak; shorter runs are smoke tests only."""
import argparse
import asyncio
import base64
from collections import defaultdict
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from headless_tests import stop
from qualification_matrix import private_environment, owned_processes, cleanup_owned
from qualify import source_fingerprint


def usage(pid):
    base = Path('/proc') / str(pid)
    status = base.joinpath('status').read_text().splitlines()
    fields = {line.split(':', 1)[0]: line.split(':', 1)[1].strip() for line in status if ':' in line}
    children = set()
    for task in base.joinpath('task').iterdir():
        children.update(int(value) for value in task.joinpath('children').read_text().split())
    return {'pid': pid, 'fds': len(list(base.joinpath('fd').iterdir())),
            'rss_kib': int(fields['VmRSS'].split()[0]), 'threads': int(fields['Threads']),
            'children': sorted(children)}


def descendants(pid):
    pending = list(usage(pid)['children']); result = []
    while pending:
        child = pending.pop()
        try:
            row = usage(child)
            row['name'] = Path('/proc', str(child), 'comm').read_text().strip()
            result.append(row); pending.extend(row['children'])
        except (FileNotFoundError, ProcessLookupError):
            pass
    return result


def metrics(values):
    ordered = sorted(values)
    return {'count': len(values), 'minimum': min(values), 'median': statistics.median(values),
            'p95': ordered[min(len(ordered)-1, int(len(ordered)*.95))], 'maximum': max(values)}


async def child(seconds, interval, out):
    out.mkdir(parents=True, exist_ok=True)
    durations = defaultdict(list); samples = []; calls = 0
    wm = None; app = None; server_pid = None
    began = time.monotonic(); result = {'status': 'failed', 'requested_seconds': seconds}
    source_before = source_fingerprint(ROOT)
    try:
        with tempfile.TemporaryDirectory(prefix='luda-soak-fixture-') as directory:
            fixture_dir = Path(directory)
            with (out/'desktop.log').open('w') as desktop_log:
                wm = subprocess.Popen(['xfwm4', '--compositor=off'], stdout=desktop_log, stderr=desktop_log)
                deadline = time.monotonic()+5
                while subprocess.run(['wmctrl', '-m'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                    assert time.monotonic()<deadline, 'private WM unavailable'
                    await asyncio.sleep(.05)
                app = subprocess.Popen(['/usr/bin/python3', str(ROOT/'tests/fixture.py'), directory], stdout=desktop_log, stderr=desktop_log)
                async def oracle(text, clicks):
                    deadline = time.monotonic()+3
                    while time.monotonic()<deadline:
                        try:
                            state = json.loads((fixture_dir/'state.json').read_text())
                            if state['text']==text and state['clicks']==clicks:
                                return state
                        except (FileNotFoundError, json.JSONDecodeError):
                            pass
                        await asyncio.sleep(.02)
                    raise AssertionError(f'Independent application mismatch at action count {clicks}')

                parameters = StdioServerParameters(command=sys.executable,
                    args=[__file__, '--server-child', str(out/'server.pid')], env=dict(os.environ))
                async with stdio_client(parameters) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        server_pid = int((out/'server.pid').read_text())
                        async def call(name, **arguments):
                            nonlocal calls
                            start = time.monotonic()
                            response = await session.call_tool(name, arguments)
                            elapsed = (time.monotonic()-start)*1000
                            payload = json.loads(next(block.text for block in response.content if block.type=='text'))
                            calls += 1; durations[name].append(elapsed)
                            with (out/'requests.jsonl').open('a') as log:
                                log.write(json.dumps({'index': calls, 'tool': name, 'elapsed_ms': elapsed,
                                    'ok': not response.isError, 'effect': payload.get('effect'), 'code': payload.get('code')})+'\n')
                            assert not response.isError and payload.get('ok', True), (name, payload)
                            return payload, response
                        owner = None
                        for _ in range(100):
                            windows, _ = await call('desktop_windows')
                            owner = next((row for row in windows['windows'] if row['pid']==app.pid), None)
                            if owner: break
                            await asyncio.sleep(.05)
                        assert owner, 'owned fixture unavailable'
                        wid = owner['window_id']; await call('desktop_activate', window_id=wid)
                        doctor, _ = await call('desktop_doctor')
                        assert os.getuid()!=0
                        workload_start = time.monotonic(); next_progress = workload_start+60; iteration = 0
                        expected_text = ''; expected_clicks = 0; observed_nodes = 0
                        while time.monotonic()-workload_start < seconds:
                            iteration_start = time.monotonic()
                            tree, _ = await call('desktop_inspect', window_id=wid, limit=100)
                            observed_nodes += len(tree['nodes'])
                            nodes = {row['name']: row for row in tree['nodes'] if row['name']}
                            entry = nodes['Contract text']['element_id']; button = nodes['Record action']['element_id']
                            expected_text = f'Soak {iteration}: 日本語 👩🏽‍💻\nsecond line\tend'
                            await call('desktop_type', element_id=entry, text=expected_text, mode='replace')
                            if iteration%10==0:
                                expected_text += '\nclipboard replacement'
                                await call('desktop_focus_element', element_id=entry)
                                await call('desktop_press_keys', window_id=wid, chord='ctrl+a')
                                await call('desktop_paste', window_id=wid, text=expected_text)
                            readback, _ = await call('desktop_read_text', element_id=entry)
                            assert readback['text']==expected_text
                            await call('desktop_invoke', element_id=button)
                            expected_clicks += 1
                            await oracle(expected_text, expected_clicks)
                            snapshot, response = await call('desktop_observe', max_width=640)
                            assert snapshot['image_size']['width']==640
                            if iteration==0:
                                (out/'first.png').write_bytes(base64.b64decode(next(block.data for block in response.content if block.type=='image')))
                            del snapshot, response, tree, nodes
                            await asyncio.sleep(.05)  # sample quiescent request boundaries
                            sample = {'iteration': iteration, 'elapsed_seconds': time.monotonic()-workload_start,
                                'server': usage(server_pid), 'client': usage(os.getpid()),
                                'server_descendants': descendants(server_pid),
                                'private_process_count': len(owned_processes(os.environ['LUDA_MATRIX_PROCESS_TOKEN']))}
                            # One intentional clipboard owner can persist. Completed
                            # AX/capture/input helper processes must not accumulate.
                            assert len(sample['server_descendants'])<=1, sample
                            assert all(row['name']=='xclip' for row in sample['server_descendants']), sample
                            assert sample['server']['fds']<=64 and sample['server']['rss_kib']<512*1024, sample
                            samples.append(sample)
                            with (out/'samples.jsonl').open('a') as log: log.write(json.dumps(sample)+'\n')
                            iteration += 1
                            if time.monotonic()>=next_progress:
                                print(json.dumps({'progress_seconds': round(sample['elapsed_seconds'], 1), 'iterations': iteration,
                                    'requests': calls, 'server_fds': sample['server']['fds'], 'server_rss_kib': sample['server']['rss_kib']}), flush=True)
                                next_progress += 60
                            await asyncio.sleep(max(0, interval-(time.monotonic()-iteration_start)))
                        workload_seconds = time.monotonic()-workload_start
                        # No more input. Repeated independent app reads establish a
                        # measured idle window, not a guarantee about all late actions.
                        for _ in range(30):
                            await asyncio.sleep(.1); await oracle(expected_text, expected_clicks)
                        status, _ = await call('desktop_status')
                        assert not status.get('recovering'), status
                        _, response = await call('desktop_observe', max_width=640)
                        (out/'last.png').write_bytes(base64.b64decode(next(block.data for block in response.content if block.type=='image')))
                        before_disconnect = usage(server_pid)
                # stdio context exits normally: server + clipboard owner must exit.
                deadline = time.monotonic()+5
                while Path('/proc', str(server_pid)).exists() and time.monotonic()<deadline:
                    await asyncio.sleep(.05)
                assert not Path('/proc', str(server_pid)).exists(), 'MCP server survived transport close'
                for _ in range(20):
                    await asyncio.sleep(.1); await oracle(expected_text, expected_clicks)
                lingering = [pid for pid in owned_processes(os.environ['LUDA_MATRIX_PROCESS_TOKEN'])
                    if Path('/proc', str(pid), 'comm').read_text().strip()=='xclip']
                assert not lingering, lingering
                steady = samples[min(5, len(samples)-1):]
                result = {'status': 'passed', 'requested_seconds': seconds, 'workload_seconds': workload_seconds,
                    'iterations': iteration, 'requests': calls, 'observed_nodes_total': observed_nodes,
                    'uid': os.getuid(), 'platform': platform.platform(), 'doctor': doctor,
                    'latency_ms': {name: metrics(values) for name, values in durations.items()},
                    'steady_after_iteration': min(5, len(samples)-1),
                    'steady_server_fds': metrics([row['server']['fds'] for row in steady]),
                    'steady_server_rss_kib': metrics([row['server']['rss_kib'] for row in steady]),
                    'steady_client_rss_kib': metrics([row['client']['rss_kib'] for row in steady]),
                    'steady_private_process_count': metrics([row['private_process_count'] for row in steady]),
                    'first_sample': samples[0], 'last_sample': samples[-1], 'before_disconnect': before_disconnect,
                    'server_exited': True, 'clipboard_owners_after_disconnect': lingering,
                    'independent_final_clicks': expected_clicks, 'quiet_seconds_before_disconnect': 3,
                    'quiet_seconds_after_disconnect': 2,
                    'limits': ['Ten-minute sustained workload, not hours-long qualification or hard memory/latency ceilings.',
                        'Resources sampled between requests; short-lived helper peaks are not measured.',
                        'RSS regression ceiling 512 MiB and FD ceiling 64 are broad test alarms, not advertised product budgets.']}
    except BaseException as exc:
        result.update(error_type=type(exc).__name__, completed_requests=calls, completed_samples=len(samples))
        raise
    finally:
        for process in (app, wm):
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        source_after = source_fingerprint(ROOT)
        result.update(total_seconds=time.monotonic()-began, source_before=source_before, source_after=source_after,
            source_unchanged=source_before==source_after)
        if source_before!=source_after: result['status']='source_changed'
        (out/'results.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({key: value for key, value in result.items() if key not in ('source_before','source_after','doctor','first_sample','last_sample')}), flush=True)
    assert result['status']=='passed', result['status']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--interval', type=float, default=1.5)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--server-child', type=Path)
    args = parser.parse_args()
    if args.server_child:
        args.server_child.write_text(str(os.getpid()))
        os.execv(sys.executable, [sys.executable, '-m', 'luda.server'])
    if os.getuid()==0: parser.error('Run as the ordinary desktop account; this creates a private session.')
    if not 10<=args.seconds<=900 or not .1<=args.interval<=5: parser.error('seconds must be 10..900 and interval .1..5')
    out = (args.output or ROOT/'artifacts/mcp-soak'/('run-'+str(time.time_ns()))).resolve()
    if args.child: return asyncio.run(child(args.seconds, args.interval, out))
    out.mkdir(parents=True, exist_ok=True)
    token = str(uuid.uuid4())
    with tempfile.TemporaryDirectory(prefix='luda-private-soak-') as directory:
        env = private_environment(Path(directory), token)
        command = ['xvfb-run', '-a', '-s', '-screen 0 1200x900x24 -nolisten tcp', 'dbus-run-session', '--',
            sys.executable, __file__, '--child', '--seconds', str(args.seconds), '--interval', str(args.interval), '--output', str(out)]
        with (out/'harness.log').open('w') as log:
            process = subprocess.Popen(command, env=env, stdout=log, stderr=log, start_new_session=True)
            try: code = process.wait(timeout=args.seconds+60)
            finally:
                stop(process); cleanup = cleanup_owned(token)
                (out/'cleanup.json').write_text(json.dumps(cleanup, indent=2)+'\n')
        assert not cleanup['survivors'], cleanup
    print(json.dumps({'output': str(out), 'returncode': code, 'cleanup': cleanup}), flush=True)
    raise SystemExit(code)

if __name__=='__main__': main()
