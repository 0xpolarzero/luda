#!/usr/bin/env python3
"""Fail closed when the pinned test CLI is absent; run private-profile contracts."""
import contextlib
import tempfile
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

TOOL = Path(__file__).resolve().parent
ROOT = TOOL.parents[2]
EXPECTED = 'codex-cli 0.155.1'


def main():
    executable = TOOL/'node_modules/.bin/codex'
    if not executable.is_file():
        raise SystemExit('Pinned Codex CLI missing: run npm ci in tests/tools/codex-cli.')
    version = subprocess.run([str(executable), '--version'], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    if version != EXPECTED:
        raise SystemExit('Pinned Codex CLI version mismatch.')
    os.environ['PATH'] = str(executable.parent)+os.pathsep+os.environ.get('PATH','')
    suite = unittest.TestSuite()
    for pattern in ('test_plugin_bundle.py',):
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'tests'), pattern=pattern))
    suite.addTests(unittest.defaultTestLoader.discover(str(TOOL), pattern='test_setup_discovery.py', top_level_dir=str(TOOL)))
    # Exercise real pinned upstream installers, not a parallel config writer.
    with contextlib.ExitStack() as resources:
        if not os.environ.get('LUDA_TEST_AGENT_TOOLS'):
            (ROOT / 'artifacts').mkdir(exist_ok=True)
            release = Path(resources.enter_context(tempfile.TemporaryDirectory(prefix='agent-tools-', dir=ROOT / 'artifacts')))
            sys.path.insert(0, str(ROOT / 'scripts'))
            from provision_agent_tools import provision
            provision(release, ROOT / 'scripts/agent-tools')
            os.environ['LUDA_TEST_AGENT_TOOLS'] = str(release / 'agent-tools')
            resources.callback(os.environ.pop, 'LUDA_TEST_AGENT_TOOLS', None)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = {'cli_version': version, 'package_lock_sha256': hashlib.sha256((TOOL/'package-lock.json').read_bytes()).hexdigest(),
                'tests_run':result.testsRun, 'skipped':len(result.skipped), 'passed':result.wasSuccessful() and not result.skipped,
                'scope':'Actual CLI registration/cache/resolved configuration and generated setup skill discovery via app-server in temporary profiles; no model calls or authentication-file access, graphical access tested separately.'}
    output = ROOT/'artifacts/codex-cli-registration';output.mkdir(parents=True, exist_ok=True)
    (output/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence))
    return 0 if evidence['passed'] and result.testsRun else 1


if __name__ == '__main__':
    raise SystemExit(main())
