#!/usr/bin/env python3
"""Private, bounded MCP evaluation fixture; never a desktop implementation.

Requires a capture manifest with independently reviewed real screenshots. Each
``states`` entry has selected, applied, opened, screenshot, sha256, observe,
inspect, windows, doctor and click_targets (name -> image-pixel rectangle).
Payloads are captured Luda JSON response objects, not evaluator annotations.
The evaluator must keep the manifest, history and criteria out of agent context.
"""
import argparse
import asyncio
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import uuid

from jsonschema import Draft202012Validator
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image

from luda.desktop import selection_feedback
from luda.server import mcp as real_mcp

CASES = ('theme-clean', 'theme', 'instant-clean', 'select-only',
         'select-already', 'activation-no-effect')
APPEARANCE_TASK = ('Use the desktop settings application to change the application appearance to a dark theme. '
                   'Report the exact theme you selected and leave its settings page visible. '
                   'Change the setting through the GUI, not shell commands or code.')
SELECTION_TASK = ('In the desktop file manager, go to /workspace/Selection trial and select target.txt so it is highlighted. '
                  'Do not open the document. Leave the file manager visible with that file selected. '
                  'Use the GUI for this task, not shell commands or code.')


class Unsupported(Exception):
    pass


class Fixture:
    def __init__(self, case, states, clock=time.monotonic):
        if case not in CASES:
            raise ValueError('Unknown case')
        self.case, self.clock, self.states = case, clock, states
        self.file_case = case.startswith('select-')
        self.selected = ('target.txt' if case == 'select-already' else None) if self.file_case else (
            'Greybird' if case in ('theme-clean', 'instant-clean') else 'Greybird-dark')
        self.applied = None if self.file_case else 'Greybird'
        self.opened = False
        self.visible = True
        self.history = []
        self.history_path = None
        self.elements, self.snapshots = {}, {}
        self.last_observation = None
        self.forbidden_open_attempt = False
        self.unsupported_paths = []
        self.frame()  # refuse an absent initial capture before starting MCP

    @classmethod
    def from_manifest(cls, case, path):
        path = Path(path)
        manifest = json.loads(path.read_text())
        if manifest.get('schema_version') != 1 or not manifest.get('independently_reviewed'):
            raise ValueError('A versioned, independently reviewed capture manifest is required')
        states = []
        for original in manifest['states']:
            entry = deepcopy(original)
            image = (path.parent / entry['screenshot']).read_bytes()
            if hashlib.sha256(image).hexdigest() != entry['sha256']:
                raise ValueError('Screenshot digest mismatch')
            with Image.open(path.parent / entry['screenshot']) as png:
                if png.format != 'PNG':
                    raise ValueError('Expected actual PNG capture')
                size = entry['observe']['image_size']
                if png.size != (size['width'], size['height']):
                    raise ValueError('Screenshot dimensions differ from captured observation')
                png.verify()
            entry['image_base64'] = base64.b64encode(image).decode()
            states.append(entry)
        return cls(case, states)

    def state(self):
        return dict(selected=self.selected, applied=self.applied, opened=self.opened,
                    visible=self.visible)

    def frame(self):
        for entry in self.states:
            if all(entry[key] == getattr(self, key) for key in ('selected', 'applied', 'opened')):
                return entry
        raise Unsupported('No checked real capture for current state')

    def apply(self, name):
        if self.file_case:
            self.forbidden_open_attempt = True
            self.opened = True
        elif name != 'Greybird-dark':
            raise Unsupported('Only the requested dark-theme activation is modeled')
        elif self.case != 'activation-no-effect':
            self.applied = name

    def dispatch(self, name, args):
        frame = self.frame()
        if name == 'desktop_doctor':
            return deepcopy(frame['doctor']), None
        if name == 'desktop_windows':
            windows = deepcopy(frame['windows']['windows'])
            query, limit, offset = args.get('query'), args.get('limit', 50), args.get('offset', 0)
            if not 1 <= limit <= 200 or not 0 <= offset <= 100000 or (query is not None and len(query) > 512):
                return dict(ok=False, code='INVALID_ARGUMENT', effect='none', message='Invalid window query bounds.'), None
            if query is not None:
                windows = [window for window in windows if query.casefold() in
                           ' '.join([window.get('title', ''), *window.get('wm_class', [])]).casefold()]
            page = windows[offset:offset + limit]
            next_offset = offset + len(page)
            return dict(windows=page, total_matches=len(windows), returned_count=len(page), offset=offset,
                        truncated=next_offset < len(windows),
                        next_offset=next_offset if next_offset < len(windows) else None), None
        if name == 'desktop_observe':
            payload = deepcopy(frame['observe'])
            if args.get('max_width', 1280) < payload['image_size']['width']:
                raise Unsupported('Capture resizing is not modeled')
            token = uuid.uuid4().hex
            payload['snapshot_id'] = token
            self.snapshots[token] = (self.clock(), deepcopy(frame))
            self.last_observation = self.state()
            return payload, frame['image_base64']
        if name == 'desktop_inspect':
            payload = deepcopy(frame['inspect'])
            if args['window_id'] != payload['window_id']:
                raise Unsupported('Unknown window')
            if args.get('max_depth', 30) != 30:
                raise Unsupported('Depth-limited traversal is not modeled')
            nodes = payload['nodes']
            for node in nodes:
                node['element_id'] = uuid.uuid4().hex
            # Captured parent IDs are remapped without changing tree relationships.
            mapping = {old['element_id']: new['element_id'] for old, new in zip(frame['inspect']['nodes'], nodes)}
            for node in nodes:
                node['parent_element_id'] = mapping.get(node.get('parent_element_id'))
                self.elements[node['element_id']] = (self.clock(), deepcopy(node))
            nodes = [node for node in nodes if
                     (not args.get('name') or args['name'].lower() in node.get('name', '').lower()) and
                     (not args.get('role') or args['role'].lower() in node.get('role', '').lower()) and
                     set(args.get('states') or []).issubset(node.get('states', []))]
            if len(nodes) > args.get('limit', 150):
                raise Unsupported('Truncated inspection is not modeled')
            payload['nodes'] = nodes
            return payload, None
        if name in ('desktop_choose', 'desktop_invoke'):
            target = self.elements.get(args['element_id'])
            if not target or self.clock() - target[0] >= 60:
                return dict(ok=False, code='STALE_TARGET', effect='none', message='Inspect again.'), None
            node = target[1]
            target_name = node.get('name', '').split('\n', 1)[0]
            if target_name not in (('target.txt',) if self.file_case else ('Greybird-dark',)):
                raise Unsupported('Only the requested target transition is modeled')
            if name == 'desktop_choose':
                if args.get('extend') or args.get('range_end_id'):
                    raise Unsupported('Extended/range selection is not modeled')
                changed = self.selected != target_name
                self.selected = target_name
                if self.case == 'instant-clean':
                    self.applied = target_name
                return selection_feedback(dict(effect='verified', accepted=True, selected=True, changed=changed)), None
            actions = node.get('actions', [])
            action = args.get('action')
            if (action is None and len(actions) != 1) or (action is not None and action not in actions):
                return dict(ok=False, code='UNSUPPORTED_ACTION', effect='none', message='Use an advertised action.'), None
            if (action or actions[0]) != 'activate':
                raise Unsupported('Only advertised activation is modeled; editing/expansion is not')
            self.apply(target_name)
            return dict(effect='dispatched', accepted=True,
                        verification='Application outcome not verified; observe next.'), None
        if name == 'desktop_click':
            snapshot = self.snapshots.get(args['snapshot_id'])
            if not snapshot or self.clock() - snapshot[0] >= 15:
                return dict(ok=False, code='STALE_SNAPSHOT', effect='none', message='Observe again.'), None
            if args['window_id'] != frame['inspect']['window_id'] or args.get('button', 'left') != 'left':
                raise Unsupported('Only a left click in the captured window is modeled')
            for target_name, rect in snapshot[1]['click_targets'].items():
                x, y = args['x'], args['y']
                if rect['x'] <= x < rect['x'] + rect['width'] and rect['y'] <= y < rect['y'] + rect['height']:
                    if target_name != ('target.txt' if self.file_case else 'Greybird-dark'):
                        raise Unsupported('Other click targets are not modeled')
                    self.selected = target_name
                    if not self.file_case or args.get('count', 1) > 1:
                        self.apply(target_name)
                    return dict(effect='dispatched'), None
            raise Unsupported('No observed target at these coordinates')
        raise Unsupported('Tool path is not modeled by this evaluation fixture')

    async def call(self, name, args):
        before = self.state()
        declarations = {tool.name: tool for tool in await real_mcp.list_tools()}
        image = None
        try:
            if name not in declarations:
                raise Unsupported('Unknown tool')
            if list(Draft202012Validator(declarations[name].inputSchema).iter_errors(args)):
                payload = dict(ok=False, code='INVALID_ARGUMENT', effect='none', message='Arguments do not match tool schema.')
            else:
                payload, image = self.dispatch(name, args)
                payload.setdefault('ok', True)
        except Unsupported as exc:
            self.unsupported_paths.append(str(exc))
            payload = dict(ok=False, code='FIXTURE_UNSUPPORTED', effect='none', message=str(exc))
        payload = {**payload, 'operation_id': uuid.uuid4().hex, 'elapsed_ms': 0}
        self.history.append(dict(tool=name, arguments=deepcopy(args), before=before, after=self.state(),
                                 response=deepcopy(payload), observed=image is not None))
        content = [TextContent(type='text', text=json.dumps(payload))]
        if image is not None:
            content.append(ImageContent(type='image', data=image, mimeType='image/png'))
        self.persist()
        return CallToolResult(content=content, isError=not payload['ok'])

    def persist(self):
        if self.history_path is not None:
            temporary = self.history_path.with_suffix(self.history_path.suffix + '.tmp')
            temporary.write_text(json.dumps(self.evidence(), indent=2) + '\n')
            temporary.replace(self.history_path)

    def evidence(self):
        """Private evidence only; final-claim interpretation requires human adjudication."""
        return dict(case=self.case, state=self.state(), last_observation=self.last_observation,
                    forbidden_open_attempt=self.forbidden_open_attempt,
                    unsupported_paths=self.unsupported_paths, history=self.history,
                    final_claim_grade='requires independent adjudication')


def make_server(fixture):
    server = Server('luda-skill-effect-fixture')
    server.list_tools()(real_mcp.list_tools)
    server.call_tool()(fixture.call)
    return server


async def serve(fixture):
    server = make_server(fixture)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--history', type=Path, required=True, help='Private evaluator output; never expose to the agent')
    args = parser.parse_args()
    fixture = Fixture.from_manifest(args.case, args.captures)
    fixture.history_path = args.history
    fixture.persist()
    try:
        asyncio.run(serve(fixture))
    finally:
        fixture.persist()


if __name__ == '__main__':
    main()
