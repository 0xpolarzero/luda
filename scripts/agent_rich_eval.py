#!/usr/bin/env python3
"""One first-attempt rich-edit task, existing CLI auth, ordinary private GUI."""
import argparse,hashlib,http.server,json,os,pwd,shutil,subprocess,sys,tempfile,threading,time
from pathlib import Path
from agent_eval import grade_trace,stop,version
from agent_file_eval import tool_failures
from agent_trace_metrics import metrics
from qualify import source_fingerprint
ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'tests/fixtures/agent-rich-clipboard'
PREFIX='Pré 👩🏽‍💻: ';MIDDLE='ancien é';SUFFIX=' / FIN';INSERT='nouveau 日本語\n\tÉté 👩🏽‍💻\n'


def grade(actual):
    expected=PREFIX+INSERT+SUFFIX
    runs=[]
    for i,p in enumerate(actual.get('model',{}).get('content',[])):
        if i:runs.append(('\n',()))
        for n in p.get('content',[]):
            marks=tuple(sorted(m.get('type') for m in n.get('marks',[])))
            runs.extend((c,marks) for c in n.get('text',''))
    return {'exact_text':''.join(c for c,_ in runs)==expected,
            'exact_paragraphs':actual.get('paragraphs')==expected.split('\n'),
            'prefix_marks':runs[:len(PREFIX)]==[(c,('strong',)) for c in PREFIX],
            'suffix_marks':runs[-len(SUFFIX):]==[(c,('em',)) for c in SUFFIX],
            'trusted_paste':any(e.get('type')=='paste' and e.get('trusted') for e in actual.get('events',[]))}


