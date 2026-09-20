"""Real compressed archives; small injected budgets exercise production boundaries."""
import errno
import gzip
import io
import tempfile
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_silo_integration import tools, COMMIT, REQUIRED, archive


class ArchiveStreamBoundsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'source.tar.gz'

    def metadata_archive(self, format, oversized=False):
        with tarfile.open(self.path,'w:gz',format=format) as output:
            for name in REQUIRED:
                member=tarfile.TarInfo('luda-'+COMMIT+'/'+name);member.size=1
                if format==tarfile.PAX_FORMAT:member.pax_headers={'comment':'x'*(32768 if oversized else 10)}
                output.addfile(member,io.BytesIO(b'x'))
            if format==tarfile.GNU_FORMAT:
                member=tarfile.TarInfo('luda-'+COMMIT+'/'+('x'*(32768 if oversized else 120)))
                member.size=1;output.addfile(member,io.BytesIO(b'x'))

    def test_oversized_pax_and_gnu_metadata_rejected_before_parser(self):
        for format in (tarfile.PAX_FORMAT,tarfile.GNU_FORMAT):
            with self.subTest(format=format):
                self.metadata_archive(format,True)
                with patch.object(tools,'MAX_TAR_STREAM',16384),patch.object(tools.tarfile,'open') as parser:
                    with self.assertRaisesRegex(tools.OnboardingError,'tar_stream_limit'):
                        tools.extract(self.path,self.root/'output',COMMIT)
                    parser.assert_not_called()
                self.assertFalse((self.root/'output').exists())

    def test_valid_pax_and_gnu_extract(self):
        for format in (tarfile.PAX_FORMAT,tarfile.GNU_FORMAT):
            self.metadata_archive(format)
            output=tools.extract(self.path,self.root/str(format),COMMIT)
            self.assertEqual((output/'pyproject.toml').read_bytes(),b'x')

    def test_padding_and_concatenated_gzip_count_toward_total(self):
        archive(self.path);raw=gzip.decompress(self.path.read_bytes())
        self.path.write_bytes(self.path.read_bytes()+gzip.compress(b'\0'*20000))
        with patch.object(tools,'MAX_TAR_STREAM',len(raw)+100),patch.object(tools.tarfile,'open') as parser:
            with self.assertRaisesRegex(tools.OnboardingError,'tar_stream_limit'):
                tools.extract(self.path,self.root/'output',COMMIT)
            parser.assert_not_called()

    def test_exact_total_boundary_and_payload_limit_remain_distinct(self):
        archive(self.path);length=len(gzip.decompress(self.path.read_bytes()))
        with patch.object(tools,'MAX_TAR_STREAM',length):
            tools.extract(self.path,self.root/'exact',COMMIT)
        with patch.object(tools,'MAX_TAR_STREAM',length-1):
            with self.assertRaisesRegex(tools.OnboardingError,'tar_stream_limit'):
                tools.extract(self.path,self.root/'short',COMMIT)
        with patch.object(tools,'MAX_EXPANDED',1):
            with self.assertRaisesRegex(tools.OnboardingError,'expanded_limit'):
                tools.extract(self.path,self.root/'payload',COMMIT)

    def test_malformed_streams_report_fixed_error_and_close_spool(self):
        archive(self.path);valid=self.path.read_bytes()
        for index,data in enumerate((b'private malformed gzip',valid[:-5],gzip.compress(b'private malformed tar'))):
            self.path.write_bytes(data);opened=[];real=tempfile.TemporaryFile
            def temporary(**kw):
                result=real(**kw);opened.append(result);return result
            with patch.object(tools.tempfile,'TemporaryFile',side_effect=temporary):
                with self.assertRaisesRegex(tools.OnboardingError,'^archive_invalid$'):
                    tools.extract(self.path,self.root/str(index),COMMIT)
            self.assertTrue(opened[0].closed)

    def test_giant_declared_pax_size_is_rejected_without_giant_read(self):
        header=tarfile.TarInfo('metadata');header.type=tarfile.XHDTYPE;header.size=2**63
        self.path.write_bytes(gzip.compress(header.tobuf(format=tarfile.GNU_FORMAT)+b'\0'*1024))
        with self.assertRaisesRegex(tools.OnboardingError,'^archive_invalid$'):
            tools.extract(self.path,self.root/'declared',COMMIT)
        raw=io.BytesIO(b'abc');bounded=tools.BoundedTarFile(raw,3)
        self.assertEqual(bounded.read(2**100),b'abc')
        with self.assertRaises(tools.OnboardingError):bounded.seek(4)

    def test_bad_gzip_crc_is_rejected_before_parser(self):
        archive(self.path);data=bytearray(self.path.read_bytes());data[-8]^=1;self.path.write_bytes(data)
        with patch.object(tools.tarfile,'open') as parser:
            with self.assertRaisesRegex(tools.OnboardingError,'^archive_invalid$'):
                tools.extract(self.path,self.root/'crc',COMMIT)
            parser.assert_not_called()

    def test_recursive_metadata_chain_has_fixed_failure(self):
        header=tarfile.TarInfo('metadata');header.type=tarfile.XHDTYPE;header.size=0
        self.path.write_bytes(gzip.compress(header.tobuf()*1500+b'\0'*1024))
        with self.assertRaisesRegex(tools.OnboardingError,'^archive_invalid$'):
            tools.extract(self.path,self.root/'recursive',COMMIT)

    def test_disk_failure_is_safe_and_never_parsed(self):
        archive(self.path)
        with patch.object(tools.tempfile,'TemporaryFile',side_effect=OSError(errno.ENOSPC,'private path')),patch.object(tools.tarfile,'open') as parser:
            with self.assertRaisesRegex(tools.OnboardingError,'^archive_invalid$'):
                tools.extract(self.path,self.root/'output',COMMIT)
            parser.assert_not_called()
