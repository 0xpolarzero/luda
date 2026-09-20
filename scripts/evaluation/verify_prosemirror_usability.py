"""Read-only verification after the interactive MCP workflow has finished."""
import hashlib
import json
from pathlib import Path
import sys

run = Path(sys.argv[1])
rows = [json.loads(line) for line in (run / 'trace.jsonl').read_text().splitlines()]
text_responses = [json.loads(row['response']['content'][0]['text']) for row in rows]
reads = [response for response in text_responses if 'text' in response]
assert reads[0]['text'] == reads[1]['text'] == 'Bold prefix: '
assert reads[0]['model'] == reads[1]['model']
refusal = next(r for r in text_responses if r.get('code') == 'LINE_BREAK_SEMANTICS_REQUIRED')
assert refusal['effect'] == 'none'
expected = 'Bold prefix: 東京 😀 é\n\nFinal Ω\n'
assert reads[-1]['text'] == expected
saved = json.loads((run / 'saved-model.json').read_text())
assert saved['model'] == reads[-1]['model']
assert saved['paragraphs'] == expected.split('\n')
assert saved['strong'] == ['Bold prefix: 東京 😀 é']
assert 'marks' not in saved['model']['content'][2]['content'][0]
assert len([r for r in rows if r['request']['name'] == 'desktop_invoke']) == 1
proof = {'exact_text': True, 'four_paragraphs_including_blank_and_trailing': True,
         'bold_prefix_preserved': True, 'first_append_bold_later_paragraph_plain': True,
         'missing_policy_refused_and_readback_unchanged': True,
         'independent_save_matches_model_readback': True,
         'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [run / 'trace.jsonl', run / 'saved-model.json']}}
(run / 'verification.json').write_text(json.dumps(proof, indent=2))
print(json.dumps(proof, indent=2))
