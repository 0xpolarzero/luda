#!/bin/sh
set -eu
test "$(id -u)" != 0
export LUDA_ISOLATED_TEST_DISPLAY=1
export LUDA_PROBE_DIR="$(mktemp -d /tmp/luda-media-probe.XXXXXX)"
echo "Probe request/response directory: $LUDA_PROBE_DIR"
export LUDA_PROBE_BINARY="$PWD/.venv/bin/luda"
xfwm4 --compositor=off >"$LUDA_PROBE_DIR/wm.log" 2>&1 &
wm_pid=$!
/usr/bin/python3 tests/evidence/media-usability/fixture.py >"$LUDA_PROBE_DIR/fixture.log" 2>&1 &
fixture_pid=$!
trap 'kill "$fixture_pid" "$wm_pid" 2>/dev/null || true' EXIT
sleep 1
.venv/bin/python tests/evidence/media-usability/client.py
