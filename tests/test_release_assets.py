"""Release assets must preserve complete skills and keep optional code separate."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_assets', ROOT / 'scripts/build_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseAssets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        for name, content in {'src/luda/__init__.py': '# runtime\n',
                              'skills/luda/SKILL.md': '# skill\n',
                              'skills/luda/references/text.md': '# text guidance\n',
                              '.codex-plugin/plugin.json': '{"name":"luda"}',
                              '.mcp.json': '{}',
                              'skills/unrelated/SKILL.md': '# not part of this plugin\n'}.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def wheel(self, *, omit=None, extra=None):
        path = self.root / 'package.whl'
        data = {'luda/__init__.py': '# runtime\n',
                'luda.data/data/share/luda/skills/luda/SKILL.md': '# skill\n',
                'luda.data/data/share/luda/skills/luda/references/text.md': '# text guidance\n'}
        if omit:
            data.pop(omit)
        if extra:
            data.update(extra)
        with zipfile.ZipFile(path, 'w') as archive:
            for name, content in data.items():
                archive.writestr(name, content)
        return path

    def test_complete_runtime_and_skill_verified(self):
        self.assertEqual(release.verify_wheel(self.source, self.wheel(), 'luda', 'luda'), 1)

    def test_missing_reference_fails(self):
        wheel = self.wheel(omit='luda.data/data/share/luda/skills/luda/references/text.md')
        with self.assertRaises(ValueError):
            release.verify_wheel(self.source, wheel, 'luda', 'luda')

    def test_unexpected_runtime_or_addon_code_fails(self):
        for extra in ({'luda/unexpected.py': '# stale'}, {'luda_editor_bridge/__init__.py': '# addon'},
                      {'share/luda/prosemirror.mjs': '// addon'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                release.verify_wheel(self.source, self.wheel(extra=extra), 'luda', 'luda')

    def test_missing_skill_source_is_not_silently_verified(self):
        (self.source / 'skills/luda/SKILL.md').unlink()
        with self.assertRaises(ValueError):
            release.verify_wheel(self.source, self.wheel(), 'luda', 'luda')

    def test_plugin_has_complete_skill_but_no_unrelated_skill(self):
        path = self.root / 'plugin.zip'
        release.plugin_zip(self.source, path, 'luda')
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read('luda/skills/luda/references/text.md'), b'# text guidance\n')
            self.assertFalse(any('unrelated' in name for name in archive.namelist()))
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))

    def test_plugin_directory_uses_manifest_name_independently_of_skill(self):
        (self.source / '.codex-plugin/plugin.json').write_text('{"name":"editor-bridge"}')
        path = self.root / 'addon.zip'
        release.plugin_zip(self.source, path, 'luda')
        with zipfile.ZipFile(path) as archive:
            self.assertIn('editor-bridge/skills/luda/SKILL.md', archive.namelist())

    def test_plugin_rejects_missing_entrypoint_and_symlink(self):
        path = self.source / 'skills/luda/references/text.md'
        path.unlink()
        path.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            release.plugin_zip(self.source, self.root / 'bad.zip', 'luda')
        path.unlink()
        (self.source / 'skills/luda/SKILL.md').unlink()
        with self.assertRaises(ValueError):
            release.plugin_zip(self.source, self.root / 'missing.zip', 'luda')
