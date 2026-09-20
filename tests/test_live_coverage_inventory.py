"""Static inventory validation must never execute runner or fixture code."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('live_inventory',ROOT/'scripts/build_live_coverage.py')
inventory=importlib.util.module_from_spec(spec);spec.loader.exec_module(inventory)

class LiveInventory(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup);self.root=Path(self.directory.name)
        for name in ('scripts','tests','docs'):(self.root/name).mkdir()
        (self.root/'docs/requirements.json').write_text(json.dumps({'features':[{'cases':[{'id':'CASE-01'}]}]}))
        self.sentinel=self.root/'must-not-execute'
        forbidden=f"\nraise RuntimeError('must not import this source')\n"
        (self.root/'scripts/qualification_matrix.py').write_text("SUITES={'a':suite('live_a.py','CASE-01',gaps=('Known unsupported path',))}"+forbidden)
        (self.root/'scripts/native_app_tests.py').write_text("SUITES={'b':'live_b.py'}"+forbidden)
        (self.root/'scripts/headless_tests.py').write_text("def main():\n suites=[('shared',[str(ROOT/'tests/live_a.py')])]\n"+forbidden)
        for name in ('live_a.py','live_b.py'):
            (self.root/'tests'/name).write_text(f'"""Owned synthetic fixture."""\nfrom pathlib import Path\nPath({str(self.sentinel)!r}).touch()\n')
        self.metadata={'scripts':{'live_b.py':{'requirements':['CASE-01'],'scope':'Independent native file oracle.','limits':'Only owned files.'}}};self.write_metadata()
    def write_metadata(self):(self.root/'docs/live-suite-map.json').write_text(json.dumps(self.metadata))
    def test_static_parse_deduplicates_script_and_never_executes_sources(self):
        rows,unregistered,total=inventory.load_inventory(self.root)
        self.assertEqual(len(rows),2);self.assertEqual(len(rows[0]['runners']),2)
        self.assertEqual(rows[0]['limits'],['Known unsupported path'])
        self.assertFalse(self.sentinel.exists());self.assertEqual(unregistered,[]);self.assertEqual(total,1)
    def test_unknown_requirement_id_rejected(self):
        self.metadata['scripts']['live_b.py']['requirements']=['NONEXISTENT'];self.write_metadata()
        with self.assertRaisesRegex(ValueError,'Unknown requirement'):inventory.load_inventory(self.root)
    def test_missing_fixture_rejected(self):
        (self.root/'tests/live_b.py').unlink()
        with self.assertRaisesRegex(ValueError,'Missing fixture'):inventory.load_inventory(self.root)
    def test_missing_supplemental_associations_rejected(self):
        self.metadata['scripts']={};self.write_metadata()
        with self.assertRaisesRegex(ValueError,'Missing supplemental'):inventory.load_inventory(self.root)
    def test_duplicate_requirement_source_rejected(self):
        self.metadata['scripts']['live_a.py']={'requirements':['CASE-01']};self.write_metadata()
        with self.assertRaisesRegex(ValueError,'Duplicate matrix/supplement'):inventory.load_inventory(self.root)
    def test_stale_metadata_and_duplicate_ids_rejected(self):
        self.metadata['scripts']['live_b.py']['requirements']=['CASE-01','CASE-01'];self.write_metadata()
        with self.assertRaisesRegex(ValueError,'Duplicate requirement IDs'):inventory.load_inventory(self.root)
        self.metadata['scripts']={'old.py':{'requirements':['CASE-01']}};self.write_metadata()
        with self.assertRaisesRegex(ValueError,'Stale supplemental'):inventory.load_inventory(self.root)
    def test_unregistered_script_is_listed_without_execution_or_invented_status(self):
        (self.root/'tests/live_extra.py').write_text("raise RuntimeError('do not import')")
        rows,unregistered,_=inventory.load_inventory(self.root)
        self.assertEqual(unregistered,['live_extra.py'])
        rendered=inventory.render(self.root)
        self.assertIn('assigns no current pass/fail status',rendered)
        self.assertIn('Known unsupported path',rendered)
        self.assertTrue(all('status' not in row and 'passed' not in row for row in rows))
    def test_real_generated_inventory_is_current(self):
        self.assertEqual((ROOT/'docs/LIVE-COVERAGE.md').read_text(),inventory.render(ROOT))

if __name__=='__main__':unittest.main()
