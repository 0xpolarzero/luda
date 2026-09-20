"""Bounded read-only polling of independent fixture state; never retries input."""
import asyncio
import json
import time

async def wait_text(path, expected, timeout=2.0):
    began=time.monotonic()
    last=None
    samples=0
    while True:
        try:
            last=json.loads(path.read_text())
        except (FileNotFoundError,json.JSONDecodeError):
            last=None
        samples+=1
        elapsed=time.monotonic()-began
        matched=isinstance(last,dict) and last.get('text')==expected
        if matched or elapsed>=timeout:
            return {'matched':matched,'seconds':elapsed,'samples':samples,'last_state':last}
        await asyncio.sleep(min(.02,max(0,timeout-elapsed)))
