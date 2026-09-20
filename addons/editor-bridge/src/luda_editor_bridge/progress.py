"""Strict payload-free final-receipt progress; never a resume/replay instruction."""
MAX_RICH_SEGMENTS = 27


def rich_text_progress(value, expected_count=None):
    keys = {'unit', 'requested', 'verified_completed', 'current_uncertain',
            'not_started', 'application_commit_verified'}
    if not isinstance(value, dict) or set(value) != keys:
        return None
    if value['unit'] != 'rich_text_segment' or value['application_commit_verified'] is not False:
        return None
    count, done, partial, pending = (value[k] for k in
        ('requested', 'verified_completed', 'current_uncertain', 'not_started'))
    if any(type(n) is not int for n in (count, done, partial, pending)):
        return None
    if not 1 <= count <= MAX_RICH_SEGMENTS or not 0 <= done <= count or partial not in (0, 1) or not 0 <= pending <= count:
        return None
    if done + partial + pending != count or expected_count is not None and count != expected_count:
        return None
    return dict(value)



class RichProgress:
    def __init__(self, requested):
        self.value = dict(unit='rich_text_segment', requested=requested,
            verified_completed=0, current_uncertain=0, not_started=requested,
            application_commit_verified=False)

    def begin(self):
        if not self.value['current_uncertain']:
            self.value['current_uncertain'] = 1
            self.value['not_started'] -= 1

    def complete(self):
        self.begin()  # Empty segments may be verified without content dispatch.
        self.value['verified_completed'] += 1
        self.value['current_uncertain'] = 0

def operation_progress(value):
    from luda.progress import operation_progress as core_progress
    return rich_text_progress(value) or core_progress(value)
