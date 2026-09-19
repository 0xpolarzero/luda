#!/usr/bin/env bash
# Explicit guest install; no edits to Codex configuration or running desktop.
set -euo pipefail
prefix=${1:?Usage: install.sh /absolute/install/path [--skip-system]}
case "$prefix" in /*) ;; *) echo 'Install path must be absolute.' >&2; exit 2;; esac
if [[ -e "$prefix/.venv" ]]; then
  echo 'An installation already exists. Use a new versioned directory; upgrades are not automated.' >&2
  exit 2
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ "${2:-}" != '--skip-system' ]]; then
  if [[ $(id -u) != 0 ]]; then echo 'Install system dependencies as root, or use --skip-system after provisioning them.' >&2; exit 2; fi
  apt-get update
  apt-get install -y python3 python3-venv python3-gi gir1.2-atspi-2.0 libx11-6 xdotool wmctrl xclip scrot x11-utils
fi
mkdir -p -- "$prefix"
python3 -m venv "$prefix/.venv"
"$prefix/.venv/bin/pip" install --require-hashes -r "$source_dir/requirements.lock"
"$prefix/.venv/bin/pip" install --no-deps "$source_dir"
mkdir -p -- "$prefix/skills"
cp -R -- "$source_dir/skills/silo-desktop" "$prefix/skills/"
echo "Installed into $prefix. Use silo-desktop-session to attach to the desktop."
echo 'Codex MCP/skill registration is explicit; see README.md.'
