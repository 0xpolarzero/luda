"""Exercise Gio desktop-entry filtering in fresh, isolated helper processes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from luda.apps import list_applications
from luda.common import environment_scope


class ApplicationVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = subprocess.run(
            ['/usr/bin/python3', '-c', 'from gi.repository import Gio'],
            capture_output=True, timeout=10,
        )
        if probe.returncode:
            raise unittest.SkipTest('System Python requires Gio for real desktop-entry visibility tests.')

    def test_selected_identity_controls_only_show_in_and_not_show_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            applications = root / 'data' / 'applications'
            applications.mkdir(parents=True)
            entries = {
                'always': '',
                'only': 'OnlyShowIn=ExampleDesktop;\n',
                'excluded': 'NotShowIn=ExampleDesktop;\n',
                'other': 'OnlyShowIn=OtherDesktop;\n',
                'hidden': 'NoDisplay=true\n',
            }
            for name, visibility in entries.items():
                (applications / f'luda-visibility-{name}.desktop').write_text(
                    '[Desktop Entry]\nType=Application\n'
                    f'Name=Luda visibility {name}\nExec=/bin/true\n{visibility}'
                )
            environment = {
                'PATH': '/usr/bin:/bin', 'HOME': str(root), 'LANG': 'C.UTF-8',
                'XDG_DATA_HOME': str(root / 'data'), 'XDG_DATA_DIRS': str(root / 'empty'),
                'XDG_CONFIG_HOME': str(root / 'config'),
            }
            for desktop, expected in (
                (None, {'always', 'excluded'}),
                ('ExampleDesktop', {'always', 'only'}),
                ('OtherDesktop', {'always', 'excluded', 'other'}),
                ('Secondary:ExampleDesktop', {'always', 'only'}),
            ):
                with self.subTest(desktop=desktop):
                    selected = dict(environment)
                    if desktop is not None:
                        selected['XDG_CURRENT_DESKTOP'] = desktop
                    # The production wrapper starts a new system-Python helper;
                    # no Gio cache or caller desktop identity can affect results.
                    with environment_scope(selected):
                        result = list_applications(query='luda-visibility-', limit=20)
                    self.assertEqual(
                        {item['application_id'] for item in result['applications']},
                        {f'luda-visibility-{name}.desktop' for name in expected},
                    )


if __name__ == '__main__':
    unittest.main()
