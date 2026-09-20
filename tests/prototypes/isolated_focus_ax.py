import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi

def walk(n):
 if n.get_name()=='agent':
  def entry(x):
   if x.get_role_name()=='text':return x
   for i in range(x.get_child_count()):
    r=entry(x.get_child_at_index(i))
    if r:return r
  e=entry(n)
  if e:print(e.get_component_iface().grab_focus());return True
 for i in range(n.get_child_count()):
  if walk(n.get_child_at_index(i)):return True
 return False
assert walk(Atspi.get_desktop(0))
