#!/usr/bin/env python3
"""Fresh-agent tasks with independent oracles; requires existing Codex CLI auth.

Run under xvfb-run + dbus-run-session with LUDA_ISOLATED_TEST_DISPLAY=1.
No credentials or global agent configuration are read or modified by this harness.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from qualify import source_fingerprint

ROOT=Path(__file__).resolve().parents[1]
PAYLOAD='Leave by the blue door.\n日本語 👩🏽\u200d💻\n\tRing twice.\n'


def stop(process):
    if process is None:return
    for sig in (signal.SIGTERM,signal.SIGKILL):
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:pass
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:pass


def allowed_command(command,skill):
    try:
        parts=shlex.split(command)
        if len(parts)>=3 and parts[-2] in ('-lc','-c'):parts=shlex.split(parts[-1])
        return parts in (['cat',str(skill)],['cat',str(skill.relative_to(skill.parents[3]))])
    except (ValueError,TypeError):return False


def grade_trace(events,skill):
    items=[e.get('item',{}) for e in events if e.get('type') in ('item.started','item.completed')]
    commands=[i.get('command','') for i in items if i.get('type')=='command_execution']
    calls=[i for i in items if i.get('type')=='mcp_tool_call']
    return {'skill_reads_only':all(allowed_command(c,skill) for c in commands),
            'only_public_desktop_tools':all(i.get('server')=='luda' and str(i.get('tool','')).startswith('desktop_') for i in calls),
            'no_direct_file_changes':not any(i.get('type')=='file_change' for i in items),
            'tool_calls':[e['item'].get('tool') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call'],
            'usage':[e.get('usage') for e in events if e.get('type')=='turn.completed']}


def version(command):
    try:return subprocess.check_output(command,text=True,stderr=subprocess.STDOUT,timeout=5).strip()[:600]
    except (subprocess.SubprocessError,OSError):return 'unavailable'


def run_task(task,args,codex,artifacts):
    output=artifacts/task;output.mkdir(parents=True,exist_ok=True)
    result={'task':task,'passed':False,'model_requested':args.model or 'CLI default (resolved model not exposed by JSON events)',
            'source_before':source_fingerprint(ROOT)}
    fixture=agent=None
    with tempfile.TemporaryDirectory(prefix='luda-agent-task-') as directory:
        base=Path(directory);workspace=base/'workspace';workspace.mkdir()
        skill=workspace/'.agents/skills/luda/SKILL.md';skill.parent.mkdir(parents=True)
        shutil.copyfile(ROOT/'skills/luda/SKILL.md',skill)
        oracle=base/'oracle.json';destination=base/'Delivery 日本語.txt'
        common=' Use the desktop tools to operate the visible application. Do not read application source or hidden files, execute other programs, browse the network, or modify files directly. You may read the installed Luda skill. Verify the visible result.'
        if task=='form':
            expected={'note':PAYLOAD,'updates':True,'express':True}
            app=['/usr/bin/python3',str(ROOT/'tests/agent_fixture.py'),str(oracle)]
            prompt='In "Luda agent task", replace Delivery note with the exact string represented by this JSON literal: '+json.dumps(PAYLOAD,ensure_ascii=False)+'. Enable Send updates, choose Express delivery, and save the preferences.'+common
        elif task=='mousepad':
            expected=PAYLOAD
            app=['mousepad','--disable-server']
            prompt='Use the open Mousepad text editor to create a document containing exactly the string represented by this JSON literal: '+json.dumps(PAYLOAD,ensure_ascii=False)+'. Save it using the graphical Save As dialog to '+str(destination)+'. Preserve tabs, Unicode, and the final newline.'+common
        else:
            expected={'color':'Amber','cell':'B2','saved':True}
            app=['/usr/bin/python3',str(ROOT/'tests/agent_fixture.py'),str(oracle),'canvas']
            prompt='In "Luda visual task", choose Amber from the Palette menu, place a marker in cell B2, and commit the board.'+common
        result['prompt']=prompt
        try:
            fixture=subprocess.Popen(app,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            from luda.desktop import Desktop
            desktop=Desktop()
            try:
                deadline=time.monotonic()+8
                while not any(w['pid']==fixture.pid for w in desktop.list_windows()):
                    if fixture.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Task application did not open')
                    time.sleep(.05)
            finally:desktop.close()
            command=[codex,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--json','--sandbox','read-only','-C',str(workspace),'-c','approval_policy="never"','-c','mcp_servers.luda.command='+json.dumps(str(ROOT/'.venv/bin/luda')),'-c','mcp_servers.luda.env_vars='+json.dumps(['DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','XDG_RUNTIME_DIR']),'-c','mcp_servers.luda.default_tools_approval_mode="approve"','-c','mcp_servers.luda.required=true','-c','mcp_servers.luda.startup_timeout_sec=20','-c','mcp_servers.luda.tool_timeout_sec=20']
            if args.model:command+=['--model',args.model]
            command.append(prompt)
            result['argv']=command
            started=time.monotonic()
            with (output/'events.jsonl').open('wb') as out,(output/'stderr.log').open('wb') as err:
                agent=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
                try:result['returncode']=agent.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:result['timeout']=True
                finally:stop(agent)
            result['seconds']=round(time.monotonic()-started,3)
            events=[]
            for line in (output/'events.jsonl').read_text().splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            result.update(grade_trace(events,skill))
            actual=destination.read_bytes() if task=='mousepad' and destination.exists() else (json.loads(oracle.read_text()) if oracle.exists() else None)
            exact=actual==expected.encode() if task=='mousepad' else actual==expected
            result['oracle_exact']=exact
            result['oracle']={'bytes':len(actual),'sha256':hashlib.sha256(actual).hexdigest()} if isinstance(actual,bytes) else actual
            result['source_after']=source_fingerprint(ROOT)
            result['source_unchanged']=result['source_before']==result['source_after']
            result['passed']=result.get('returncode')==0 and exact and result['skill_reads_only'] and result['only_public_desktop_tools'] and result['no_direct_file_changes'] and result['source_unchanged'] and bool(result['tool_calls'])
        except Exception as exc:result['harness_error']={'type':type(exc).__name__,'message':str(exc)}
        finally:
            stop(agent);stop(fixture)
            (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout',type=int,default=150)
    parser.add_argument('--model')
    parser.add_argument('--tasks',nargs='+',choices=['form','mousepad','canvas'],default=['form','mousepad','canvas'])
    args=parser.parse_args()
    if not 1<=args.timeout<=150:parser.error('Each fresh-agent run must be bounded to 1..150 seconds.')
    if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1' or not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):parser.error('Use a fresh Xvfb/private D-Bus desktop with LUDA_ISOLATED_TEST_DISPLAY=1.')
    codex=shutil.which('codex')
    if not codex:parser.error('An already authenticated Codex CLI is required.')
    artifacts=ROOT/'artifacts/agent-eval';artifacts.mkdir(parents=True,exist_ok=True)
    result={'scope':'Three local held-out task types; not repeatability or general usability qualification.',
            'environment':{'codex':version([codex,'--version']),'python':platform.python_version(),'architecture':platform.machine(),
             'packages':version(['dpkg-query','-W','-f=${Package} ${Version}\n','mousepad','libgtk-3-0t64','libatspi2.0-0t64','xvfb','xfwm4']),
             'mcp':importlib.metadata.version('mcp'),'uid':os.getuid()}}
    wm=None
    with tempfile.TemporaryDirectory(prefix='luda-agent-session-') as runtime:
        os.environ['XDG_RUNTIME_DIR']=runtime
        os.environ['XDG_CONFIG_HOME']=str(Path(runtime)/'config')
        os.environ['XDG_CACHE_HOME']=str(Path(runtime)/'cache')
        os.environ['NO_AT_BRIDGE']='0';os.environ['GTK_MODULES']='gail:atk-bridge'
        with (artifacts/'window-manager.log').open('wb') as log:
            wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=log,stderr=log,start_new_session=True)
            try:
                deadline=time.monotonic()+8
                while subprocess.run(['wmctrl','-m'],capture_output=True,timeout=2).returncode:
                    if wm.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Private window manager not ready')
                    time.sleep(.1)
                result['tasks']=[run_task(task,args,codex,artifacts) for task in args.tasks]
            finally:stop(wm)
    (artifacts/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if all(r['passed'] for r in result['tasks']) else 1

if __name__=='__main__':sys.exit(main())
