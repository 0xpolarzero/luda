import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('provision_firefox',Path(__file__).resolve().parents[1]/'scripts/provision_firefox.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class Provision(unittest.TestCase):
    def test_verified_archive_extracts_and_records_manifest(self):
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w:xz') as tar:
            info=tarfile.TarInfo('firefox/firefox');info.size=4;tar.addfile(info,io.BytesIO(b'test'))
        data=archive.getvalue();checksum=hashlib.sha256(data).hexdigest()
        sums=(checksum+'  '+p.ARCHIVE+'\n').encode()
        with tempfile.TemporaryDirectory() as base, patch.object(p,'SHA256',checksum), patch.object(p.urllib.request,'urlopen',side_effect=[io.BytesIO(sums),io.BytesIO(data)]):
            directory=Path(base)/'browser';p.main(directory)
            self.assertEqual((directory/'firefox/firefox').read_bytes(),b'test')
            self.assertIn(checksum,(directory/'provision.json').read_text())
    def test_upstream_mismatch_refuses_archive_download(self):
        with tempfile.TemporaryDirectory() as base, patch.object(p.urllib.request,'urlopen',return_value=io.BytesIO(('0'*64+'  '+p.ARCHIVE+'\n').encode())) as download:
            with self.assertRaises(RuntimeError):p.main(Path(base)/'browser')
            self.assertEqual(download.call_count,1)
    def test_archive_mismatch_never_extracts(self):
        sums=(p.SHA256+'  '+p.ARCHIVE+'\n').encode()
        with tempfile.TemporaryDirectory() as base, patch.object(p.urllib.request,'urlopen',side_effect=[io.BytesIO(sums),io.BytesIO(b'corrupt')]):
            directory=Path(base)/'browser'
            with self.assertRaises(RuntimeError):p.main(directory)
            self.assertFalse((directory/'firefox').exists())
    def test_existing_destination_never_overwritten(self):
        with tempfile.TemporaryDirectory() as base, patch.object(p.urllib.request,'urlopen') as download:
            with self.assertRaises(FileExistsError):p.main(base)
            download.assert_not_called()

if __name__=='__main__':unittest.main()
