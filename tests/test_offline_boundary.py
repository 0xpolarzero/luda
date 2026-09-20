"""Network proof must reject accessible canaries or an unchanged host namespace."""
import errno
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('offline_probe',Path(__file__).parent/'evidence/offline-startup/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

class OfflineBoundary(unittest.TestCase):
    def check(self,results,namespace='net:[2]',interfaces=None,routes='header\n'):
        socket=Mock();socket.__enter__=Mock(return_value=socket);socket.__exit__=Mock(return_value=False);socket.connect_ex.side_effect=results
        with patch.object(probe.os,'readlink',return_value=namespace),patch.object(probe.socket,'if_nameindex',return_value=interfaces if interfaces is not None else [(1,'lo')]),patch.object(probe.socket,'socket',return_value=socket),patch.object(probe.Path,'read_text',return_value=routes):
            return probe.network_proof('net:[1]',1234)
    def test_requires_separate_route_free_namespace_and_failed_canaries(self):
        failed=[errno.ENETUNREACH,errno.ENETUNREACH,errno.EADDRNOTAVAIL]
        result=self.check(failed);self.assertTrue(result['namespace_differs_from_host'])
        for kwargs in ({'namespace':'net:[1]'},{'interfaces':[(1,'lo'),(2,'eth0')]},{'routes':'header\neth0 route\n'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(AssertionError):self.check(failed,**kwargs)
        for index in range(3):
            results=list(failed);results[index]=0
            with self.subTest(reachable=index),self.assertRaises(AssertionError):self.check(results)
    def test_timeout_is_not_misreported_as_kernel_denial(self):
        with self.assertRaises(AssertionError):self.check([errno.ETIMEDOUT]*3)
