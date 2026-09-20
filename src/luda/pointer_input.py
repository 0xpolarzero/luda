"""Bounded one-shot clicks/wheels with supervised owned-button release."""
import json
import sys
from .common import DesktopError,run
from .keyboard import _dispatch_plan,keyboard_recovery_checkpoint


def click_button(button,count=1,target=None):
    if button not in ('1','2','3','4','5','6','7') or type(count) is not int or not 1<=count<=20:
        raise DesktopError('INVALID_ARGUMENT','Expected pointer button 1–7 and count 1–20.')
    if target is not None and (type(target) is not int or not 0<target<=0xffffffff):
        raise DesktopError('INVALID_ARGUMENT','Invalid native pointer target.')
    keyboard_recovery_checkpoint()
    request={'button':button,'count':count,'target':target}
    plan=json.loads(run([sys.executable,'-m','luda._pointer_native','plan'],data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096))
    if plan.get('code'):raise DesktopError(plan['code'],plan['message'],effect=plan.get('effect','none'))
    return _dispatch_plan(plan)
