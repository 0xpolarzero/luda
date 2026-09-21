#!/usr/bin/env python3
"""Fresh uncoached agent appearance trial on a private XFCE desktop.

Uses existing Codex authentication without reading credentials. Real theme assets
must be supplied separately; never installs system packages or changes :1.
"""
import argparse, hashlib, json, os, pwd, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from agent_eval import copy_skill, grade_trace, stop, version
from agent_trace_metrics import metrics
ROOT = Path(__file__).resolve().parents[1]
PROMPT = ('Change XFCE application appearance to a dark theme. '
          'Use only public Luda desktop MCP tools. Read the installed Luda skill first; '
          'you may use cat to read .agents/skills/luda/SKILL.md and its linked Markdown references '
          'within that skill folder. Do not read application source, hidden files or oracle data, '
          'run other programs, modify files directly, or browse websites.')


def child(base, task):
    if (os.getuid()==0 or os.environ.get('LUDA_SELECTION_EVAL_PRIVATE')!='1'
            or Path(os.environ.get('HOME',''))!=base/'HOME'
            or os.environ.get('DISPLAY','').split('.')[0] in ('',':1')):
        raise RuntimeError('Child requires an ordinary account and private evaluation desktop')
    wm = app = settings = None
    try:
        wm = subprocess.Popen(['xfwm4', '--compositor=off'], start_new_session=True)
        subprocess.run(['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName', '-n', '-t', 'string', '-s', 'Greybird'], check=True)
        if task == 'theme':
            app = subprocess.Popen(['xfce4-appearance-settings'], start_new_session=True)
        else:
            files = Path(os.environ['HOME'])/'Files'; files.mkdir()
            (files/'Report.txt').write_text('Selection-only test document.\n')
            applications = Path(os.environ['XDG_DATA_HOME'])/'applications'; applications.mkdir()
            handler = base/'record-open.py'
            handler.write_text('from pathlib import Path\nPath('+repr(str(base/'opened'))+').write_text("opened")\n')
            (applications/'record-open.desktop').write_text('[Desktop Entry]\nType=Application\nName=Record open\nExec=/usr/bin/python3 '+str(handler)+' %f\nMimeType=text/plain;\n')
            (Path(os.environ['XDG_CONFIG_HOME'])/'mimeapps.list').write_text('[Default Applications]\ntext/plain=record-open.desktop;\n')
            subprocess.run(['update-desktop-database',str(applications)],check=True)
            subprocess.run(['gio','open',str(files/'Report.txt')],check=True)
            end=time.monotonic()+5
            while not (base/'opened').exists():
                if time.monotonic()>end:raise RuntimeError('Independent file-open marker preflight failed')
                time.sleep(.05)
            (base/'opened').unlink()
            subprocess.run(['xfconf-query','-c','thunar','-p','/last-view','-n','-t','string','-s','ThunarDetailsView'],check=True)
            app = subprocess.Popen(['thunar',str(files)], start_new_session=True)
        settings = subprocess.Popen(['xfsettingsd','--no-daemon'], start_new_session=True)
        time.sleep(2)
        keys = ('HOME','DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','XDG_RUNTIME_DIR','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_DATA_DIRS','XDG_CACHE_HOME','XDG_CONFIG_DIRS','XDG_CURRENT_DESKTOP','LANG','LC_ALL','PATH')
        (base/'ready.json').write_text(json.dumps({k:os.environ[k] for k in keys if k in os.environ}))
        end = time.monotonic()+240
        while not (base/'stop').exists() and time.monotonic()<end:
            if task == 'theme':
                state = {'theme':subprocess.check_output(['xfconf-query','-c','xsettings','-p','/Net/ThemeName'],text=True).strip()}
            else:
                import gi
                gi.require_version('Atspi','2.0')
                from gi.repository import Atspi, GLib
                while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
                pending=[Atspi.get_desktop(0)]; selected=[]; observed=[]; seen=0
                while pending and seen<2000:
                    node=pending.pop(); seen+=1
                    try:
                        node.clear_cache()
                        if node.get_name()=='Report.txt':observed.append(node.get_role_name())
                        if node.get_name()=='Report.txt' and node.get_state_set().contains(Atspi.StateType.SELECTED):selected.append(node.get_name())
                        pending.extend(node.get_child_at_index(i) for i in range(node.get_child_count()))
                    except Exception:pass
                state={'observed_file_roles':observed,'selected':selected,'opened':(base/'opened').exists()}
            (base/'oracle-next.json').write_text(json.dumps(state))
            (base/'oracle-next.json').replace(base/'oracle.json')
            if not (base/'initial.json').exists():(base/'initial.json').write_text(json.dumps(state))
            time.sleep(.2)
    finally:
        stop(app); stop(settings); stop(wm)


