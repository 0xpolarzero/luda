#!/usr/bin/env bash
# Provision guest dependencies, then atomically select a versioned installation.
set -euo pipefail
prefix=${1:?Usage: install.sh /absolute/install/path [--skip-system] [--browser-config FILE] [--user ACCOUNT]}
shift
skip_system=false
optional=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-system) skip_system=true; shift ;;
    --browser-config|--user) [[ $# -ge 2 ]] || exit 2; optional+=("$1" "$2"); shift 2 ;;
    *) echo 'Unknown installer option' >&2; exit 2 ;;
  esac
done
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Validate before apt or any installation mutation.
python3 - "$source_dir/scripts" "$prefix" "${optional[@]}" <<'PYVALIDATE'
import argparse,sys
sys.path.insert(0,sys.argv[1])
from manage_install import checked_prefix, read_browser_config, verify_browser, check_install_access
checked_prefix(sys.argv[2])
p=argparse.ArgumentParser();p.add_argument('--browser-config');p.add_argument('--user',default='silo-desktop')
a=p.parse_args(sys.argv[3:])
check_install_access(checked_prefix(sys.argv[2]),a.user)
if a.browser_config:verify_browser(read_browser_config(a.browser_config),a.user)
PYVALIDATE
if [[ "$skip_system" != true ]]; then
  if [[ $(id -u) != 0 ]]; then echo 'Provision dependencies as root, or use --skip-system after provisioning.' >&2; exit 2; fi
  apt-get update
  apt-get install -y python3 python3-venv python3-gi gir1.2-atspi-2.0 gir1.2-pango-1.0 libx11-6 libxi6 libxtst6 libxrandr2 fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji xdotool wmctrl xclip scrot x11-utils
fi
exec python3 "$source_dir/scripts/manage_install.py" install --prefix "$prefix" "${optional[@]}"
