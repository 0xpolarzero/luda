#!/usr/bin/env python3
"""Fresh Codex agent usability probe on an explicitly isolated test desktop.

Requires an already authenticated Codex CLI. Never configures auth or runs in CI
by default. Agent sees the task, installed skill and public MCP schemas only.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout',type=int,default=180)
    args=parser.parse_args()
    if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':
        parser.error('Use only on a fresh Xvfb/XFWM4/session-bus desktop with LUDA_ISOLATED_TEST_DISPLAY=1.')
    codex=shutil.which('codex')
    if not codex:parser.error('An already authenticated Codex CLI is required; it is not a Luda runtime dependency.')
    artifacts=ROOT/'artifacts/agent-eval';artifacts.mkdir(parents=True,exist_ok=True)
    payload='Leave by the blue door.\n日本語 👩🏽\u200d💻\n\tRing twice.\n'
    expected={'note':payload,'updates':True,'express':True}
    result={'passed':False,'expected':expected}
    with tempfile.TemporaryDirectory(prefix='luda-agent-task-') as directory:
        base=Path(directory);workspace=base/'workspace';workspace.mkdir()
        skill=workspace/'.agents/skills/luda';skill.mkdir(parents=True)
        shutil.copyfile(ROOT/'skills/luda/SKILL.md',skill/'SKILL.md')
        oracle=base/'oracle.json'
        fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/agent_fixture.py'),str(oracle)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        agent=None
        try:
            from luda.desktop import Desktop
            desktop=Desktop()
            try:
                deadline=time.monotonic()+8
                while not any(w['pid']==fixture.pid for w in desktop.list_windows()):
                    if time.monotonic()>deadline:raise RuntimeError('Task fixture did not open')
                    time.sleep(.05)
            finally:desktop.close()
            prompt=('Use the visible "Luda agent task" application to save delivery preferences. Replace the Delivery note with the exact string represented by this JSON literal: '+json.dumps(payload,ensure_ascii=False)+'. Enable Send updates, choose Express delivery, and save the preferences. Verify the visible saved status. Use the available desktop tools; do not read application source, inspect hidden files, or modify files directly. You may read the installed Luda skill. No additional applications or network browsing are needed.')
            command=[codex,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--json','--sandbox','read-only','-C',str(workspace),'-c','approval_policy="never"','-c','mcp_servers.luda.command='+json.dumps(str(ROOT/'.venv/bin/luda')),'-c','mcp_servers.luda.env_vars='+json.dumps(['DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','XDG_RUNTIME_DIR']),'-c','mcp_servers.luda.default_tools_approval_mode="approve"','-c','mcp_servers.luda.required=true','-c','mcp_servers.luda.startup_timeout_sec=20','-c','mcp_servers.luda.tool_timeout_sec=20',prompt]
            started=time.monotonic()
            with (artifacts/'events.jsonl').open('wb') as out,(artifacts/'stderr.log').open('wb') as err:
                agent=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
                try:result['returncode']=agent.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:result['timeout']=True
                finally:
                    try:os.killpg(agent.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:agent.wait(timeout=3)
                    except subprocess.TimeoutExpired:os.killpg(agent.pid,signal.SIGKILL);agent.wait(timeout=3)
            result['seconds']=round(time.monotonic()-started,3)
            result['actual']=json.loads(oracle.read_text()) if oracle.exists() else None
            events=[]
            for line in (artifacts/'events.jsonl').read_text().splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            commands=[event['item']['command'] for event in events if event.get('type')=='item.completed' and event.get('item',{}).get('type')=='command_execution']
            def allowed(command):
                parts=shlex.split(command)
                if len(parts)>=3 and parts[-2] in ('-lc','-c'):parts=shlex.split(parts[-1])
                return parts==['cat',str(skill/'SKILL.md')]
            result['skill_reads_only']=all(allowed(command) for command in commands)
            result['tool_calls']=[event['item'].get('tool') for event in events if event.get('type')=='item.completed' and event.get('item',{}).get('type')=='mcp_tool_call']
            result['passed']=result.get('returncode')==0 and result['actual']==expected and result['skill_reads_only']
            result['source_revision']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
            result['scope']='One fresh-agent synthetic GTK task, not general usability qualification.'
        finally:
            try:os.killpg(fixture.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            fixture.wait(timeout=3)
            (artifacts/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['passed'] else 1

if __name__=='__main__':sys.exit(main())
