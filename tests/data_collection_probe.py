"""Read-only provider diagnostic for an owned grid fixture."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/luda'))
import ax_worker as w
A=w.Atspi
rows=[]
for node,depth in w.candidates(int(sys.argv[1]),depth=1):
 if depth!=1:continue
 row={'root':node.path,'name':node.get_name()}
 try:
  states=A.StateSet.new([A.StateType.EDITABLE,A.StateType.SHOWING])
  rule=A.MatchRule.new(states,A.CollectionMatchType.ALL,{},A.CollectionMatchType.ALL,[A.Role.ENTRY,A.Role.TEXT],A.CollectionMatchType.ANY,[],A.CollectionMatchType.ALL,False)
  matches=A.Collection.get_matches(node.get_collection_iface(),rule,A.CollectionSortOrder.CANONICAL,20,True)
  row['matches']=[{'path':n.path,'role':n.get_role_name(),'name':n.get_name(),'parent':n.get_parent().path if n.get_parent() else None} for n in matches]
 except Exception as exc:row['error']=str(exc)
 try:
  active=A.Collection.get_active_descendant(node.get_collection_iface());row['active']=active.path if active else None
 except Exception as exc:row['active_error']=str(exc)
 row['exhaustive_diagnostic']=[];stats={};count=0
 for child,_ in w.candidates(int(sys.argv[1]),limit=6000,depth=30,root_path=node.path,stats=stats):
  count+=1;states=w.states_of(child);role=child.get_role_name()
  if role in ('entry','text') or 'editable' in states or 'focused' in states:
   row['exhaustive_diagnostic'].append({'role':role,'name':child.get_name(),'states':list(states),'interfaces':child.get_interfaces(),'path':child.path})
 row['diagnostic_count']=count;row['diagnostic_coverage']=stats
 rows.append(row)
print(json.dumps(rows))
