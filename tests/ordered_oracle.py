"""Test-only HTTP snapshot ordering; never an application mutation driver."""
def accept_snapshot(current, incoming):
    keys=('oracle_document','oracle_sequence')
    if not isinstance(incoming,dict) or any(type(incoming.get(k)) is not int or incoming[k]<1 for k in keys):
        return False
    if current and tuple(incoming[k] for k in keys)<=tuple(current[k] for k in keys):
        return False
    current.clear();current.update(incoming)
    return True
