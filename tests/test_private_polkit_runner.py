import hashlib,importlib.util,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('private_polkit_tests',ROOT/'scripts/private_polkit_tests.py')
import sys
sys.path.insert(0,str(ROOT/'scripts'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class PrivatePolkitRunnerTests(unittest.TestCase):
 def test_changed_or_linked_package_refused_before_any_provisioning(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);(p/'a.deb').write_bytes(b'wrong')
   with patch.dict(module.PACKAGES,{'a.deb':hashlib.sha256(b'right').hexdigest()},clear=True):
    with self.assertRaises(ValueError):module.checked_packages(p)
    (p/'a.deb').unlink();(p/'target').write_bytes(b'right');(p/'a.deb').symlink_to(p/'target')
    with self.assertRaises(ValueError):module.checked_packages(p)
 def test_only_pinned_bytes_are_staged_not_extra_packages(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);(p/'a.deb').write_bytes(b'right');(p/'extra.deb').write_bytes(b'ignored')
   with patch.dict(module.PACKAGES,{'a.deb':hashlib.sha256(b'right').hexdigest()},clear=True):self.assertEqual(module.checked_packages(p),{'a.deb':b'right'})
 def test_namespace_helper_refuses_direct_execution_before_mutation(self):
  with tempfile.TemporaryDirectory() as directory:
   r=subprocess.run(['/bin/bash',str(ROOT/'tests/private_polkit_namespace.sh'),directory,str(ROOT)],capture_output=True,timeout=2)
   self.assertNotEqual(r.returncode,0);self.assertEqual(list(Path(directory).iterdir()),[])
if __name__=='__main__':unittest.main()