def launch(base, themes, task):
    env = dict(os.environ)
    for key in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
        path=base/key; path.mkdir(mode=0o700); env[key]=str(path)
    env.update(LUDA_SELECTION_EVAL_PRIVATE='1', XDG_CONFIG_DIRS=env['XDG_CONFIG_HOME'], XDG_DATA_DIRS=f'{themes}:/usr/local/share:/usr/share', XDG_CURRENT_DESKTOP='XFCE', LANG='C.UTF-8', LC_ALL='C.UTF-8', NO_AT_BRIDGE='0', GTK_MODULES='gail:atk-bridge')
    process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1440x1000x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--child',str(base),'--task',task],env=env,start_new_session=True)
    try:return process.wait(timeout=250)
    finally:stop(process)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',type=Path); parser.add_argument('--launch',type=Path)
    parser.add_argument('--themes',type=Path); parser.add_argument('--label',default='trial')
    parser.add_argument('--task',choices=['theme','file'],default='theme'); parser.add_argument('--user'); parser.add_argument('--timeout',type=int,default=180)
    args=parser.parse_args()
    if args.child:child(args.child,args.task); return 0
    if args.launch:return launch(args.launch,args.themes,args.task)
    if not args.themes or not (args.themes/'themes/Greybird-dark/gtk-3.0/gtk.css').exists():parser.error('--themes must contain real themes/Greybird-dark/gtk-3.0/gtk.css')
    prompt = PROMPT if args.task=='theme' else PROMPT.replace('Change XFCE application appearance to a dark theme.','Select Report.txt in the file manager without opening it. Leave it selected and leave the window open.')
    if not args.user:parser.error('--user requires an explicit ordinary desktop account')
    account=pwd.getpwnam(args.user); codex=shutil.which('codex')
    if account.pw_uid==0:parser.error('--user must identify an ordinary desktop account')
    if not 1<=args.timeout<=180:parser.error('--timeout must be 1..180 seconds')
    out=ROOT/'artifacts/agent-selection-effect'/f'{args.label}-{time.time_ns()}';out.mkdir(parents=True)
    result={'label':args.label,'prompt':prompt,'task':args.task,'source_commit':version(['git','rev-parse','HEAD']),'codex':version([codex,'--version']),'passed':False}
    result['source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'skills/luda/SKILL.md',ROOT/'src/luda/ax_worker.py',ROOT/'src/luda/desktop.py',ROOT/'src/luda/server.py',*sorted((ROOT/'skills/luda').rglob('*.md'))]}
    agent=launcher=None
    with tempfile.TemporaryDirectory(prefix='luda-selection-',dir='/workspace') as directory:
        base=Path(directory);base.chmod(0o755)
        desktop=base/'desktop';desktop.mkdir();os.chown(desktop,account.pw_uid,account.pw_gid)
        workspace=base/'workspace';workspace.mkdir();skill=workspace/'.agents/skills/luda/SKILL.md';copy_skill(ROOT/'skills/luda',skill)
        try:
            with (out/'desktop.log').open('wb') as log:
                launcher=subprocess.Popen(['runuser','-u',args.user,'--',str(ROOT/'.venv/bin/python'),__file__,'--launch',str(desktop),'--themes',str(args.themes),'--task',args.task],stdout=log,stderr=log,start_new_session=True)
                end=time.monotonic()+30
                while not (desktop/'ready.json').exists():
                    if launcher.poll() is not None or time.monotonic()>end:raise RuntimeError('Private desktop failed')
                    time.sleep(.1)
                if args.task=='file':
                    end=time.monotonic()+10
                    while not (desktop/'initial.json').exists():
                        if time.monotonic()>end:raise RuntimeError('File oracle not initialized')
                        time.sleep(.1)
                    initial=json.loads((desktop/'initial.json').read_text())
                    if not initial.get('observed_file_roles') or initial['selected'] or initial['opened']:
                        raise RuntimeError('File must be independently observable, unselected and unopened before agent start')
                env=json.loads((desktop/'ready.json').read_text())
                server_args=['-u',args.user,'--','/usr/bin/env',*[f'{k}={v}' for k,v in env.items()],str(ROOT/'.venv/bin/luda')]
                cmd=[codex,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--json','--sandbox','read-only','-C',str(workspace),'-c','approval_policy="never"','-c','mcp_servers.luda.command="/usr/sbin/runuser"','-c','mcp_servers.luda.args='+json.dumps(server_args),'-c','mcp_servers.luda.default_tools_approval_mode="approve"','-c','mcp_servers.luda.required=true','-c','mcp_servers.luda.startup_timeout_sec=20','-c','mcp_servers.luda.tool_timeout_sec=20',prompt]
                started=time.monotonic()
                with (out/'events.jsonl').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
                    agent=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
                    try:result['returncode']=agent.wait(timeout=args.timeout)
                    except subprocess.TimeoutExpired:result['timeout']=True
                    finally:stop(agent)
                result['seconds']=round(time.monotonic()-started,2)
                events=[]
                for line in (out/'events.jsonl').read_text().splitlines():
                    try:events.append(json.loads(line))
                    except ValueError:pass
                result.update(grade_trace(events,skill));result['metrics']=metrics(events)
                result['final_messages']=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
                result['oracle']=json.loads((desktop/'oracle.json').read_text())
                result['initial_oracle']=json.loads((desktop/'initial.json').read_text())
                result['selection_feedback']=[json.loads(c['text']) for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('tool')=='desktop_choose' for c in (e['item'].get('result') or {}).get('content',[]) if c.get('type')=='text']
                result['resolved_model']='Not exposed by CLI JSON; existing CLI default (no override).'
                result['oracle_passed']=(result['oracle']['theme']=='Greybird-dark' if args.task=='theme' else bool(result['oracle']['selected']) and not result['oracle']['opened'] and not result['initial_oracle']['selected'])
                result['trace_constraints_passed']=all(result[k] for k in ('skill_reads_only','only_public_desktop_tools','no_direct_file_changes','no_other_tools'))
                result['passed']=result.get('returncode')==0 and result['oracle_passed'] and result['trace_constraints_passed']
        except Exception as exc:result['harness_error']=str(exc)
        finally:
            (desktop/'stop').touch()
            if launcher:
                try:launcher.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
            stop(agent);stop(launcher)
            (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'artifact_directory':str(out),**result},indent=2));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
