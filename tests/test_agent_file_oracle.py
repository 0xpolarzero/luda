import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('agent_file_oracle',Path(__file__).resolve().parents[1]/'scripts/agent_file_oracle.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)

class AgentFileOracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.before=oracle.seed(self.root);self.watch=oracle.ProtectedWatch(self.root/'Sorted'/oracle.RESUME);self.addCleanup(self.watch.close)
    def finish(self):
        (self.root/'Inbox'/oracle.JOURNEY).rename(self.root/'Sorted'/oracle.JOURNEY)
        shutil.copyfile(self.root/'Inbox'/oracle.RESUME,self.root/'Sorted'/oracle.COPY)
        (self.root/'References'/oracle.JOURNEY).symlink_to('../Sorted/'+oracle.JOURNEY)
    def test_initial_state_is_not_success(self):self.assertFalse(oracle.grade(self.root,self.before,self.watch.drain())['exact'])
    def test_required_result_passes(self):
        self.finish();self.assertTrue(oracle.grade(self.root,self.before,self.watch.drain())['exact'])
    def test_rewrite_same_protected_bytes_fails(self):
        self.finish();(self.root/'Sorted'/oracle.RESUME).write_bytes(oracle.PROTECTED)
        self.assertFalse(oracle.grade(self.root,self.before,self.watch.drain())['cases']['protected_destination_never_rewritten'])
    def test_regular_copy_is_not_symlink(self):
        self.finish();link=self.root/'References'/oracle.JOURNEY;link.unlink();link.write_bytes(oracle.PAYLOADS[oracle.JOURNEY])
        self.assertFalse(oracle.grade(self.root,self.before,self.watch.drain())['cases']['real_symlink_to_moved_file'])
    def test_unrequested_extra_file_fails(self):
        self.finish();(self.root/'Inbox'/'extra').touch();self.assertFalse(oracle.grade(self.root,self.before,self.watch.drain())['exact'])
