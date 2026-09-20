#!/usr/bin/env python3
"""One held-out soft-line-break edit, five-minute first attempt only."""
import json
from pathlib import Path
import importlib.util
_spec=importlib.util.spec_from_file_location('hard_break_harness',Path(__file__).resolve().with_name('agent_rich_eval.py'))
harness=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(harness)
harness.__file__=__file__
harness.ASSETS=harness.ROOT/'tests/fixtures/agent-hard-breaks'
harness.MAX_TIMEOUT=300;harness.CHILD_SECONDS=345;harness.TASK_DIRECTORY='agent-hard-breaks'
harness.REQUIRED_OBSERVATIONS=()
harness.PREFIX=PREFIX='Plan 🧭: ';harness.MIDDLE=MIDDLE='old meeting details';harness.SUFFIX=SUFFIX=' — approved'
harness.INSERT=INSERT='Arrive 08:45\nCafé terrace\nBring 日本語 notes'


def prompt(url):
 return ('Open '+url+' in a temporary browser session and edit Meeting note. Replace only '+json.dumps(MIDDLE)+' with these three lines: '+json.dumps(INSERT,ensure_ascii=False)+'. Use soft line breaks within the same paragraph, like Shift+Enter, rather than starting new paragraphs. Keep the bold prefix and italic suffix exactly as they are, with their formatting. Save using the visible Save meeting note button and verify the result. Mention any clipboard side effect in your final response. Use only public Luda desktop MCP tools. Read the installed Luda skill first at .agents/skills/luda/SKILL.md. Do not inspect application source or hidden files, run other programs, change files directly, or browse other sites.')


def grade(actual):
 paragraphs=actual.get('model',{}).get('content',[]);runs=[];breaks=0
 for index,paragraph in enumerate(paragraphs):
  if index:runs.append(('\n',('paragraph',)))
  for node in paragraph.get('content',[]):
   marks=tuple(sorted(m.get('type') for m in node.get('marks',[])))
   if node.get('type')=='hard_break':runs.append(('\n',marks));breaks+=1
   else:runs.extend((c,marks) for c in node.get('text',''))
 return {'exact_logical_text':''.join(c for c,_ in runs)==PREFIX+INSERT+SUFFIX,
         'one_paragraph_two_hard_breaks':len(paragraphs)==1 and breaks==2,
         'prefix_marks':runs[:len(PREFIX)]==[(c,('strong',)) for c in PREFIX],
         'suffix_marks':runs[-len(SUFFIX):]==[(c,('em',)) for c in SUFFIX],
         'caret_after_insert':actual.get('modelCaretCodePoints')==len(PREFIX+INSERT)}

harness.task_prompt=prompt;harness.grade=grade
if __name__=='__main__':raise SystemExit(harness.main())
