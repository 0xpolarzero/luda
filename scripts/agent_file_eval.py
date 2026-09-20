#!/usr/bin/env python3
"""One held-out Codex attempt: native file manager, private ordinary-user desktop."""
import argparse,gzip,hashlib,json,os,pwd,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from agent_eval import grade_trace,stop,version
from qualify import source_fingerprint
from agent_file_oracle import seed, grade, ProtectedWatch, RESUME


def tool_failures(events):
    """CLI events may omit MCP isError; inspect the public structured payload."""
    failures=[]
    for event in events:
        item=event.get('item',{})
        if event.get('type')!='item.completed' or item.get('type')!='mcp_tool_call':continue
        result=item.get('result') or {}
        failed=bool(item.get('error') or result.get('isError'))
        for content in result.get('content',[]):
            if content.get('type')!='text':continue
            try:value=json.loads(content.get('text',''))
            except (ValueError,TypeError):continue
            if isinstance(value,dict) and value.get('ok') is False:failed=True
        if failed:failures.append(item)
    return failures


def desktop_child(base,backend):
    envkeys=('DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','XDG_RUNTIME_DIR','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_CONFIG_DIRS','LOCPATH','LANG','LC_ALL','TZ','PATH')
    wm=fixture=watch=None
    try:
        wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        end=time.monotonic()+8
        while subprocess.run(['wmctrl','-m'],capture_output=True,timeout=2).returncode:
            if time.monotonic()>end:raise RuntimeError('Private window manager unavailable')
            time.sleep(.05)
        data=base/'File task'; before=seed(data);(base/'initial.json').write_text(json.dumps(before))
        watch=ProtectedWatch(data/'Sorted'/RESUME);events=[];(base/'protected-events.json').write_text('[]')
        fixture=subprocess.Popen(['thunar',str(data)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        from luda.desktop import Desktop
        desktop=Desktop()
        try:
            end=time.monotonic()+8
            while not any(window['pid']==fixture.pid for window in desktop.list_windows()):
                if fixture.poll() is not None or time.monotonic()>end:raise RuntimeError('Private Thunar fixture unavailable')
                time.sleep(.05)
        finally:desktop.close()
        (base/'ready.json').write_text(json.dumps({'uid':os.getuid(),'fixture_pid':fixture.pid,'environment':{key:os.environ[key] for key in envkeys if key in os.environ}}))
        end=time.monotonic()+340
        while not (base/'stop').exists() and time.monotonic()<end:
            events+=watch.drain();temporary=base/'protected-events.tmp';temporary.write_text(json.dumps(events));temporary.replace(base/'protected-events.json');time.sleep(.05)
    finally:
        if watch:watch.close()
        stop(fixture);stop(wm)


def desktop_launch(base,backend):
    with tempfile.TemporaryDirectory(prefix='luda-agent-files-desktop-') as directory:
        private=Path(directory);env=dict(os.environ)
        for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
            path=private/key;path.mkdir(mode=0o700);env[key]=str(path)
        env.update(XDG_CONFIG_DIRS=env['XDG_CONFIG_HOME'],LANG='C.UTF-8',LC_ALL='C.UTF-8',NO_AT_BRIDGE='0',GTK_MODULES='gail:atk-bridge',GSETTINGS_BACKEND='memory')
        child=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1440x1000x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--desktop-child',str(base),'--backend-root',str(backend)],env=env,start_new_session=True)
        try:return child.wait(timeout=355)
        finally:stop(child)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-root',type=Path,required=True)
    parser.add_argument('--desktop-launch',type=Path)
    parser.add_argument('--desktop-child',type=Path)
    parser.add_argument('--desktop-user',default='silo-desktop')
    parser.add_argument('--timeout',type=int,default=300)
    args=parser.parse_args();backend=args.backend_root.resolve()
    if args.desktop_child:desktop_child(args.desktop_child,backend);return 0
    if args.desktop_launch:return desktop_launch(args.desktop_launch,backend)
    if os.getuid()!=0:parser.error('This existing-auth harness expects the root CLI and drops only desktop/MCP to the named ordinary account.')
    if not 1<=args.timeout<=300:parser.error('Agent budget must be 1..300 seconds.')
    codex=shutil.which('codex');assert codex,'Existing authenticated Codex CLI required'
    account=pwd.getpwnam(args.desktop_user);assert account.pw_uid!=0
    artifacts=backend/'artifacts/agent-files'/('run-'+str(time.time_ns()));artifacts.mkdir(parents=True)
    result={'attempt':1,'budget_seconds':args.timeout,'agent_uid':os.getuid(),'desktop_uid':account.pw_uid,'codex_version':version([codex,'--version']),'model_requested':'CLI default; resolved model recorded only if explicitly present in events','source_before':source_fingerprint(backend),'provider_versions':version(['dpkg-query','-W','-f=${Package} ${Version}\n','thunar','libgtk-3-0t64','libatspi2.0-0t64','xvfb','xfwm4']),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'passed':False}
    launcher=agent=None
    with tempfile.TemporaryDirectory(prefix='luda-agent-files-eval-') as directory:
        base=Path(directory);base.chmod(0o711);desktop=base/'desktop';desktop.mkdir(mode=0o700);os.chown(desktop,account.pw_uid,account.pw_gid)
        workspace=base/'workspace';workspace.mkdir();skill=workspace/'.agents/skills/luda/SKILL.md';skill.parent.mkdir(parents=True);shutil.copyfile(backend/'skills/luda/SKILL.md',skill)
        prompt='In the open Thunar File task folder, organize the files using the graphical interface. Move Inbox/旅程 東京.txt into Sorted. Copy Inbox/Résumé été.txt into Sorted under the new name Résumé été — copie.txt, preserving the original in Inbox. Sorted already contains Résumé été.txt: do not overwrite, replace, rename, or delete that existing file. Create a symbolic link named 旅程 東京.txt inside References pointing to the moved Sorted/旅程 東京.txt (a real link, not a copy). Leave Inbox/À garder.txt untouched, and leave no extra files. Verify the visible result. Use only public Luda desktop MCP tools to operate the application. Read the installed Luda skill first. Do not read application source or hidden files, run other programs, browse the network, or modify files directly. You may read .agents/skills/luda/SKILL.md.'
        result['prompt']=prompt
        try:
            launch=['/usr/sbin/runuser','-u',args.desktop_user,'--',str(backend/'.venv/bin/python'),str(Path(__file__).resolve()),'--desktop-launch',str(desktop),'--backend-root',str(backend)]
            with (artifacts/'desktop.log').open('wb') as log:
                launcher=subprocess.Popen(launch,stdout=log,stderr=log,start_new_session=True)
                end=time.monotonic()+30
                while not (desktop/'ready.json').exists():
                    if launcher.poll() is not None or time.monotonic()>end:raise RuntimeError('Private ordinary-user desktop startup failed')
                    time.sleep(.05)
                ready=json.loads((desktop/'ready.json').read_text());result['desktop_uid']=ready['uid']
                # Codex keeps its existing root authentication; the graphical
                # backend process and application run as the ordinary account.
                server_args=['-u',args.desktop_user,'--','/usr/bin/env',*[key+'='+value for key,value in ready['environment'].items()],str(backend/'.venv/bin/luda')]
                command=[codex,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--json','--sandbox','read-only','-C',str(workspace),'-c','approval_policy="never"','-c','mcp_servers.luda.command="/usr/sbin/runuser"','-c','mcp_servers.luda.args='+json.dumps(server_args),'-c','mcp_servers.luda.default_tools_approval_mode="approve"','-c','mcp_servers.luda.required=true','-c','mcp_servers.luda.startup_timeout_sec=20','-c','mcp_servers.luda.tool_timeout_sec=20',prompt]
                result['argv']=command;started=time.monotonic()
                with (artifacts/'events.jsonl').open('wb') as out,(artifacts/'stderr.log').open('wb') as err:
                    agent=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
                    try:result['returncode']=agent.wait(timeout=args.timeout)
                    except subprocess.TimeoutExpired:result['timeout']=True
                    finally:stop(agent)
                result['seconds']=round(time.monotonic()-started,3)
                events=[]
                for line in (artifacts/'events.jsonl').read_text().splitlines():
                    try:events.append(json.loads(line))
                    except ValueError:pass
                result.update(grade_trace(events,skill))
                result['resolved_model']='unknown unless explicitly exposed in CLI JSON events'
                result['models_reported']=sorted({event['model'] for event in events if isinstance(event.get('model'),str)})
                time.sleep(.15)
                result['oracle']=grade(desktop/'File task',json.loads((desktop/'initial.json').read_text()),json.loads((desktop/'protected-events.json').read_text()))
                result['oracle_exact']=result['oracle']['exact']
                result['tool_errors']=tool_failures(events)
                result['source_after']=source_fingerprint(backend);result['source_unchanged']=result['source_before']==result['source_after']
                result['passed']=result.get('returncode')==0 and result['oracle_exact'] and result['source_unchanged'] and all(result[key] for key in ('skill_reads_only','only_public_desktop_tools','no_direct_file_changes','no_other_tools','no_injected_actions')) and bool(result['tool_calls'])
        except Exception as exc:result['harness_error']={'type':type(exc).__name__,'message':str(exc)}
        finally:
            (desktop/'stop').touch()
            if launcher:
                try:launcher.wait(timeout=6)
                except subprocess.TimeoutExpired:pass
            stop(agent);stop(launcher)
            (artifacts/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'artifact_directory':str(artifacts),'passed':result['passed'],'seconds':result.get('seconds'),'tool_calls':len(result.get('tool_calls',[])),'tool_errors':len(result.get('tool_errors',[])),'oracle':result.get('oracle',{}).get('cases'),'harness_error':result.get('harness_error')},ensure_ascii=False))
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
