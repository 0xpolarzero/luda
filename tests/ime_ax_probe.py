"""Read-only synthetic-fixture AT-SPI evidence; never changes IME state."""
import json
import sys
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
Atspi.set_timeout(600,1000)
pid=int(sys.argv[1]);queue=[Atspi.get_desktop(0)];results=[]
for _ in range(200):
    if not queue:break
    node=queue.pop(0)
    if node.get_process_id()==pid and node.get_name()=='Composition field':
        result={'states':[s.value_nick for s in node.get_state_set().get_states()],'attributes':node.get_attributes(),'interfaces':node.get_interfaces()}
        if 'Text' in result['interfaces']:
            text=node.get_text_iface();count=Atspi.Text.get_character_count(text)
            result['text']=Atspi.Text.get_text(text,0,count)
            result['text_attributes']=[Atspi.Text.get_attribute_run(text,i,True)[0] for i in range(count)]
        results.append(result)
    queue.extend(node.get_child_at_index(i) for i in range(min(node.get_child_count(),100)))
print(json.dumps(results,ensure_ascii=False))
