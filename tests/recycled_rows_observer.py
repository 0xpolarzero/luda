"""Independent read-only provider-path evidence, never supplies UI input."""
import gi,json,sys
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
Atspi.set_timeout(600,1000)
root=Atspi.get_desktop(0);pid=int(sys.argv[1]);nodes=[]
for index in range(root.get_child_count()):
 app=root.get_child_at_index(index)
 if app.get_process_id()==pid:nodes.append(app)
result=[];budget=200
while nodes and budget:
 node=nodes.pop(0);budget-=1
 if node.get_role_name()=='table cell':result.append({'name':node.get_name(),'path':node.path,'provider':node.app.bus_name})
 nodes.extend(node.get_child_at_index(i) for i in range(node.get_child_count()))
assert not nodes,'Observer traversal budget exceeded'
print(json.dumps(result))
