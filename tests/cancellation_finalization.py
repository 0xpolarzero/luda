"""Test-only receipt predicate: process cleanup alone is not server finalization."""
def finalized_cancellation(status, prior_ids):
    if status.get('recovering') is not False:return None
    events=[event for event in status.get('operations',[]) if event.get('operation_id') not in prior_ids and event.get('method')=='type_text']
    if len(events)!=1:return None
    event=events[0]
    return event if event.get('operation_id') and event.get('ok') is False and event.get('code')=='CANCELLED' and event.get('effect')=='uncertain' else None
