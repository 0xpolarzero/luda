from pathlib import Path
import sys,subprocess,tarfile,zipfile,hashlib,json
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root/'scripts'))
from manage_install import build_source,release_identity
out=Path(sys.argv[2]).resolve();out.mkdir(exist_ok=False)
python=sys.argv[3]
with build_source(root,out,release_identity(root)) as staged:
 subprocess.run([python,'-I','-c','import setuptools.build_meta as b; b.build_wheel(sys.argv[1])' .replace('import setuptools','import sys; import setuptools'),str(out)],cwd=staged,check=True)
 subprocess.run([python,'-I','-c','import sys; import setuptools.build_meta as b; b.build_sdist(sys.argv[1])',str(out)],cwd=staged,check=True)
wheel=next(out.glob('*.whl'));sdist=next(out.glob('*.tar.gz'))
expected={str(p.relative_to(root/'src')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'src/luda').rglob('*.py')}
with zipfile.ZipFile(wheel) as z:
 actual={p:hashlib.sha256(z.read(p)).hexdigest() for p in z.namelist() if p.startswith('luda/') and p.endswith('.py')}
 assert actual==expected
 skill=next(p for p in z.namelist() if p.endswith('/skills/luda/SKILL.md'))
 assert z.read(skill)==(root/'skills/luda/SKILL.md').read_bytes()
with tarfile.open(sdist) as t:
 names=t.getnames()
 assert not any('/integrations/silo/' in p or '/historical-reports/' in p or 'node_modules/' in p for p in names)
 for path,digest in expected.items():
  entry=next(p for p in names if p.endswith('/src/'+path))
  assert hashlib.sha256(t.extractfile(entry).read()).hexdigest()==digest
result={'modules':len(expected),'skill_matches':True,'sdist_excludes_removed_integration_and_historical_reports':True,'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [wheel,sdist]}}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
