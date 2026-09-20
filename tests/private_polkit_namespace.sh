#!/bin/bash
set -eu
base=$1
root=$2
# This helper is unsafe outside its launcher-created namespaces: fail closed.
test "$$" -eq 1
test "$(readlink /proc/self/ns/mnt)" != "$LUDA_PARENT_MOUNT_NS"
test "$(readlink /proc/self/ns/net)" != "$LUDA_PARENT_NET_NS"
unset DBUS_SYSTEM_BUS_ADDRESS
mount --make-rprivate /
mount -t tmpfs -o size=128m,mode=755 tmpfs "$base/rw"
for tree in usr etc var; do
 mkdir -p "$base/rw/${tree}-upper" "$base/rw/${tree}-work"
 mount -t overlay overlay -o "lowerdir=/$tree,upperdir=$base/rw/${tree}-upper,workdir=$base/rw/${tree}-work" "/$tree"
done
mount -t tmpfs -o size=32m,mode=755 tmpfs /run
mkdir -p "$base/rw/payload" /run/dbus
for package in "$base"/packages/*.deb; do dpkg-deb -x "$package" "$base/rw/payload"; done
cp -a "$base/rw/payload/usr/." /usr/
# Match the pinned package postinst only inside the private tmpfs-backed overlay.
chmod 4755 /usr/bin/pkexec
if test -d "$base/rw/payload/etc"; then cp -a "$base/rw/payload/etc/." /etc/; fi
printf 'polkitd:x:65530:65530:Private polkit daemon:/var/lib/polkit-1:/usr/sbin/nologin\n' >> /etc/passwd
printf 'polkitd:x:65530:\n' >> /etc/group
mkdir -p /var/lib/polkit-1 /etc/polkit-1/rules.d
chown 65530:65530 /var/lib/polkit-1
cat >/run/dbus/private.conf <<'EOF'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN" "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><type>system</type><listen>unix:path=/run/dbus/system_bus_socket</listen><auth>EXTERNAL</auth><policy context="default"><allow user="*"/><allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>
EOF
dbus-daemon --nofork --config-file=/run/dbus/private.conf >"$base/dbus.log" 2>&1 &
bus=$!
trap 'kill "$bus" "${authority:-}" 2>/dev/null || true' EXIT
for n in $(seq 1 30); do test -S /run/dbus/system_bus_socket && break; sleep .1; done
/usr/lib/polkit-1/polkitd >"$base/authority.log" 2>&1 &
authority=$!
sleep 1
mkdir -p "$base/gui" "$base/gui/runtime" "$base/gui/config" "$base/gui/cache" "$base/gui/data"
chown -R 1001:1001 "$base/gui"
chmod 700 "$base/gui/runtime"
runuser -u silo-desktop -- env HOME="$base/gui" XDG_RUNTIME_DIR="$base/gui/runtime" XDG_CONFIG_HOME="$base/gui/config" xvfb-run -a dbus-run-session -- timeout 6 /usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1 >"$base/agent.log" 2>&1 || true
kill -0 "$authority"
runuser -u silo-desktop -- env LUDA_TEST_AUTHORITY_PID="$authority" HOME="$base/gui" XDG_RUNTIME_DIR="$base/gui/runtime" XDG_CONFIG_HOME="$base/gui/config" XDG_CACHE_HOME="$base/gui/cache" XDG_DATA_HOME="$base/gui/data" LANG=C.UTF-8 LC_ALL=C.UTF-8 NO_AT_BRIDGE=0 GTK_MODULES=gail:atk-bridge xvfb-run -a dbus-run-session -- "$root/.venv/bin/python" "$root/tests/live_private_polkit.py" "$base/gui"
printf 'private_authority_alive\n' 
