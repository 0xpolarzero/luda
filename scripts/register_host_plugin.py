#!/usr/bin/env python3
"""Explicit registration into one selected host Codex profile; never a default profile."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import uuid


class RegistrationError(Exception):
    pass


def read_json(path):
    with path.open('rb') as stream:
        data=stream.read(1048577)
    if len(data)>1048576:raise RegistrationError('metadata_limit')
    return json.loads(data)


def atomic(path,value):
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    try:
        with temporary.open('x') as stream:json.dump(value,stream)
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def cli(executable,home,*arguments):
    # A failed CLI can echo local configuration; return only a fixed stage code.
    with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as error:
        child=subprocess.Popen([str(executable),*arguments,'--json'],env={**os.environ,'CODEX_HOME':str(home)},
                               stdin=subprocess.DEVNULL,stdout=output,stderr=error,start_new_session=True)
        try:
            code=child.wait(timeout=30)
        except BaseException:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait();raise
        if code:raise RegistrationError('codex_command_failed')
        output.seek(0);data=output.read(1048577)
        if len(data)>1048576:raise RegistrationError('codex_output_limit')
        return json.loads(data)


def validate_bundle(market):
    meta=read_json(market/'host-registration.json')
    identity=uuid.UUID(meta['vm_id']).hex
    if meta.get('format')!=1 or meta.get('plugin')!='luda-'+identity or meta.get('marketplace')!='silo-'+identity:
        raise RegistrationError('bundle_identity_invalid')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}',meta.get('version','')):
        raise RegistrationError('bundle_version_invalid')
    if meta.get('server_name')!='ld-'+identity:
        raise RegistrationError('bundle_server_identity_invalid')
    plugin=market/'plugins'/meta['plugin']
    if set(read_json(plugin/'.mcp.json').get('mcpServers',{}))!={meta['server_name']}:
        raise RegistrationError('bundle_server_identity_invalid')
    manifest=read_json(plugin/'.codex-plugin/plugin.json')
    if manifest.get('name')!=meta['plugin'] or manifest.get('version')!=meta['version']:
        raise RegistrationError('bundle_manifest_mismatch')
    catalog=read_json(market/'.agents/plugins/marketplace.json')
    if catalog.get('name')!=meta['marketplace'] or len(catalog.get('plugins',[]))!=1 or catalog['plugins'][0].get('name')!=meta['plugin'] or catalog['plugins'][0].get('source')!={'source':'local','path':'./plugins/'+meta['plugin']}:
        raise RegistrationError('bundle_catalog_mismatch')
    for file,key in (('.mcp.json','mcp_sha256'),('skills/luda/SKILL.md','skill_sha256')):
        if hashlib.sha256((plugin/file).read_bytes()).hexdigest()!=meta.get(key):raise RegistrationError('bundle_content_changed')
    if any(p.is_symlink() for p in market.rglob('*')):raise RegistrationError('bundle_symlink')
    return meta


def register(market,codex_executable,codex_home,runner=cli):
    market=Path(market);executable=Path(codex_executable);home=Path(codex_home)
    if not all(p.is_absolute() for p in (market,executable,home)):
        raise RegistrationError('explicit_absolute_paths_required')
    if not executable.is_file() or not os.access(executable,os.X_OK):raise RegistrationError('codex_executable_unavailable')
    if not home.is_dir() or home.is_symlink() or home.stat().st_uid!=os.getuid() or home.stat().st_mode&0o022:
        raise RegistrationError('profile_must_exist_and_be_owned')
    meta=validate_bundle(market);market=market.resolve();plugin_id=meta['plugin']+'@'+meta['marketplace']
    fd=os.open(home/'.luda-registration.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipts=home/'luda-registrations'
        if receipts.is_symlink():raise RegistrationError('receipt_directory_invalid')
        receipts.mkdir(exist_ok=True,mode=0o700)
        receipt=receipts/(meta['plugin']+'.json')
        previous=read_json(receipt) if receipt.exists() else None
        desired={'plugin_id':plugin_id,'marketplace_root':str(market),'version':meta['version'],
                 'skill_sha256':meta['skill_sha256'],'mcp_sha256':meta['mcp_sha256']}
        if previous and previous.get('identity')!=desired:raise RegistrationError('registration_conflict')
        def run(*args):return runner(executable,home,*args)
        markets=run('plugin','marketplace','list')['marketplaces']
        matches=[m for m in markets if m.get('name')==meta['marketplace']]
        if matches and (len(matches)!=1 or matches[0].get('marketplaceSource')!={'sourceType':'local','source':str(market)}):
            raise RegistrationError('marketplace_conflict')
        installed=run('plugin','list')['installed']
        entries=[p for p in installed if p.get('pluginId')==plugin_id]
        def verify(entries):
            if len(entries)!=1 or entries[0].get('enabled') is not True or entries[0].get('version')!=meta['version']:
                raise RegistrationError('installed_plugin_conflict')
            cached=home/'plugins/cache'/meta['marketplace']/meta['plugin']/meta['version']
            for file,key in (('.mcp.json','mcp_sha256'),('skills/luda/SKILL.md','skill_sha256')):
                if hashlib.sha256((cached/file).read_bytes()).hexdigest()!=meta[key]:raise RegistrationError('cached_content_mismatch')
            effective=[entry for entry in run('mcp','list') if entry.get('name')==meta['server_name']]
            expected=read_json(cached/'.mcp.json')['mcpServers'][meta['server_name']]
            if len(effective)!=1 or effective[0].get('enabled') is not True:
                raise RegistrationError('effective_server_conflict')
            transport=effective[0].get('transport',{})
            # Codex profile overrides can retain argv while changing the process
            # context. Verify the actual stdio launch, not only cached bytes.
            if (transport.get('type')!='stdio'
                    or any(transport.get(key)!=expected[key] for key in ('command','args'))
                    or ({} if transport.get('env') is None else transport['env'])!=({} if expected.get('env') is None else expected['env'])
                    or ([] if transport.get('env_vars') is None else transport['env_vars'])!=([] if expected.get('env_vars') is None else expected['env_vars'])
                    or transport.get('cwd')!=expected.get('cwd')):
                raise RegistrationError('effective_server_conflict')
        if entries:
            verify(entries)
            atomic(receipt,{'state':'registered','identity':desired})
            return {'status':'already_registered','plugin_id':plugin_id,'server_name':meta['server_name'],'vm_id':meta['vm_id'],'verified_cached_content':True,'restart_required':True}
        if previous:raise RegistrationError('previous_attempt_requires_review')
        stage='marketplace_add'
        atomic(receipt,{'state':'pending','stage':stage,'identity':desired})
        try:
            if not matches:run('plugin','marketplace','add',str(market))
            stage='plugin_add';atomic(receipt,{'state':'pending','stage':stage,'identity':desired})
            run('plugin','add',plugin_id)
            stage='verification'
            verify([p for p in run('plugin','list')['installed'] if p.get('pluginId')==plugin_id])
            atomic(receipt,{'state':'registered','identity':desired})
        except Exception:
            # No rollback/removal of a possibly successful registration. A later
            # inspection can confirm it, but never blindly repeats a failed add.
            atomic(receipt,{'state':'unconfirmed','stage':stage,'identity':desired})
            return {'status':'unconfirmed','stage':stage,'plugin_id':plugin_id,'automatic_retry_allowed':False,
                    'next_step':'Inspect this profile with codex plugin list/marketplace list. Rerun only to verify a completed installation; an incomplete attempt requires explicit administrative review.'}
        return {'status':'registered','plugin_id':plugin_id,'server_name':meta['server_name'],'vm_id':meta['vm_id'],'verified_cached_content':True,'restart_required':True}
    finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--marketplace-root',required=True,type=Path)
    parser.add_argument('--codex-executable',required=True,type=Path)
    parser.add_argument('--codex-home',required=True,type=Path)
    args=parser.parse_args()
    try:result=register(args.marketplace_root,args.codex_executable,args.codex_home)
    except RegistrationError as exc:
        result={'status':'refused','code':str(exc),'automatic_retry_allowed':False}
    except (OSError,ValueError,KeyError,TypeError):
        result={'status':'refused','code':'bundle_or_profile_invalid','automatic_retry_allowed':False}
    print(json.dumps(result));return 0 if result['status'] in ('registered','already_registered') else 1

if __name__=='__main__':raise SystemExit(main())
