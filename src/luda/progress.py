"""Strict payload-free final-receipt progress; never a resume/replay instruction."""
def selection_progress(value):
    keys={'unit','requested','verified_completed','current_uncertain','not_started','application_commit_verified'}
    if not isinstance(value,dict) or set(value)!=keys or value['unit']!='selection_step' or value['application_commit_verified'] is not False:return None
    count,done,partial,pending=(value[k] for k in ('requested','verified_completed','current_uncertain','not_started'))
    if any(type(n) is not int for n in (count,done,partial,pending)):return None
    if not 0<=count<=550 or not 0<=done<=count or partial not in (0,1) or not 0<=pending<=count or done+partial+pending!=count:return None
    return dict(value)

def operation_progress(value):
    if not isinstance(value, dict):
        return None
    if value.get('unit') == 'selection_step':
        return selection_progress(value)
    from .keyboard import key_dispatch_progress
    return key_dispatch_progress(value)


