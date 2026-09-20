#!/usr/bin/env python3
"""One first-attempt native additive range selection task, existing CLI auth, ordinary private GUI."""
import argparse,base64,json,os,pwd,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from agent_eval import grade_trace,stop,version
from agent_file_eval import tool_failures
from agent_trace_metrics import metrics
from qualify import source_fingerprint
ROOT=Path(__file__).resolve().parents[1]



def grade(actual,_unused=None):
    return {'exact_selected_ids':actual.get('selected_ids')==[2,3,4,6],
            'initial_record_preserved':bool(actual.get('events')) and all(6 in ids for ids in actual['events']),
            'no_unrequested_selection':all(set(ids)<={2,3,4,6} for ids in actual.get('events',[]))}


def semantic_receipt(calls):
    if not calls:return False
    item=calls[-1];args=item.get('arguments',{})
    if (item.get('tool')!='desktop_inspect' or args.get('role')!='table cell'
            or args.get('states')!=['selected'] or args.get('name')):return False
    for content in (item.get('result') or {}).get('content',[]):
        if content.get('type')!='text':continue
        try:v=json.loads(content['text'])
        except (ValueError,KeyError):continue
        nodes=v.get('nodes',[])
        if (v.get('ok') is True and v.get('available') is True and v.get('truncated') is False
                and v.get('unreadable_nodes')==0 and v.get('unreadable_branches')==0
                and all(v.get('truncation',{}).get(k) is False for k in ('result_or_time_limit','budget_pruned','depth_pruned'))
                and v.get('truncation',{}).get('unreadable_branches')==0
                and v.get('window_id')==args.get('window_id')
                and len(nodes)==4 and {n.get('name') for n in nodes}=={'Record 002','Record 003','Record 004','Record 006'}
                and all(n.get('role')=='table cell' and 'selected' in n.get('states',[]) for n in nodes)):
            return True
    return False


def trace_observations(events):
    calls=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    groups=[];range_calls=[]
    for item in calls:
        if item.get('tool')=='desktop_inspect':
            for content in (item.get('result') or {}).get('content',[]):
                if content.get('type')!='text':continue
                try:v=json.loads(content['text'])
                except ValueError:continue
                groups.append({n.get('element_id') for n in v.get('nodes',[])})
        if item.get('tool')=='desktop_choose' and item.get('arguments',{}).get('range_end_id'):
            a=item['arguments'];range_calls.append({'extend':a.get('extend') is True,'same_observed_group':any(a.get('element_id') in g and a.get('range_end_id') in g for g in groups)})
    return {'range_calls':range_calls,'range_add_discovered':len(range_calls)==1 and all(range_calls[0].values()),'exact_public_semantic_receipt':semantic_receipt(calls)}


def child(base):
    wm=fixture=None
    try:
        wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        end=time.monotonic()+8
        while subprocess.run(['wmctrl','-m'],capture_output=True,timeout=2).returncode:
            if time.monotonic()>end:raise RuntimeError('Private window manager unavailable')
            time.sleep(.05)
        fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/agent_range_fixture.py'),str(base)],start_new_session=True)
        (base/'fixture.pid').write_text(str(fixture.pid))
        from luda.desktop import Desktop
        desktop=Desktop()
        try:
            end=time.monotonic()+8
            while not any(w['pid']==fixture.pid for w in desktop.list_windows()):
                if fixture.poll() is not None or time.monotonic()>end:raise RuntimeError('Fixture window absent')
                time.sleep(.05)
        finally:desktop.close()
        keys=('DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','XDG_RUNTIME_DIR','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_CONFIG_DIRS','LANG','LC_ALL','PATH')
        (base/'ready.json').write_text(json.dumps({'uid':os.getuid(),'environment':{k:os.environ[k] for k in keys if k in os.environ}}))
        end=time.monotonic()+220
        while not (base/'stop').exists() and time.monotonic()<end:time.sleep(.05)
    finally:stop(fixture);stop(wm)


