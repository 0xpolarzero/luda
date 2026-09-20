#!/usr/bin/env bash
# Provision Linux dependencies, select a versioned runtime, and connect agents.
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: scripts/install.sh [OPTIONS]
       scripts/install.sh /absolute/prefix [OPTIONS]  (legacy runtime-only form)

Install Luda on the Linux machine whose desktop the agent will control.
Requires Python 3.12+. System dependencies use apt-get and require root.

  --prefix PATH          Dedicated absolute installation path (default /opt/luda)
  --user ACCOUNT         Account that runs the agent and desktop (required as root)
  --agent NAME           Connect an agent; repeat for multiple agents, or use auto
  --list-agents          Show supported agent identifiers without installing
  --scope user|project   Agent configuration scope (default user)
  --project PATH         Project directory for project-scoped configuration
  --export PATH          Export tools and skill for a custom agent
  --check-desktop        Check the running desktop after agent setup (not image builds)
  --yes                  Noninteractive setup; still requires explicit selection
  --runtime-only         Install runtime without configuring any agent (image builds)
  --skip-system          Skip apt; use only when dependencies are already installed
  --browser-config FILE  Existing managed Chromium configuration (optional)
  -h, --help             Show this help

Examples:
  sudo scripts/install.sh --user alice --agent codex --yes
  sudo scripts/install.sh --user alice --agent codex --agent claude-code --yes
  sudo scripts/install.sh --user alice --runtime-only --yes
  scripts/install.sh --prefix "$HOME/.local/share/luda" --skip-system --agent codex

With no agent selection, a terminal prompts you to choose agents. Automated
installation must specify --agent or --runtime-only. No desktop or credentials
are needed to bake the runtime, skill and tool configuration into an image.
HELP
}
fail() { echo "Luda installer: $*" >&2; exit 2; }
prefix=/opt/luda
legacy=false
prefix_set=false
skip_system=false
runtime_only=false
assume_yes=false
account=''
export_selected=false
optional=()
setup_options=()
agents=()
if [[ $# -gt 0 && "$1" != -* ]]; then
  prefix=$1; prefix_set=true; legacy=true; shift
fi
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --list-agents)
      source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
      PYTHONPATH="$source_dir/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m luda.setup --list-agents ;;
    --skip-system) skip_system=true; shift ;;
    --runtime-only) runtime_only=true; shift ;;
    --check-desktop) setup_options+=(--check-desktop); shift ;;
    --yes) assume_yes=true; setup_options+=(--yes); shift ;;
    --prefix|--user|--browser-config|--agent|--scope|--project|--export)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail "$1 requires a value"
      case "$1" in
        --prefix) [[ "$prefix_set" == false ]] || fail 'Specify the prefix only once'; prefix=$2; prefix_set=true ;;
        --user) [[ -z "$account" ]] || fail 'Specify --user only once'; account=$2 ;;
        --browser-config) optional+=("$1" "$2") ;;
        --export) export_selected=true; setup_options+=("$1" "$2") ;;
        --agent) agents+=("$1" "$2") ;;
        *) setup_options+=("$1" "$2") ;;
      esac
      shift 2 ;;
    *) fail "Unknown option: $1 (see --help)" ;;
  esac
done
[[ "$runtime_only" == false || ${#agents[@]} -eq 0 ]] || fail '--runtime-only cannot be combined with --agent'
if [[ "$legacy" == true && ${#agents[@]} -eq 0 && "$export_selected" == false ]]; then runtime_only=true; fi
if [[ "$runtime_only" == false && ${#agents[@]} -eq 0 && "$export_selected" == false ]] && { [[ ! -t 0 ]] || [[ "$assume_yes" == true ]]; }; then
  fail 'Choose --agent NAME (repeatable), --agent auto, or --runtime-only for noninteractive installation'
fi
command -v python3 >/dev/null || fail 'Python 3.12 or newer is required; install it first'
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' || fail 'Python 3.12 or newer is required; install it first'
if [[ -z "$account" ]]; then
  [[ $(id -u) != 0 ]] || fail 'Specify --user ACCOUNT explicitly when installing as root'
  account=$(id -un)
fi
optional+=(--user "$account")
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Validate all arguments and target account before apt or installation mutation.
python3 - "$source_dir/scripts" "$prefix" "${optional[@]}" <<'PYVALIDATE'
import argparse,sys,pwd
sys.path.insert(0,sys.argv[1])
from manage_install import checked_prefix, verify_browser, read_browser_config, check_install_access
p=argparse.ArgumentParser();p.add_argument('--browser-config');p.add_argument('--user',required=True)
a=p.parse_args(sys.argv[3:])
try:
    pwd.getpwnam(a.user)
    check_install_access(checked_prefix(sys.argv[2]),a.user)
    if a.browser_config: verify_browser(read_browser_config(a.browser_config),a.user)
except Exception as exc:
    p.exit(2, f'Luda installer: {exc}\n')
PYVALIDATE
if [[ "$runtime_only" == false ]]; then
  PYTHONPATH="$source_dir/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m luda.setup --validate-only --prefix "$prefix" --user "$account" "${agents[@]}" "${setup_options[@]}"
elif [[ ${#setup_options[@]} -gt 0 ]]; then
  # --yes is meaningful to automation, but scope/project without setup is a mistake.
  for option in "${setup_options[@]}"; do
    [[ "$option" == --yes ]] || fail 'Agent setup options cannot be combined with --runtime-only'
  done
fi
if [[ "$skip_system" != true ]]; then
  [[ $(id -u) == 0 ]] || fail 'Run with sudo --user ACCOUNT, or use --skip-system after provisioning dependencies'
  command -v apt-get >/dev/null || fail 'Automatic system dependencies require apt-get; provision them manually and use --skip-system'
  apt-get update
  apt-get install -y python3 python3-venv python3-gi gir1.2-atspi-2.0 gir1.2-pango-1.0 libx11-6 libxi6 libxtst6 libxrandr2 fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji xdotool wmctrl xclip scrot x11-utils
fi
python3 "$source_dir/scripts/manage_install.py" install --prefix "$prefix" "${optional[@]}"
if [[ "$runtime_only" == true ]]; then
  echo "Luda runtime installed at $prefix. No agents were configured."
  echo "Connect an agent with: $prefix/current/.venv/bin/luda setup --user $account --agent NAME"
else
  "$prefix/current/.venv/bin/python" -m luda.setup --prefix "$prefix" --user "$account" "${agents[@]}" "${setup_options[@]}"
fi
