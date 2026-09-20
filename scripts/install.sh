#!/usr/bin/env bash
# Provision guest dependencies, then atomically select a versioned installation.
set -euo pipefail
prefix=${1:?Usage: install.sh /absolute/install/path [--skip-system]}
if [[ $# -gt 2 || ( $# -eq 2 && $2 != '--skip-system' ) ]]; then
  echo 'Usage: install.sh /absolute/install/path [--skip-system]' >&2
  exit 2
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Validate before apt or any installation mutation.
python3 -c 'import sys;sys.path.insert(0,sys.argv[1]);from manage_install import checked_prefix;checked_prefix(sys.argv[2])' "$source_dir/scripts" "$prefix"
if [[ "${2:-}" != '--skip-system' ]]; then
  if [[ $(id -u) != 0 ]]; then echo 'Provision dependencies as root, or use --skip-system after provisioning.' >&2; exit 2; fi
  apt-get update
  apt-get install -y python3 python3-venv python3-gi gir1.2-atspi-2.0 libx11-6 libxi6 libxtst6 xdotool wmctrl xclip scrot x11-utils
fi
exec python3 "$source_dir/scripts/manage_install.py" install --prefix "$prefix"
