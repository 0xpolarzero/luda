"""Provider-local paths must never authorize another same-process AT-SPI tree."""
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from test_semantic import load_worker

w=load_worker()
class Node:
    def __init__(self,bus,path='/root',x=0,children=()):
        self.app=N(bus_name=bus);self.path=path;self.x=x;self.children=list(children)
    def get_process_id(self):return 42
    def get_child_count(self):return len(self.children)
    def get_child_at_index(self,i):return self.children[i]
    def get_interfaces(self):return ['Component']
    def get_component_iface(self):return N(get_extents=lambda _:N(x=self.x,y=0,width=100,height=50))
    def get_parent(self):return None
    def get_name(self):return 'Same visible identity'

class ProviderScope(unittest.TestCase):
    def setUp(self):
        self.a=Node(':1.10');self.b=Node(':1.11',x=200)
        self.desktop=Node(':1.0',children=[Node(':1.11','/app',children=[self.b]),Node(':1.10','/app',children=[self.a])])
        self.description=dict(role='push button',name='Same visible identity',start='1',states=['showing','enabled'],protected=False)
        self.atspi=patch.object(w,'Atspi',N(get_desktop=lambda _:self.desktop,CoordType=N(SCREEN=0)));self.atspi.start();self.addCleanup(self.atspi.stop)
    def inspect(self):
        with patch.object(w,'describe',side_effect=lambda node,pid:dict(self.description,path=node.path,provider_marker=node.app.bus_name)):
            return w.main(dict(op='inspect',pid=42,bounds=dict(x=0,y=0,width=100,height=50),frame_bounds=dict(x=0,y=0,width=100,height=50)))
    def test_geometry_selected_root_stays_in_its_provider(self):
        r=self.inspect();self.assertEqual([n['provider_marker'] for n in r['nodes']],[':1.10']);self.assertEqual(r['nodes'][0]['root_provider'],':1.10')
    def test_mutation_cannot_choose_first_colliding_provider(self):
        target=dict(self.description,root_path='/root',root_bus_guid='a'*32,path='/root',root_provider=':1.10')
        with patch.object(w,'describe',return_value=self.description),patch.object(w,'semantic',return_value={'effect':'verified'}) as action:
            r=w.main(dict(op='check',pid=42,target=target,checked=True))
        self.assertEqual(r['effect'],'verified');self.assertIs(action.call_args.args[0],self.a)
    def test_disappeared_provider_never_rebinds_identical_path(self):
        self.desktop.children=self.desktop.children[:1]
        with patch.object(w,'semantic') as action:
            r=w.main(dict(op='check',pid=42,target=dict(root_path='/root',root_bus_guid='a'*32,path='/root',root_provider=':1.10')))
        self.assertEqual(r['error'],'STALE_TARGET');action.assert_not_called()
    def test_missing_provider_identity_never_widens_scope(self):
        self.assertEqual(list(w.candidates(42,root_path='/root')),[])
    def test_foreign_provider_child_is_incomplete_not_exposed(self):
        self.a.children=[Node(':1.11','/child')]
        r=self.inspect();self.assertTrue(r['truncated']);self.assertEqual(r['unreadable_branches'],1);self.assertEqual(len(r['nodes']),1)
    def test_well_known_alias_not_accepted_as_generation(self):
        for name in ('org.a11y.Application','',':1','sensitive text'):
            with self.subTest(name=name),self.assertRaises(ValueError):w.provider_identity(Node(name))

if __name__=='__main__':unittest.main()
