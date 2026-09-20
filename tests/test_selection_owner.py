import unittest
from unittest.mock import patch
from luda.common import DesktopError
from luda.x11 import X11

class SelectionOwnerTests(unittest.TestCase):
    @patch('luda.x11.run',side_effect=[b'{"result":1}',b'{"result":null}',b'{"result":42}'])
    def test_unowned_and_owned_selections(self,run):
        x=X11();self.assertIsNone(x.selection_owner());self.assertEqual(x.selection_owner('PRIMARY'),42)
    @patch('luda.x11.run',return_value=b'{"result":1}')
    def test_other_atoms_rejected(self,run):
        x=X11();run.reset_mock()
        for name in ('SECONDARY','clipboard','',None,True,[]):
            with self.subTest(name=name),self.assertRaises(DesktopError):x.selection_owner(name)
        run.assert_not_called()

if __name__=='__main__':unittest.main()
