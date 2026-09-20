"""Content identities for the running tool declarations and bundled skill."""
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


def bundled_skill_identity(dist):
    scope = 'Server installation artifact; does not identify the skill loaded by an agent.'
    try:
        direct = json.loads(dist.read_text('direct_url.json') or '{}')
        location = urlsplit(direct.get('url', ''))
        if direct.get('dir_info', {}).get('editable') and location.scheme == 'file' and location.netloc in ('', 'localhost'):
            path = Path(unquote(location.path)) / 'skills/luda/SKILL.md'
        else:
            matches = [p for p in (dist.files or []) if str(p).endswith('share/luda/skills/luda/SKILL.md')]
            if len(matches) != 1:
                return {'status': 'unavailable', 'reason': 'artifact_not_located', 'scope': scope}
            path = Path(dist.locate_file(matches[0]))
        with path.open('rb') as stream:
            content = stream.read(262145)
        if len(content) > 262144:
            return {'status': 'unavailable', 'reason': 'artifact_size_limit', 'scope': scope}
        return {'status': 'identified', 'sha256': hashlib.sha256(content).hexdigest(), 'scope': scope}
    except (OSError, ValueError, TypeError, AttributeError):
        return {'status': 'unavailable', 'reason': 'artifact_unreadable', 'scope': scope}


def version_identity(tool_definitions):
    """Hash the complete discovery declarations, independent of their ordering."""
    declarations = sorted(tool_definitions, key=lambda tool: tool['name'])
    canonical = json.dumps(declarations, sort_keys=True, ensure_ascii=False,
                           separators=(',', ':'), allow_nan=False).encode('utf-8')
    dist = distribution('luda')
    return {'identity_format': 1, 'driver_version': dist.version,
            'tool_schema': {'sha256': hashlib.sha256(canonical).hexdigest(),
                            'algorithm': 'sha256-canonical-tools-list-v1',
                            'scope': 'Complete tools/list declarations, including descriptions and annotations.'},
            'bundled_skill': bundled_skill_identity(dist)}
