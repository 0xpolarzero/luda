#!/usr/bin/env python3
"""Verify the pinned GitHub archive against a trusted local Git tree; never install it."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True,help='Trusted local Luda repository')
    parser.add_argument('--manifest',type=Path,required=True,help='Reviewed candidate with exact URL/hash/commit')
    parser.add_argument('--output',type=Path,required=True,help='New private evidence directory')
    args=parser.parse_args();args.output.mkdir(mode=0o700)
    candidate=json.loads(args.manifest.read_text());commit=candidate['source_commit'];root_name='luda-'+commit
    def git(*values):return subprocess.check_output(['git','--no-replace-objects','-C',str(args.repo),*values])
    assert git('rev-parse',commit).decode().strip()==commit
    # Trusted LOCAL committed extractor, not code read from downloaded bytes.
    helper=args.output/'reviewed-local-guest.py'
    helper.write_bytes(git('show',commit+':integrations/silo/guest/agent-tools.py'))
    spec=importlib.util.spec_from_file_location('reviewed_guest',helper)
    guest=importlib.util.module_from_spec(spec);spec.loader.exec_module(guest)
    assert guest.manifest(args.manifest)==candidate
    archive=args.output/'source.tar.gz';guest.download(candidate,archive)
    sha=hashlib.sha256(archive.read_bytes()).hexdigest();assert sha==candidate['source_sha256']
    entries={};directories={root_name}
    for raw in git('ls-tree','-rz','--full-tree',commit).split(b'\0'):
        if not raw:continue
        metadata,name=raw.split(b'\t',1);mode,kind,oid=metadata.decode().split()
        assert kind=='blob' and mode in ('100644','100755')
        name=name.decode();entries[name]=(mode,oid)
        parts=name.split('/')
        directories.update(root_name+'/'+('/'.join(parts[:n])) for n in range(1,len(parts)))
    files=set();dirs=set();seen=set();expanded=0
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            assert member.name not in seen;seen.add(member.name)
            if member.isdir():
                dirs.add(member.name);assert member.mode==0o775;continue
            assert member.isfile() and member.name.startswith(root_name+'/')
            name=member.name[len(root_name)+1:];files.add(name);mode,oid=entries[name]
            assert member.mode==(0o775 if mode=='100755' else 0o664)
            assert tar.extractfile(member).read()==git('cat-file','blob',oid),name
            expanded+=member.size
    assert files==set(entries) and dirs==directories
    extracted=guest.extract(archive,args.output/'extracted',commit)
    for name,(mode,oid) in entries.items():
        path=extracted/name;assert path.read_bytes()==git('cat-file','blob',oid),name
        assert path.stat().st_mode&0o777==(0o755 if mode=='100755' else 0o644),name
    result={'commit':commit,'source_url':candidate['source_url'],'source_sha256':sha,
            'compressed_bytes':archive.stat().st_size,'expanded_file_bytes':expanded,
            'git_files_exact':len(files),'directory_entries_exact':len(dirs),'tar_entries':len(seen),
            'git_executable_bits_exact':True,'guest_extraction_content_and_normalized_modes_exact':True,
            'downloaded_code_executed':False,'candidate_manifest_validated_only_not_enabled':True}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
