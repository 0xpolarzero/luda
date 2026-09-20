#!/usr/bin/env python3
"""Inventory declared live-suite associations without importing executable code."""
import argparse
import ast
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def assignment(path,name):
    tree=ast.parse(path.read_text(),filename=str(path))
    found=[node.value for node in ast.walk(tree) if isinstance(node,ast.Assign)
           and any(isinstance(target,ast.Name) and target.id==name for target in node.targets)]
    if len(found)!=1:raise ValueError(f'{path.name}: expected exactly one {name} assignment')
    return found[0]


def registrations(root):
    rows=[]
    matrix=assignment(root/'scripts/qualification_matrix.py','SUITES')
    if not isinstance(matrix,ast.Dict):raise ValueError('Matrix SUITES must be a literal dictionary')
    for key,value in zip(matrix.keys,matrix.values):
        if not isinstance(value,ast.Call) or not isinstance(value.func,ast.Name) or value.func.id!='suite':
            raise ValueError('Matrix entry must be a declarative suite call')
        keywords={item.arg:ast.literal_eval(item.value) for item in value.keywords}
        rows.append({'runner':'qualification_matrix.py','name':ast.literal_eval(key),
                     'script':ast.literal_eval(value.args[0]),'requirements':ast.literal_eval(value.args[1]).split(),
                     'limits':list(keywords.get('gaps',()))})
    native=ast.literal_eval(assignment(root/'scripts/native_app_tests.py','SUITES'))
    rows.extend({'runner':'native_app_tests.py','name':name,'script':script} for name,script in native.items())
    headless=assignment(root/'scripts/headless_tests.py','suites')
    if not isinstance(headless,ast.List):raise ValueError('Headless suites must be a literal list')
    for entry in headless.elts:
        if not isinstance(entry,ast.Tuple) or len(entry.elts)!=2:raise ValueError('Invalid headless suite entry')
        scripts=[node.value for node in ast.walk(entry.elts[1]) if isinstance(node,ast.Constant)
                 and isinstance(node.value,str) and node.value.startswith('tests/') and node.value.endswith('.py')]
        if len(scripts)!=1:raise ValueError('Headless suite must identify exactly one fixture script')
        rows.append({'runner':'headless_tests.py','name':ast.literal_eval(entry.elts[0]),'script':Path(scripts[0]).name})
    names=[(row['runner'],row['name']) for row in rows]
    if len(names)!=len(set(names)):raise ValueError('Duplicate runner suite names')
    return rows


def load_inventory(root=ROOT):
    catalog=json.loads((root/'docs/requirements.json').read_text())
    ids={case['id'] for feature in catalog['features'] for case in feature['cases']}
    metadata=json.loads((root/'docs/live-suite-map.json').read_text())['scripts']
    rows=registrations(root);merged={}
    for row in rows:
        script=row['script']
        if not isinstance(script,str) or Path(script).name!=script or not script.endswith('.py'):
            raise ValueError('Invalid fixture filename')
        path=root/'tests'/script
        if not path.is_file():raise ValueError(f'Missing fixture: {script}')
        item=merged.setdefault(script,{'script':script,'runners':[],'requirements':None,'limits':[],
            'scope':(ast.get_docstring(ast.parse(path.read_text())) or 'Read the linked fixture assertions.').splitlines()[0]})
        item['runners'].append((row['runner'],row['name']))
        if 'requirements' in row:
            if item['requirements'] is not None:raise ValueError(f'Duplicate requirement declarations: {script}')
            item['requirements']=row['requirements'];item['limits']+=row['limits']
    if set(metadata)-set(merged):raise ValueError(f'Stale supplemental entries: {sorted(set(metadata)-set(merged))}')
    for script,item in merged.items():
        supplement=metadata.get(script,{})
        if 'requirements' in supplement:
            if item['requirements'] is not None:raise ValueError(f'Duplicate matrix/supplement requirement declarations: {script}')
            item['requirements']=supplement['requirements']
        if item['requirements'] is None:raise ValueError(f'Missing supplemental requirement associations: {script}')
        values=item['requirements']
        if not isinstance(values,list) or not all(isinstance(v,str) for v in values):raise ValueError('Requirement IDs must be strings')
        if len(values)!=len(set(values)):raise ValueError(f'Duplicate requirement IDs: {script}')
        if set(values)-ids:raise ValueError(f'Unknown requirement IDs for {script}: {sorted(set(values)-ids)}')
        if supplement.get('scope'):item['scope']=supplement['scope']
        if supplement.get('limits'):item['limits'].append(supplement['limits'])
        if not item['limits']:item['limits']=['Declared fixture scope only; no current result is inferred. Consult its assertions and matching run artifacts.']
    unregistered=sorted(p.name for p in (root/'tests').glob('live_*.py') if p.name not in merged)
    return sorted(merged.values(),key=lambda x:x['script']),unregistered,len(ids)


