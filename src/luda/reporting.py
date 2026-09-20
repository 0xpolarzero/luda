"""Content-free diagnostic projection; never serialize arbitrary provider records."""
from importlib.metadata import version, PackageNotFoundError
import math
import platform
import re
from .common import run

METHODS = frozenset('doctor list_windows window_overview recording observe ocr inspect workspaces wait_for wait_condition reconnect recover_input list_applications launch_application activate pointer pointer_popup hover drag_between key paste element type_text manage_window switch_workspace'.split())
# Deliberate fixed vocabulary; never infer safety from arbitrary uppercase text.
CODES = frozenset('RECORDING_BUSY RECORDING_LIMIT RECORDING_UNAVAILABLE RECORDING_FAILED OCR_UNAVAILABLE OCR_LANGUAGE_UNAVAILABLE OCR_INVALID_OUTPUT OCR_LIMIT ACCESSIBILITY_ERROR ACCESSIBILITY_UNAVAILABLE AMBIGUOUS_ACCESSIBILITY_WINDOW INVALID_SELECTION LAUNCH_FAILED NOT_PROTECTED_FIELD SELECTION_TOO_LARGE SELECTION_UNVERIFIABLE TARGET_IDENTITY_UNAVAILABLE UNSUPPORTED_OPERATION ACTION_REQUIRED ACTIVATION_FAILED ADMISSION_UNAVAILABLE BACKEND_ERROR BUSY CANCELLED CLIPBOARD_CHANGED CLIPBOARD_FAILED CLOSED CONTROL_PAUSED CONTROL_UNAVAILABLE DEPENDENCY_MISSING DESKTOP_CHANGED DISPLAY_UNAVAILABLE FOCUS_CHANGED FOCUS_UNVERIFIED INPUT_CLEANUP_PENDING INPUT_HELD INPUT_RELEASE_UNVERIFIED INPUT_STATE_CHANGED INPUT_UNAVAILABLE INTERNAL_ERROR INVALID_ARGUMENT INVALID_CARET INVALID_KEY INVALID_PROPERTY INVALID_WINDOW_TOKEN KEYBOARD_CLEANUP_PENDING KEYBOARD_UNAVAILABLE KEYMAP_CHANGED NOT_EDITABLE NOT_INTERACTABLE OCCLUDED_TARGET OUTPUT_LIMIT OUT_OF_BOUNDS PROTECTED_FIELD RESOURCE_UNAVAILABLE SCREENSHOT_LIMIT SCREENSHOT_UNAVAILABLE SELECTION_UNVERIFIED SESSION_BLOCKED SESSION_CHANGED STALE_OBSERVATION STALE_TARGET TEXT_CHANGED TEXT_MISMATCH TEXT_REPRESENTATION_UNSUPPORTED TEXT_TOO_LARGE TIMEOUT TOPOLOGY_UNAVAILABLE UNSAFE_RUNTIME UNSUPPORTED UNSUPPORTED_BACKEND UNSUPPORTED_ACTION UNSUPPORTED_INPUT_STATE UNSUPPORTED_KEYMAP UNSUPPORTED_PASTE UNSUPPORTED_SELECTION UNSUPPORTED_TEXT VERIFICATION_LIMIT'.split())
ELEMENT_ACTIONS = frozenset('read secret choose focus invoke select value check expand'.split())
EFFECTS = frozenset(('none', 'dispatched', 'verified', 'uncertain'))
PACKAGES = ('xdotool', 'wmctrl', 'scrot', 'xclip', 'x11-utils', 'at-spi2-core', 'libgtk-3-0t64', 'xfwm4')
DEPENDENCIES = ('xdotool', 'wmctrl', 'scrot', 'xclip', 'xprop')
VERSION = re.compile(r'[0-9]+(?:[.:+~_-]?[0-9]+|ubuntu|build|dfsg|repack|deb|rc|dev|a|b|post)*\Z')


def safe_version(value):
    return value if isinstance(value, str) and len(value) <= 64 and VERSION.fullmatch(value) else None


def empty_environment():
    return {'distribution': None, 'distribution_version': None,
              'architecture': None, 'python': None,
              'packages': {name: None for name in PACKAGES},
              'python_packages': {name: None for name in ('luda', 'mcp', 'Pillow')}}


