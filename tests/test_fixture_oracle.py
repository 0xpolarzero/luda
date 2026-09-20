import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from fixture_oracle import wait_text

class FixtureOracle(unittest.IsolatedAsyncioTestCase):
    async def test_delayed_state_after_150ms(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';path.write_text('{"text":""}')
            async def update():
                await asyncio.sleep(.2)
                path.write_text(json.dumps({'text':'new'}))
            task=asyncio.create_task(update())
            result=await wait_text(path,'new',timeout=1)
            await task
            self.assertTrue(result['matched'])
            self.assertGreaterEqual(result['seconds'],.2)

    async def test_stale_prior_payload_is_not_empty_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';path.write_text('{"text":"old"}')
            result=await wait_text(path,'',timeout=.04)
            self.assertFalse(result['matched'])
            self.assertEqual(result['last_state'],{'text':'old'})

    async def test_missing_or_malformed_is_not_empty_text(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json'
            for malformed in (None,'{'):
                if malformed is not None:path.write_text(malformed)
                result=await wait_text(path,'',timeout=.02)
                self.assertFalse(result['matched'])
                self.assertIsNone(result['last_state'])
