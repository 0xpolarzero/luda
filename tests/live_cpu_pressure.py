"""PERF-10: one-CPU scheduling pressure with an independent unpinned watchdog."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qualification_matrix import private_environment,cleanup_owned,owned_processes
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
OUT=ROOT/'artifacts/cpu-pressure'
BASELINE='before CPU pressure\n'
PRESSURE='under CPU pressure 日本語\n'
RECOVERED='after CPU pressure recovered 👩🏽‍💻\n'


def write(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2));temporary.replace(path)


def load_worker(base,index,cpu):
    os.sched_setaffinity(0,{cpu});resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    began=time.monotonic();cpu_start=time.process_time()
    info={'pid':os.getpid(),'cpu':cpu,'affinity':sorted(os.sched_getaffinity(0)),'nice':os.getpriority(os.PRIO_PROCESS,0),'began':began}
    write(base/f'load-{index}-ready.json',info)
    value=1
    while time.monotonic()-began<25 and not (base/'end-load').exists():
        for _ in range(20000):value=(value*1664525+1013904223)&0xffffffff
    info.update(ended=time.monotonic(),cpu_seconds=time.process_time()-cpu_start)
    write(base/f'load-{index}-result.json',info)


async def actor(base):
    trace=[];records=[];wm=app=None
    def record(case,passed,**details):
        records.append({'case':case,'passed':bool(passed),**details});write(base/'actor-result.json',{'cases':records,'trace':trace})
    def state():return json.loads((base/'widget/state.json').read_text())
    async def until(fn,timeout=8):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            result=await fn()
            if result:return result
            await asyncio.sleep(.05)
        raise RuntimeError('Bounded fixture condition failed')
    try:
        wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        async def ready_wm():return subprocess.run(['wmctrl','-m'],capture_output=True,timeout=2).returncode==0
        await until(ready_wm)
        app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),str(base/'widget')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        async with stdio_client(StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ))) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                async def call(name,allow_error=False,**arguments):
                    began=time.monotonic();response=await asyncio.wait_for(session.call_tool(name,arguments),timeout=15)
                    value=json.loads(response.content[0].text)
                    trace.append({'tool':name,'began':began,'ended':time.monotonic(),'seconds':time.monotonic()-began,'error':response.isError,'result':value})
                    write(base/'trace.json',trace)
                    if response.isError and not allow_error:raise RuntimeError(name+': '+value.get('code','unknown'))
                    return value
                async def find_window():return next((w for w in (await call('desktop_windows'))['windows'] if w['pid']==app.pid),None)
                window=await until(find_window);wid=window['window_id']
                await call('desktop_activate',window_id=wid)
                tree=await call('desktop_inspect',window_id=wid)
                element=next(n for n in tree['nodes'] if n['name']=='Contract text')
                await call('desktop_type',element_id=element['element_id'],mode='replace',text=BASELINE)
                async def baseline():return state()['text']==BASELINE
                await until(baseline)
                await call('desktop_observe')
                write(base/'ready.json',{'actor_pid':os.getpid(),'app_pid':app.pid,'nice':os.getpriority(os.PRIO_PROCESS,0),'affinity':sorted(os.sched_getaffinity(0))})
                async def loaded():return (base/'go').exists()
                await until(loaded)
                began=time.monotonic()
                response=await call('desktop_type',allow_error=True,element_id=element['element_id'],mode='replace',text=PRESSURE)
                duration=time.monotonic()-began
                allowed_failure=response.get('code') in ('TIMEOUT','ACCESSIBILITY_ERROR','ACCESSIBILITY_UNAVAILABLE','RESOURCE_UNAVAILABLE','BACKEND_ERROR') and response.get('effect') in ('none','uncertain')
                record('pressure-response-bounded-and-useful',duration<15 and (response.get('ok') is True and response.get('effect')=='verified' or allowed_failure),seconds=duration,response=response)
                status=await call('desktop_status')
                record('status-responsive-under-pressure',status.get('ok') is True and not status.get('recovering'),seconds=trace[-1]['seconds'])
                write(base/'pressure-done.json',{'response':response,'widget_at_response':state(),'began':began,'ended':time.monotonic()})
                async def no_load():return (base/'load-ended').exists()
                await until(no_load,timeout=30)
                await asyncio.sleep(.4)
                observed=state()['text'];expected=PRESSURE if response.get('ok') else BASELINE if response.get('effect')=='none' else None
                record('independent-post-load-effects',observed==expected if expected is not None else observed in (BASELINE,PRESSURE),text=observed,reported_effect=response.get('effect'),no_retry=True)
                prior=observed;await asyncio.sleep(.4)
                record('post-load-widget-remains-stable',state()['text']==prior)
                tree=await call('desktop_inspect',window_id=wid)
                fresh=next(n for n in tree['nodes'] if n['name']=='Contract text')
                recovered=await call('desktop_type',element_id=fresh['element_id'],mode='replace',text=RECOVERED)
                async def recovered_state():return state()['text']==RECOVERED
                await until(recovered_state)
                record('new-explicit-request-recovers',recovered.get('effect')=='verified',text=state()['text'])
                write(base/'finished.json',{'passed':all(r['passed'] for r in records)})
    except Exception as exc:
        record('harness-failure',False,error=type(exc).__name__,message=str(exc));raise
    finally:
        for process in (app,wm):
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)


def sample(token):
    rows=[]
    for pid,start in owned_processes(token).items():
        try:
            proc=Path('/proc')/str(pid);fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
            threads={p.name:list(map(int,(p/'schedstat').read_text().split())) for p in (proc/'task').iterdir()}
            try:autogroup=(proc/'autogroup').read_text().strip()
            except OSError:autogroup=None
            rows.append({'thread_schedstats':threads,'autogroup':autogroup,'pid':pid,'start':start,'name':(proc/'comm').read_text().strip(),'nice':os.getpriority(os.PRIO_PROCESS,pid),'affinity':sorted(os.sched_getaffinity(pid)),'cpu_seconds':(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK'),'schedstat':list(map(int,(proc/'schedstat').read_text().split()))})
        except (OSError,ValueError):pass
    return {'time':time.monotonic(),'processes':rows}


def controller():
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Ordinary UID and private matrix required')
    allowed=sorted(os.sched_getaffinity(0))
    if len(allowed)<2 or os.getpriority(os.PRIO_PROCESS,0)!=0:raise RuntimeError('Need at least two allowed CPUs and a normal-priority unpinned watchdog')
    OUT.mkdir(parents=True,exist_ok=True);cpu=allowed[0];token=uuid.uuid4().hex;children=[];samples=[];records=[];started=time.monotonic()
    result={'uid':os.getuid(),'selected_cpu':cpu,'watchdog_affinity':allowed,'watchdog_nice':0,'records':records}
    with tempfile.TemporaryDirectory(prefix='luda-cpu-pressure-') as directory:
        base=Path(directory);(base/'environment').mkdir();(base/'widget').mkdir()
        env=private_environment(base/'environment',token)
        log=(OUT/'actor.log').open('wb')
        def wait_file(path,timeout):
            end=time.monotonic()+timeout
            while not path.exists():
                if time.monotonic()>end or time.monotonic()-started>70:raise RuntimeError('Independent watchdog deadline exceeded')
                if children and children[0].poll() is not None:raise RuntimeError('Desktop actor exited before requested phase')
                time.sleep(.05)
        try:
            actor_process=subprocess.Popen([sys.executable,__file__,'--launch',str(base),'--cpu',str(cpu)],env=env,stdout=log,stderr=log,start_new_session=True);children.append(actor_process)
            wait_file(base/'ready.json',15);result['desktop']=json.loads((base/'ready.json').read_text())
            for index in range(2):
                children.append(subprocess.Popen([sys.executable,__file__,'--load',str(base),'--index',str(index),'--cpu',str(cpu)],env=env,stdout=log,stderr=log,start_new_session=True))
                wait_file(base/f'load-{index}-ready.json',3)
            load_started=time.monotonic();samples.append(sample(token));(base/'go').touch()
            while not (base/'pressure-done.json').exists():
                if time.monotonic()-load_started>23:raise RuntimeError('Pressure response exceeded independent 23-second phase watchdog')
                samples.append(sample(token));time.sleep(.2)
            while time.monotonic()-load_started<5:time.sleep(.05)
            samples.append(sample(token));(base/'end-load').touch()
            for process in children[1:]:process.wait(timeout=3)
            workers=[json.loads((base/f'load-{i}-result.json').read_text()) for i in range(2)];result['load_workers']=workers
            wall=max(w['ended'] for w in workers)-min(w['began'] for w in workers);cpu_time=sum(w['cpu_seconds'] for w in workers)
            records.append({'case':'measured-single-cpu-contention','passed':all(w['affinity']==[cpu] and w['nice']==0 for w in workers) and wall>=5 and .5<cpu_time/wall<1.05,'wall_seconds':wall,'worker_cpu_seconds':cpu_time,'single_cpu_busy_fraction':cpu_time/wall})
            pressure=json.loads((base/'pressure-done.json').read_text());result['pressure_interval']={'began':pressure['began'],'ended':pressure['ended']}
            records.append({'case':'both-workers-active-through-pressure-request','passed':all(w['began']<=pressure['began']<pressure['ended']<=w['ended'] for w in workers)})
            service_pids={result['desktop']['actor_pid'],result['desktop']['app_pid']}
            service_rows=[p for p in samples[0]['processes'] if p['pid'] in service_pids or p['name'] in ('luda','Xvfb','xfwm4')]
            records.append({'case':'reduced-weight-desktop-separate-watchdog','passed':len(service_rows)>=5 and all(p['nice']==15 and p['affinity']==[cpu] for p in service_rows) and len(allowed)>1,'observed_services':service_rows})
            (base/'load-ended').touch();wait_file(base/'finished.json',18);actor_process.wait(timeout=5)
            result['actor']=json.loads((base/'actor-result.json').read_text());result['passed']=all(r['passed'] for r in records) and all(r['passed'] for r in result['actor']['cases']) and actor_process.returncode==0
        except Exception as exc:result.update(passed=False,error={'type':type(exc).__name__,'message':str(exc)})
        finally:
            (base/'end-load').touch()
            for name in ('trace.json','actor-result.json','pressure-done.json'):
                if (base/name).exists():(OUT/name).write_bytes((base/name).read_bytes())
            result['cleanup']=cleanup_owned(token)
            for process in children:
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:result['passed']=False
            if result['cleanup']['survivors']:result['passed']=False
            result['samples']=samples;result['seconds']=time.monotonic()-started
            write(OUT/'results.json',result);log.close()
    print(json.dumps({k:v for k,v in result.items() if k not in ('samples','actor')},indent=2))
    return 0 if result.get('passed') else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--launch',type=Path);parser.add_argument('--actor',type=Path);parser.add_argument('--load',type=Path);parser.add_argument('--cpu',type=int);parser.add_argument('--index',type=int);args=parser.parse_args()
    if args.load:load_worker(args.load,args.index,args.cpu)
    elif args.launch:
        os.sched_setaffinity(0,{args.cpu});os.nice(15)
        os.execvp('xvfb-run',['xvfb-run','-a','-s','-screen 0 1200x900x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--actor',str(args.launch)])
    elif args.actor:asyncio.run(actor(args.actor))
    else:raise SystemExit(controller())