def render(root=ROOT):
    rows,unregistered,total=load_inventory(root)
    associated={case for row in rows for case in row['requirements']}
    def clean(value):return value.replace('|','\\|').replace('\n',' ')
    lines=['# Live-suite requirement inventory','',
      'Generated by `python3 scripts/build_live_coverage.py`; use `--check` to detect drift. Runner declarations and fixture docstrings are parsed as Python syntax, never imported or executed. Acceptance text is not copied here: IDs link to the authoritative [catalog](REQUIREMENTS.md).','',
      f'{len(rows)} distinct fixture scripts are registered across the broad matrix, headless and native-app runners, with {len(associated)} distinct declared requirement associations out of {total} catalog cases. This is an inventory count, not a coverage score. Every case remains release-unqualified.','',
      'A unit-map “no evidence” status means no mapped unit assertion. It does not mean a live workflow is absent. Conversely, association with a live suite does not imply that the requirement passed: some suites deliberately expose failing or unsupported cases. This document reads no result artifacts and assigns no current pass/fail status. Match any actual run to its source hashes, environment, versions, failure transcript and independent oracle.','',
      'Matrix IDs and declared gaps come from [qualification_matrix.py](../scripts/qualification_matrix.py). Associations absent from the headless/native runner source are maintained once in [live-suite-map.json](live-suite-map.json), keyed by fixture filename. Shared scripts are listed once. See [the metadata audit](LIVE-MAPPING-AUDIT.md) for corrected earlier labels; old raw artifacts remain unchanged.','',
      '| Fixture and registered runners | Associated requirements | Declared scope and limits |','|---|---|---|']
    for row in rows:
        fixture=f"[{row['script']}](../tests/{row['script']})"
        runners='; '.join(f'[{runner}:{name}](../scripts/{runner})' for runner,name in row['runners'])
        cases=', '.join(f'[{case}](REQUIREMENTS.md)' for case in row['requirements']) or 'No catalog association declared'
        lines.append(f"| {fixture}<br>{runners} | {cases} | {clean(row['scope'])} **Limits:** {clean(' '.join(row['limits']))} |")
    lines+=['','## Outside these three runner registrations','',
      'These existing live scripts are not registered in the three inventoried runners. They may have standalone commands or historical evidence; no status or requirement mapping is fabricated here. This list is generated from filenames, not imported tests.','']
    lines += [f'- [{name}](../tests/{name})' for name in unregistered] or ['None.']
    lines+=['','## Separate evidence needing curated association','',
      '- [Agent evaluation runner](../scripts/agent_eval.py), [agent evaluation records](AGENT-EVALUATION.md) and [fresh-agent regression](AGENT-USABILITY-REGRESSION.md) are review candidates for INTEL-01/02/03/05/08/09/10 and EVAL-01/05/09/10; this is not a new formal mapping. These runs are not part of the three runner registries. They do not by themselves establish MCP-01 fresh Mac-to-Codex SSH onboarding.',
      '- Standalone font diagnostics are review candidates for OBS-11; native RandR probes for GEO-06/08/10; private storage-filesystem probes for LIFE-09/FAULT-09; native editor workflows in live_apps.py for FILE-01/02/03. These need their own scoped associations and exact recorded environments. Their omission from these runner registrations is not a claim that the features are absent.',
      '- Requirements without an association here remain for further review. Do not add a label solely to make every catalog case appear covered.','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    output=ROOT/'docs/LIVE-COVERAGE.md';content=render()
    if args.check:
        if not output.exists() or output.read_text()!=content:
            print('Live coverage inventory is stale; run scripts/build_live_coverage.py.',file=sys.stderr);return 1
    else:output.write_text(content)
    return 0

if __name__=='__main__':sys.exit(main())
