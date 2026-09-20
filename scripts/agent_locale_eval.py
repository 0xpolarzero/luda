#!/usr/bin/env python3
"""One fresh Codex attempt: root CLI auth, ordinary-user private locale desktop."""
import argparse,gzip,hashlib,json,os,pwd,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from agent_eval import grade_trace,stop,version
from qualify import source_fingerprint


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
    wm=fixture=None
    try:
        wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        end=time.monotonic()+8
        while subprocess.run(['wmctrl','-m'],capture_output=True,timeout=2).returncode:
            if time.monotonic()>end:raise RuntimeError('Private window manager unavailable')
            time.sleep(.05)
        fixture=subprocess.Popen(['/usr/bin/python3',str(backend/'tests/data_entry_fixture.py'),str(base/'oracle')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        from luda.desktop import Desktop
        desktop=Desktop()
        try:
            end=time.monotonic()+8
            while not any(window['pid']==fixture.pid for window in desktop.list_windows()):
                if fixture.poll() is not None or time.monotonic()>end:raise RuntimeError('Private data fixture unavailable')
                time.sleep(.05)
        finally:desktop.close()
        (base/'ready.json').write_text(json.dumps({'uid':os.getuid(),'fixture_pid':fixture.pid,'environment':{key:os.environ[key] for key in envkeys if key in os.environ}}))
        end=time.monotonic()+150
        while not (base/'stop').exists() and time.monotonic()<end:time.sleep(.1)
    finally:stop(fixture);stop(wm)


def desktop_launch(base,backend,locale_source):
    with tempfile.TemporaryDirectory(prefix='luda-agent-locale-desktop-') as directory:
        private=Path(directory);env=dict(os.environ)
        for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
            path=private/key;path.mkdir(mode=0o700);env[key]=str(path)
        env['XDG_CONFIG_DIRS']=env['XDG_CONFIG_HOME']
        charmap=private/'UTF-8';charmap.write_bytes(gzip.decompress((locale_source/'charmaps/UTF-8.gz').read_bytes()))
        locales=private/'locales';locales.mkdir()
        subprocess.run(['localedef','--no-archive','-i',str(locale_source/'locales/de_DE'),'-f',str(charmap),str(locales/'de_DE.UTF-8')],env=dict(env,I18NPATH=str(locale_source)),check=True,capture_output=True,timeout=20)
        env.update(LOCPATH=str(locales),LANG='de_DE.UTF-8',LC_ALL='de_DE.UTF-8',TZ='Europe/Berlin',NO_AT_BRIDGE='0',GTK_MODULES='gail:atk-bridge')
        child=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1200x900x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--desktop-child',str(base),'--backend-root',str(backend)],env=env,start_new_session=True)
        try:return child.wait(timeout=165)
        finally:stop(child)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-root',type=Path,required=True)
    parser.add_argument('--locale-source',type=Path,default=Path('/usr/share/i18n'))
    parser.add_argument('--desktop-launch',type=Path)
    parser.add_argument('--desktop-child',type=Path)
    parser.add_argument('--desktop-user',default='silo-desktop')
    parser.add_argument('--timeout',type=int,default=120)
    args=parser.parse_args();backend=args.backend_root.resolve()
    if args.desktop_child:desktop_child(args.desktop_child,backend);return 0
    if args.desktop_launch:return desktop_launch(args.desktop_launch,backend,args.locale_source)
    if os.getuid()!=0:parser.error('This existing-auth harness expects the root CLI and drops only desktop/MCP to the named ordinary account.')
    if not 1<=args.timeout<=120:parser.error('Agent budget must be 1..120 seconds.')
    codex=shutil.which('codex');assert codex,'Existing authenticated Codex CLI required'
    account=pwd.getpwnam(args.desktop_user);assert account.pw_uid!=0
    artifacts=backend/'artifacts/agent-locale'/('run-'+str(time.time_ns()));artifacts.mkdir(parents=True)
    result={'attempt':1,'budget_seconds':args.timeout,'agent_uid':os.getuid(),'desktop_uid':account.pw_uid,'codex_version':version([codex,'--version']),'model_requested':'CLI default; resolved model recorded only if explicitly present in events','source_before':source_fingerprint(backend),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'passed':False}
    launcher=agent=None
    with tempfile.TemporaryDirectory(prefix='luda-agent-locale-eval-') as directory:
        base=Path(directory);base.chmod(0o711);desktop=base/'desktop';desktop.mkdir(mode=0o700);os.chown(desktop,account.pw_uid,account.pw_gid)
        workspace=base/'workspace';workspace.mkdir();skill=workspace/'.agents/skills/luda/SKILL.md';skill.parent.mkdir(parents=True);shutil.copyfile(backend/'skills/luda/SKILL.md',skill)
        prompt='In the visible "Luda data entry oracle" form, set the local date and time to 18.11.2027 16:45 in Europe/Berlin, set the amount to 12,35, and explicitly select "Bergen, Norway" from the Destination autocomplete suggestions rather than merely entering it as literal text. Check the values, then submit exactly once and verify the visible result. Use only the public Luda desktop MCP tools to operate the application. Read the installed Luda skill first. Do not read application source or hidden files, run other programs, browse the network, or modify files directly. You may read .agents/skills/luda/SKILL.md.'
        result['prompt']=prompt
        try:
            launch=['/usr/sbin/runuser','-u',args.desktop_user,'--',str(backend/'.venv/bin/python'),str(Path(__file__).resolve()),'--desktop-launch',str(desktop),'--backend-root',str(backend),'--locale-source',str(args.locale_source)]
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
                result['models_reported']=sorted({event['model'] for event in events if isinstance(event.get('model'),str)})
                state_path=desktop/'oracle/state.json';state=json.loads(state_path.read_text()) if state_path.exists() else None
                result['oracle']=state
                expected={'utc':'2027-11-18T15:45:00+00:00','amount':12.35,'amount_text':'12,35','destination':'Bergen, Norway','selected_suggestion':'Bergen, Norway'}
                result['oracle_exact']=bool(state and state['committed']==expected and state['submits']==1 and state['accepted']==1 and state['selection_count']==1)
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
    print(json.dumps({'artifact_directory':str(artifacts),**result},ensure_ascii=False))
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