def child(base):
    wm=None;service=None
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            routes={'/':ASSETS/'index.html','/app.js':ASSETS/'app.bundle.js','/bridge.mjs':ROOT/'integrations/prosemirror/luda-prosemirror.mjs'}
            path=routes.get(self.path)
            if path is None:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8' if self.path=='/' else 'text/javascript');self.end_headers();self.wfile.write(path.read_bytes())
        def do_POST(self):
            if self.path!='/save':self.send_error(404);return
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<1048576:self.send_error(413);return
            value=json.loads(self.rfile.read(size));temporary=base/'saved.tmp';temporary.write_text(json.dumps(value,ensure_ascii=False));temporary.replace(base/'saved.json')
            self.send_response(204);self.end_headers()
    try:
        wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        end=time.monotonic()+8
        while subprocess.run(['wmctrl','-m'],capture_output=True,timeout=2).returncode:
            if time.monotonic()>end:raise RuntimeError('Private window manager unavailable')
            time.sleep(.05)
        service=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=service.serve_forever,daemon=True).start()
        keys=('DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','XDG_RUNTIME_DIR','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_CONFIG_DIRS','LANG','LC_ALL','PATH','LUDA_CHROMIUM_EXECUTABLE')
        (base/'ready.json').write_text(json.dumps({'uid':os.getuid(),'url':f'http://127.0.0.1:{service.server_port}/','environment':{k:os.environ[k] for k in keys if k in os.environ}}))
        end=time.monotonic()+220
        while not (base/'stop').exists() and time.monotonic()<end:time.sleep(.05)
    finally:
        if service:service.shutdown();service.server_close()
        stop(wm)


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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--child',type=Path);parser.add_argument('--launch',type=Path);parser.add_argument('--executable');parser.add_argument('--timeout',type=int,default=180);args=parser.parse_args()
    if args.child:child(args.child);return 0
    if args.launch:return launch(args.launch)
    if os.getuid()!=0:parser.error('Existing root CLI authentication is used; desktop/MCP drop to the ordinary account.')
    if not 1<=args.timeout<=180:parser.error('Bound must be1..180 seconds')
    codex=shutil.which('codex');account=pwd.getpwnam('silo-desktop')
    if not codex or not args.executable:parser.error('Existing Codex CLI and explicitly provisioned Chromium required')
    out=ROOT/'artifacts/agent-rich'/('run-'+str(time.time_ns()));out.mkdir(parents=True)
    result={'attempt':1,'passed':False,'source_before':source_fingerprint(ROOT),'codex':version([codex,'--version']),'browser':version([args.executable,'--version']),'resolved_model':'unknown unless exposed by CLI JSON','agent_uid':os.getuid(),'desktop_uid':account.pw_uid,'budget_seconds':args.timeout}
    launcher=agent=None
    with tempfile.TemporaryDirectory(prefix='luda-agent-rich-') as directory:
        base=Path(directory);base.chmod(0o711);desktop=base/'desktop';desktop.mkdir(mode=0o700);os.chown(desktop,account.pw_uid,account.pw_gid)
        workspace=base/'workspace';workspace.mkdir();skill=workspace/'.agents/skills/luda/SKILL.md';skill.parent.mkdir(parents=True);shutil.copyfile(ROOT/'skills/luda/SKILL.md',skill)
        try:
            with (out/'desktop.log').open('wb') as log:
                launcher=subprocess.Popen(['/usr/sbin/runuser','-u','silo-desktop','--','/usr/bin/env','LUDA_CHROMIUM_EXECUTABLE='+args.executable,str(ROOT/'.venv/bin/python'),__file__,'--launch',str(desktop)],stdout=log,stderr=log,start_new_session=True)
                end=time.monotonic()+30
                while not (desktop/'ready.json').exists():
                    if launcher.poll() is not None or time.monotonic()>end:raise RuntimeError('Private desktop startup failed')
                    time.sleep(.05)
                ready=json.loads((desktop/'ready.json').read_text())
                prompt='Use a temporary browser session to open '+ready['url']+' and edit Travel note. Replace only the unique middle text '+json.dumps(MIDDLE,ensure_ascii=False)+' with exactly this JSON string: '+json.dumps(INSERT,ensure_ascii=False)+'. Preserve the existing bold prefix and italic suffix, including all their characters and formatting. Save the travel note through its visible Save button and verify the saved result. In your final response mention any clipboard side effect. Use only public Luda desktop MCP tools for this task. Read the installed Luda skill first; you may read .agents/skills/luda/SKILL.md. Do not read application source, hidden files or oracle data, run other programs, modify files directly, or browse other sites.'
                result['prompt']=prompt
                server_args=['-u','silo-desktop','--','/usr/bin/env',*[k+'='+v for k,v in ready['environment'].items()],str(ROOT/'.venv/bin/luda')]
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
                actual=json.loads((desktop/'saved.json').read_text()) if (desktop/'saved.json').exists() else {};result['oracle']=actual;result['oracle_checks']=grade(actual)
                calls=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
                result['exact_range_observed']=any(c.get('tool')=='desktop_select' and c.get('arguments',{}).get('start_offset')==len(PREFIX) and c.get('arguments',{}).get('end_offset')==len(PREFIX+MIDDLE) for c in calls)
                result['explicit_clipboard_observed']=any(c.get('tool')=='desktop_type' and c.get('arguments',{}).get('transport')=='clipboard' for c in calls)
                result['final_messages']=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
                result['source_after']=source_fingerprint(ROOT);result['source_unchanged']=result['source_before']==result['source_after']
                result['passed']=result.get('returncode')==0 and all(result['oracle_checks'].values()) and result['source_unchanged'] and all(result[k] for k in ('skill_reads_only','only_public_desktop_tools','no_direct_file_changes','no_other_tools','no_injected_actions','exact_range_observed','explicit_clipboard_observed'))
        except Exception as exc:result['harness_error']={'type':type(exc).__name__,'message':str(exc)}
        finally:
            (desktop/'stop').touch()
            if launcher:
                try:launcher.wait(timeout=6)
                except subprocess.TimeoutExpired:pass
            stop(agent);stop(launcher);(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'artifact_directory':str(out),'passed':result['passed'],'seconds':result.get('seconds'),'harness_error':result.get('harness_error')},ensure_ascii=False));return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