def environment_summary():
    result = empty_environment()
    result['python'] = safe_version(platform.python_version())
    try:
        release = platform.freedesktop_os_release()
        if release.get('ID') in ('ubuntu', 'debian', 'fedora', 'arch', 'alpine', 'opensuse', 'rhel', 'rocky'):
            result['distribution'] = release['ID']
        value = release.get('VERSION_ID', '')
        if re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,3}', value):
            result['distribution_version'] = value
    except (OSError, ValueError):
        pass
    machine = platform.machine()
    if machine in ('aarch64', 'arm64', 'x86_64', 'i386', 'i686', 'armv7l', 'ppc64le', 's390x', 'riscv64'):
        result['architecture'] = machine
    for name in ('luda', 'mcp', 'Pillow'):
        try:
            result['python_packages'][name] = safe_version(version(name))
        except (PackageNotFoundError, ValueError):
            result['python_packages'][name] = None
    try:
        raw = run(['/usr/bin/dpkg-query', '-W', '-f=${Package}\t${Version}\n', *PACKAGES],
                  timeout=2, max_output_bytes=16384)
        for line in raw.decode('ascii', errors='replace').splitlines():
            fields = line.split('\t')
            if len(fields) == 2 and fields[0] in PACKAGES:
                result['packages'][fields[0]] = safe_version(fields[1])
    except Exception:
        # Missing package manager, deadline or malformed diagnostics add no raw text.
        pass
    return result


def project_health(value):
    value = value if isinstance(value, dict) else {}
    result = {key: value.get(key) if type(value.get(key)) is bool else None
              for key in ('ready', 'display_available', 'topology_available', 'accessibility_available', 'session_bus')}
    dependencies = value.get('dependencies')
    dependencies = dependencies if isinstance(dependencies, dict) else {}
    result['dependencies'] = {key: dependencies.get(key) if type(dependencies.get(key)) is bool else None for key in DEPENDENCIES}
    for name, fields in [('recording', ('available',)), ('ocr', ('available',)), ('keyboard', ('available',)), ('control', ('available', 'paused')), ('session_state', ('input_ready',))]:
        item = value.get(name)
        item = item if isinstance(item, dict) else {}
        result[name] = {key: item.get(key) if type(item.get(key)) is bool else None for key in fields}
    return result


def project_versions(health):
    value = health.get('versions') if isinstance(health, dict) else None
    value = value if isinstance(value, dict) else {}
    result = {'driver_version': safe_version(value.get('driver_version'))}
    for name in ('tool_schema', 'bundled_skill'):
        item = value.get(name)
        item = item if isinstance(item, dict) else {}
        digest = item.get('sha256')
        result[name] = {'sha256': digest if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) else None}
        if name == 'bundled_skill':
            status = item.get('status')
            result[name]['status'] = status if isinstance(status, str) and status in ('identified', 'unavailable') else None
    return result


def project_history(history):
    result = []
    for value in list(history)[-32:]:
        if not isinstance(value, dict):
            continue
        row = {}
        identifier = value.get('operation_id')
        if isinstance(identifier, str) and re.fullmatch(r'[0-9a-f]{32}', identifier):
            row['operation_id'] = identifier
        method = value.get('method')
        if isinstance(method, str) and method in METHODS:
            row['method'] = method
        effect = value.get('effect')
        if isinstance(effect, str) and effect in EFFECTS:
            row['effect'] = effect
        code = value.get('code')
        if isinstance(code, str) and code in CODES:
            row['code'] = code
        action = value.get('action')
        if method == 'element' and isinstance(action, str) and action in ELEMENT_ACTIONS:
            row['action'] = action
        elapsed = value.get('elapsed_ms')
        if type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 86400000:
            row['elapsed_ms'] = round(elapsed, 3)
        if type(value.get('ok')) is bool:
            row['ok'] = value['ok']
        if row:
            result.append(row)
    return result


def build_report(health, history, *, cli=False, recovering=False):
    try:
        environment = environment_summary()
    except Exception:
        # A diagnostic failure is not permission to serialize its exception.
        environment = empty_environment()
    return {'schema_version': 1, 'effect': 'none', 'environment': environment,
            'health': project_health(health), 'versions': project_versions(health), 'recovering': recovering is True,
            'history_scope': 'fresh_cli_process' if cli else 'current_mcp_process',
            'history_limit': 32, 'operations': project_history(history),
            'omitted': ['screenshots', 'window_titles', 'input_text', 'clipboard', 'paths',
                        'environment_variables', 'exception_messages', 'exception_details',
                        'action_arguments', 'reproduction_steps'],
            'limitations': ['No persistent history or earlier-process operations.',
                            'Health is a point-in-time probe; null means unavailable or omitted.',
                            'Supply synthetic reproduction steps separately; this report never retains them.',
                            'No files written, uploaded, deleted or actions replayed.']}
