# Final standalone local verification

At `3f9da53`, root ran924 tests in35.577seconds:923passed, one build-tool skip. The ordinary account ran924 in35.747seconds:921passed, three environment-dependent skips. Actual wheel-build tests separately passed using locked build tools. Source stayed unchanged during both runs. The revised input-generation case passed through the normal private headless runner in0.580seconds with unchanged source.

Runtime, skill, plugin configuration and runtime dependencies are unchanged from the standalone source830a3c4. That source passed all17 local native suites, actual installation and installed MCP, and hosted desktop, native applications, media and plugin registration. Later source301a535 passed hosted browser/installed-browser, native applications, media and plugin registration. Its desktop job timed out in the old asynchronous-stop fixture; the original failure and scoped local correction are retained separately. These distinct runs are not combined into a fictional all-green single run.

The new hosted rerun for3f9da53 was still in progress when this report was written. No claim is made about its future outcome. Local checks for the two harness corrections passed; neither correction changes the production runtime.
