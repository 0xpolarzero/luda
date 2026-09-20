# Fresh-agent regression after pointer and topology changes

On 2026-09-20, the existing `scripts/agent_eval.py` ran one fresh attempt each for canvas and draft recovery against immutable revision `2d0ae2df8f11b0a884eb95f9fc21f409aa666723`. Both passed. No failed attempt was discarded and no unchanged-code retry was run.

| First attempt | Wall time | Desktop calls | Server-reported tool time | Independent outcome |
| --- | ---: | ---: | ---: | --- |
| Canvas | 49.199 s | 13 | 2.728 s | Amber, cell B2, board committed |
| Draft recovery | 51.078 s | 19 | 1.586 s | Compact layout, exact Unicode/newline draft saved, one close warning cancelled, no discard, app left open |

Canvas used five observations and four clicks, plus doctor, window discovery, activation and inspection. Draft recovery used six semantic invocations, five inspections, two observations, two window listings, doctor, activation, exact typing and text readback. Neither trace contained a tool error. Each agent read the installed skill once, then used only public desktop tools. Trace grading found no direct application-file access, file changes, program launch, network browsing, or other tool use. Both final app states exactly matched independent fixture-written oracles.

CLI-reported cumulative usage—not unique prompt size—was:

| Task | Input tokens | Cached input | Output tokens |
| --- | ---: | ---: | ---: |
| Canvas | 196,410 | 174,080 | 726 |
| Draft recovery | 258,558 | 220,672 | 930 |

The draft agent correctly distinguished rendering from data integrity: Japanese characters appeared as missing-font boxes in the final screenshot, while exact text readback and the independent oracle retained the Japanese string. The final screenshot was independently inspected and confirms the rendering problem. Basic CJK font provisioning remains actionable; this run does not establish full international text rendering. No pointer/topology or recovery friction appeared in these two samples, and they do not establish a statistical success rate.

The full traces and oracle results are retained under `artifacts/agent-eval/run-1789868964968900166/`, including `canvas-01` and `recovery-01`. Both source fingerprints were unchanged, SHA256 `7a92c6fb450c304c7b4898251d5c44fc2362efe6c6abc5a0279215df717512d4`. The private-session cleanup found no tagged process survivors. Run output is additionally retained in `/tmp/luda-agent-regression.log` on the qualification VM.