def launch(base):
    with tempfile.TemporaryDirectory(prefix='luda-agent-rich-desktop-') as tmp:
        env=dict(os.environ)
        for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
            path=Path(tmp)/key;path.mkdir(mode=0o700);env[key]=str(path)
        env.update(XDG_CONFIG_DIRS=env['XDG_CONFIG_HOME'],LANG='C.UTF-8',LC_ALL='C.UTF-8',NO_AT_BRIDGE='0',GTK_MODULES='gail:atk-bridge',GSETTINGS_BACKEND='memory')
        process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1440x1000x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--child',str(base)],env=env,start_new_session=True)
        try:return process.wait(timeout=235)
        finally:stop(process)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--child',type=Path);parser.add_argument('--launch',type=Path);parser.add_argument('--timeout',type=int,default=180);args=parser.parse_args()
    if args.child:child(args.child);return 0
    if args.launch:return launch(args.launch)
    if os.getuid()!=0:parser.error('Existing root CLI authentication is used; desktop/MCP drop to the ordinary account.')
    if not 1<=args.timeout<=180:parser.error('Bound must be1..180 seconds')
    codex=shutil.which('codex');account=pwd.getpwnam(os.environ.get('LUDA_TEST_USER', 'desktop'))
    if not codex:parser.error('Existing authenticated Codex CLI required')
    out=ROOT/'artifacts/agent-native-range'/('run-'+str(time.time_ns()));out.mkdir(parents=True)
    result={'attempt':1,'passed':False,'source_before':source_fingerprint(ROOT),'codex':version([codex,'--version']),'providers':version(['dpkg-query','-W','libgtk-3-0t64','libatspi2.0-0t64']),'resolved_model':'unknown unless exposed by CLI JSON','agent_uid':os.getuid(),'desktop_uid':account.pw_uid,'budget_seconds':args.timeout}
    launcher=agent=None
    with tempfile.TemporaryDirectory(prefix='luda-agent-rich-') as directory:
        base=Path(directory);base.chmod(0o711);desktop=base/'desktop';desktop.mkdir(mode=0o700);os.chown(desktop,account.pw_uid,account.pw_gid)
        workspace=base/'workspace';workspace.mkdir();skill=workspace/'.agents/skills/luda/SKILL.md';skill.parent.mkdir(parents=True);shutil.copyfile(ROOT/'skills/luda/SKILL.md',skill)
        try:
            with (out/'desktop.log').open('wb') as log:
                launcher=subprocess.Popen(['/usr/sbin/runuser','-u',os.environ.get('LUDA_TEST_USER', 'desktop'),'--',str(ROOT/'.venv/bin/python'),__file__,'--launch',str(desktop)],stdout=log,stderr=log,start_new_session=True)
                end=time.monotonic()+30
                while not (desktop/'ready.json').exists():
                    if launcher.poll() is not None or time.monotonic()>end:raise RuntimeError('Private desktop startup failed')
                    time.sleep(.05)
                ready=json.loads((desktop/'ready.json').read_text())
                prompt='In Range Desk, keep the already selected Record 006 and also select the contiguous records from Record 002 through Record 004, inclusive. Leave only those requested records selected, verify the selection, and leave the window open. Use only public Luda desktop MCP tools. Read the installed Luda skill first; you may read .agents/skills/luda/SKILL.md. Do not read application source, hidden files or oracle data, run other programs, modify files directly, or browse websites.'
                result['prompt']=prompt
                server_args=['-u',os.environ.get('LUDA_TEST_USER', 'desktop'),'--','/usr/bin/env',*[k+'='+v for k,v in ready['environment'].items()],str(ROOT/'.venv/bin/luda')]
                cmd=[codex,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--json','--sandbox','read-only','-C',str(workspace),'-c','approval_policy="never"','-c','mcp_servers.luda.command="/usr/sbin/runuser"','-c','mcp_servers.luda.args='+json.dumps(server_args),'-c','mcp_servers.luda.default_tools_approval_mode="approve"','-c','mcp_servers.luda.required=true','-c','mcp_servers.luda.startup_timeout_sec=20','-c','mcp_servers.luda.tool_timeout_sec=20',prompt]
                result['argv']=cmd;started=time.monotonic()
                with (out/'events.jsonl').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
                    agent=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
                    try:result['returncode']=agent.wait(timeout=args.timeout)
                    except subprocess.TimeoutExpired:result['timeout']=True
                    finally:stop(agent)
                result['seconds']=round(time.monotonic()-started,3)
                events=[]
                for line in (out/'events.jsonl').read_text().splitlines():
                    try:events.append(json.loads(line))
                    except ValueError:pass
                result.update(grade_trace(events,skill));result['metrics']=metrics(events);result['tool_errors']=tool_failures(events)
                result['models_reported']=sorted({e['model'] for e in events if isinstance(e.get('model'),str)})
                actual=json.loads((desktop/'state.json').read_text()) if (desktop/'state.json').exists() else {}
                accepted={}
                result['oracle']=actual;result['accepted_oracle']=accepted;result['oracle_checks']=grade(actual,accepted)
                result.update(trace_observations(events))
                images=[c for e in events if e.get('type')=='item.completed' for c in (e.get('item',{}).get('result') or {}).get('content',[]) if c.get('type')=='image']
                if images:(out/'last-observation.png').write_bytes(base64.b64decode(images[-1]['data']))
                result['final_messages']=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
                result['source_after']=source_fingerprint(ROOT);result['source_unchanged']=result['source_before']==result['source_after']
                result['workflow_oracle_passed']=result.get('returncode')==0 and all(result['oracle_checks'].values()) and result['source_unchanged'] and all(result[k] for k in ('skill_reads_only','only_public_desktop_tools','no_direct_file_changes','no_other_tools','no_injected_actions'))
                result['range_workflow_discovered']=result['workflow_oracle_passed'] and result['range_add_discovered']
                result['passed']=result['range_workflow_discovered'] and result['exact_public_semantic_receipt']
        except Exception as exc:result['harness_error']={'type':type(exc).__name__,'message':str(exc)}
        finally:
            (desktop/'stop').touch()
            if launcher:
                try:launcher.wait(timeout=6)
                except subprocess.TimeoutExpired:pass
            stop(agent);stop(launcher);(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'artifact_directory':str(out),'passed':result['passed'],'seconds':result.get('seconds'),'harness_error':result.get('harness_error')},ensure_ascii=False));return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
