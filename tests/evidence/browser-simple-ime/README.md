# Browser fixture: deterministic GTK simple preedit

Hosted run [35499067717](https://github.com/0xpolarzero/luda/actions/runs/35499067717)
(source `a44b652`) failed both HTML and rich-editor native composition cases.
The HTML oracle retained only Control/Shift keydown at the attempted preedit,
with `composition.active=false`; the rich case did not get the expected
`IME_COMPOSITION_ACTIVE` refusal. These are retained failures, not passes.
The preceding [90bc8ec run](https://github.com/0xpolarzero/luda/actions/runs/35497435435)
passed. The newer apt log records installation of IBus 1.5.29-2 and GTK modules
through the expanded desktop dependency set.

The fixture used `GTK_IM_MODULE=simple`. A private GTK3 module-cache probe
established that this value falls back: without IBus the actual context is
`gtk-im-context-simple`; with the official IBus GTK module available it is
`ibus`. The canonical `GTK_IM_MODULE=gtk-im-context-simple` selects the intended
built-in context in both environments. GTK documents native Ctrl-Shift-U
hexadecimal entry for [GtkIMContextSimple](https://gnome.pages.gitlab.gnome.org/gtk/gtk3/class.IMContextSimple.html);
the canonical ID is defined in [GTK's module implementation](https://chromium.googlesource.com/external/github.com/GNOME/gtk/+/refs/heads/upstream/fix-build-with-glib/gtk/gtkimmodule.c).

The corrected fixtures use that canonical ID, retain actual public MCP native
key injection and trusted DOM composition events, and retain the refusal and
independent state checks. Rich-editor qualification now explicitly proves the
preedit precondition before testing refusal. No production input setting or
IME behavior changes. This qualifies one deliberate GTK-simple fixture path,
not generic IBus support or hosted success before CI runs again.

## Reproduce without installing modules into the desktop

On Ubuntu 24.04 with the ordinary private-desktop test dependencies and the
browser extra already provisioned, create a disposable directory outside the
checkout. Download/extract official distribution packages (no postinst/service
or user-setting changes):

```sh
mkdir ime-probe
cd ime-probe
apt-get download ibus-gtk3 libibus-1.0-5
for package in *.deb; do dpkg-deb -x "$package" extracted; done
triplet=$(dpkg-architecture -qDEB_HOST_MULTIARCH)
probe=$PWD
export LD_LIBRARY_PATH="$probe/extracted/usr/lib/$triplet"
/usr/lib/"$triplet"/libgtk-3-0t64/gtk-query-immodules-3.0 \
  "$probe/extracted/usr/lib/$triplet/gtk-3.0/3.0.0/immodules/im-ibus.so" > immodules.cache
export GTK_IM_MODULE_FILE="$probe/immodules.cache"
for value in simple gtk-im-context-simple; do
  GTK_IM_MODULE="$value" xvfb-run -a /usr/bin/python3 -c \
    'import gi,os;gi.require_version("Gtk","3.0");from gi.repository import Gtk;Gtk.init([]);c=Gtk.IMMulticontext();c.focus_in();print(os.environ["GTK_IM_MODULE"],c.get_context_id())'
done
```

Run the matrix as an **ordinary UID**, retaining these two environment variables,
from the checkout with its own browser-enabled virtual environment:

```sh
.venv/bin/python scripts/qualification_matrix.py \
  --suites owned-browser owned-rich owned-rich-clipboard \
  --executable /absolute/separately-provisioned/chrome
```

The matrix creates isolated Xvfb/XFWM/D-Bus/XDG state. Its removal of ambient
`GTK_IM_MODULE` is deliberate: each fixture sets the canonical value itself.
The private `GTK_IM_MODULE_FILE` and `LD_LIBRARY_PATH` remain available to prove
that installed IBus does not change the selected fixture path. The extracted
packages and Chromium are test dependencies, not shipped runtime artifacts.

`result.json` preserves the failing precondition and exact source/environment
identities plus the before/after outcomes. Original matrix run directories and
hosted artifacts remain separately retained; only the relevant synthetic test
payload and compact evidence are copied here. The local experiment is ARM64;
the original hosted failure was AMD64. There are no synthetic composition
messages, extra retry attempts within a suite, or weakened expected results.
