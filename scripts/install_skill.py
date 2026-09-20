#!/usr/bin/env python3
"""Install Luda's skill for one agent and one explicit scope; never change MCP settings."""
import argparse
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCATIONS = {
    'codex': '.agents/skills', 'claude': '.claude/skills',
    'cursor': '.cursor/skills', 'gemini': '.gemini/skills',
    'opencode': '.config/opencode/skills',
}


def skill_files(source):
    if source.is_symlink() or not source.is_dir() or not (source / 'SKILL.md').is_file():
        raise ValueError('Source must be a real Luda skill directory containing SKILL.md.')
    files = {}
    for path in source.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('Skill trees must contain only regular files and directories.')
        if path.is_file():
            files[path.relative_to(source)] = path.read_bytes()
    return files


def install(agent, scope, source, *, home=None, project=None):
    if agent not in LOCATIONS or scope not in ('user', 'project'):
        raise ValueError('Choose a supported agent and user or project scope.')
    if scope == 'user' and project is not None:
        raise ValueError('--project applies only to project scope.')
    source = Path(source).absolute()
    expected = skill_files(source)
    base = Path(home) if home is not None else Path.home()
    if scope == 'project':
        base = Path(project or Path.cwd())
    location = LOCATIONS[agent]
    if agent == 'opencode':
        location = '.opencode/skills' if scope == 'project' else location
        if scope == 'user' and home is None and os.environ.get('XDG_CONFIG_HOME'):
            base = Path(os.environ['XDG_CONFIG_HOME'])
            if not base.is_absolute():
                raise ValueError('XDG_CONFIG_HOME must be absolute.')
            location = 'opencode/skills'
    destination = base.absolute() / location / 'luda'
    if destination.exists() or destination.is_symlink():
        if not destination.is_symlink() and skill_files(destination) == expected:
            return destination, False
        raise FileExistsError(f'{destination} already exists with different content; back it up or move it before installing.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.luda-skill-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'luda'
        shutil.copytree(source, staged)
        # Exclusive creation also refuses a destination created during staging.
        destination.mkdir()
        try:
            shutil.copytree(staged, destination, dirs_exist_ok=True)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return destination, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=LOCATIONS, required=True)
    parser.add_argument('--scope', choices=('user', 'project'), required=True)
    parser.add_argument('--project', type=Path, help='Project directory; defaults to the working directory')
    parser.add_argument('--source', type=Path, default=ROOT / 'skills/luda', help='Complete skill directory to copy')
    args = parser.parse_args()
    try:
        path, created = install(args.agent, args.scope, args.source, project=args.project)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')
    print(f'{"Installed" if created else "Already installed"}: {path}')
    print('Restart the agent to discover the skill. Register the Luda MCP server separately; see docs/AGENT-INTEGRATIONS.md.')


if __name__ == '__main__':
    main()
