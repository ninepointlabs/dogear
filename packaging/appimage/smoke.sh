#!/usr/bin/env bash
# Check a built Dogear AppImage: desktop integration files, a real start
# under Xvfb (xcb) and offscreen, the X11 window class, a start without
# Omarchy or Hyprland, what child processes inherit, and the opt-in
# --install-desktop-entry / --remove-desktop-entry flags.
#
#   packaging/appimage/smoke.sh dist/dogear-<version>-x86_64.AppImage
#
# Runs on Ubuntu 22.04 with the packages in apt-packages.txt (no FUSE needed:
# everything uses --appimage-extract-and-run).

set -euo pipefail

appimage="$(readlink -f "$1")"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
failures=0

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; failures=$((failures + 1)); }
check() {  # check "description" command...
    local what="$1"; shift
    if "$@"; then pass "$what"; else fail "$what"; fi
}

# A clean, Omarchy-free home for every run.
fresh_home() {
    local home="$tmp/home-$1"
    mkdir -p "$home"
    echo "$home"
}

# Errors Qt or Python print when the bundle misses something.
bundle_errors() {
    grep -E "Traceback|ImportError|ModuleNotFoundError|Cannot load library|Could not load the Qt platform plugin|could not be loaded|is not installed|module .* not found|QML problem" "$1"
}

echo "== $appimage"

# -- files inside the AppImage ------------------------------------------------
(cd "$tmp" && "$appimage" --appimage-extract >/dev/null)
appdir="$tmp/squashfs-root"

check "desktop-file-validate packaging/dogear.desktop" desktop-file-validate "$root/packaging/dogear.desktop"
check "desktop-file-validate AppDir/dogear.desktop" desktop-file-validate "$appdir/dogear.desktop"
check "desktop-file-validate AppDir/usr/share/applications/dogear.desktop" \
    desktop-file-validate "$appdir/usr/share/applications/dogear.desktop"
check "StartupWMClass=dogear, MimeType=application/pdf, X-AppImage-Version" bash -c "
    grep -qx 'StartupWMClass=dogear' '$appdir/dogear.desktop' &&
    grep -qx 'MimeType=application/pdf;' '$appdir/dogear.desktop' &&
    grep -q '^X-AppImage-Version=' '$appdir/dogear.desktop'"
check "appstreamcli validate --no-net" appstreamcli validate --no-net "$appdir/usr/share/metainfo/dogear.appdata.xml"

for size in 16 24 32 48 64 128 256 512; do
    png="$appdir/usr/share/icons/hicolor/${size}x${size}/apps/dogear.png"
    check "icon ${size}x${size}" bash -c "file '$png' | grep -q 'PNG image data, $size x $size'"
done
check "icon scalable SVG" bash -c "file '$appdir/usr/share/icons/hicolor/scalable/apps/dogear.svg' | grep -q SVG"
check "root icon dogear.png (256x256)" bash -c "file '$appdir/dogear.png' | grep -q 'PNG image data, 256 x 256'"
check ".DirIcon resolves to a PNG" bash -c "file -L '$appdir/.DirIcon' | grep -q 'PNG image data'"
check "Qt xcb and wayland platform plugins bundled" bash -c "
    ls '$appdir'/opt/python3.12/lib/python3.12/site-packages/PySide6/Qt/plugins/platforms/libqxcb.so \
       '$appdir'/opt/python3.12/lib/python3.12/site-packages/PySide6/Qt/plugins/platforms/libqwayland.so >/dev/null"
check "AppRun exports no LD_LIBRARY_PATH/PYTHONHOME/QT_PLUGIN_PATH/QT_QPA_PLATFORM" bash -c "
    ! grep -Eq '^[^#]*export +(LD_LIBRARY_PATH|PYTHONHOME|PYTHONPATH|QT_PLUGIN_PATH|QML2_IMPORT_PATH|QT_QPA_PLATFORM)' \
        '$appdir/AppRun' '$appdir/usr/bin/dogear'"
info="$("$appimage" --appimage-updateinformation 2>/dev/null | tr -d '\0')"
check "update information embedded ($info)" test "$info" = "gh-releases-zsync|ninepointlabs|dogear|latest|dogear-*x86_64.AppImage.zsync"

# -- running it ---------------------------------------------------------------
pdf="$tmp/sample.pdf"
"$appdir/opt/python3.12/bin/python3.12" -I "$root/tools/make_sample_pdf.py" "$pdf" 3 >/dev/null

run() {  # run NAME [VAR=value...] -- app args; output in $tmp/NAME.log. SMOKE_X11=1: under Xvfb
    local name="$1"; shift
    local envs=()
    while [[ $# -gt 0 && "$1" != "--" ]]; do envs+=("$1"); shift; done
    shift
    local home wrap=()
    home="$(fresh_home "$name")"
    [[ "${SMOKE_X11:-0}" == 1 ]] && wrap=(xvfb-run -a -s "-screen 0 1280x800x24")
    env -i PATH="${SMOKE_PATH:-/usr/local/bin:/usr/bin:/bin}" HOME="$home" LANG=C.UTF-8 "${envs[@]}" \
        "${wrap[@]}" timeout 60 "$appimage" --appimage-extract-and-run "$@" > "$tmp/$name.log" 2>&1
}

launch_ok() {  # launch_ok NAME expected-platform
    local log="$tmp/$1.log"
    if grep -q "self-test: OK" "$log" && grep -q "platform=$2 " "$log" && ! bundle_errors "$log" >/dev/null; then
        sed -n 's/^self-test: platform/  platform/p' "$log"
        return 0
    fi
    sed 's/^/  | /' "$log"
    return 1
}

SMOKE_X11=1 run xvfb -- --self-test "$pdf" || true
check "xvfb-run (xcb): starts, renders a PDF, no QML/plugin errors" launch_ok xvfb xcb

run offscreen QT_QPA_PLATFORM=offscreen -- --self-test "$pdf" || true
check "QT_QPA_PLATFORM=offscreen: starts, opens a PDF, no QML/plugin errors" launch_ok offscreen offscreen

# Degrade: empty HOME (no Omarchy theme, no fontconfig, no Hyprland), and no
# hyprctl or omarchy-* anywhere on PATH.
check "no hyprctl/omarchy on PATH" bash -c "! command -v hyprctl && ! compgen -c omarchy- | grep -q ."
check "degrade: fallback theme, no traceback" bash -c "
    grep -q 'theme=fallback/' '$tmp/offscreen.log' && ! grep -q Traceback '$tmp/offscreen.log'"

# WM_CLASS under X11 must match StartupWMClass.
wm_class() {
    local home; home="$(fresh_home wmclass)"
    env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$home" LANG=C.UTF-8 DOGEAR_SELF_TEST_DELAY=8000 \
        xvfb-run -a -s '-screen 0 1280x800x24' bash -c '
            "$1" --appimage-extract-and-run --self-test >/dev/null 2>&1 &
            for _ in $(seq 40); do
                id="$(xdotool search --onlyvisible --name "Dogear" 2>/dev/null | head -1)"
                [ -n "$id" ] && { xprop -id "$id" WM_CLASS; break; }
                sleep 0.25
            done
            wait' _ "$appimage"
}
wmclass="$(wm_class)"
check "X11 WM_CLASS ($wmclass) has class \"dogear\" = StartupWMClass" bash -c "grep -q '\"dogear\", \"dogear\"' <<< '$wmclass'"
check "Wayland app_id (QGuiApplication.desktopFileName) = dogear" grep -q "app_id=dogear " "$tmp/offscreen.log"

# Child processes: fake xdg-open (Qt's openUrl, the About dialog's email
# button) and fc-match (theme font lookup) record what they inherit.
fake="$tmp/fakebin"
mkdir -p "$fake"
for tool in xdg-open fc-match; do
    printf '#!/bin/sh\nenv > "%s/env-%s"\n' "$tmp" "$tool" > "$fake/$tool"
    chmod +x "$fake/$tool"
done
# Under X11: the offscreen platform has no openUrl.
SMOKE_X11=1 SMOKE_PATH="$fake:/usr/local/bin:/usr/bin:/bin" run children \
    DOGEAR_SELF_TEST_URL="mailto:help@example.com" DOGEAR_SELF_TEST_DELAY=2500 -- --self-test || true
sleep 1
for tool in xdg-open fc-match; do
    if [[ -f "$tmp/env-$tool" ]]; then
        leaked="$(grep -E '^(APPIMAGE|APPDIR|ARGV0|OWD|DOGEAR_APPIMAGE|LD_LIBRARY_PATH|PYTHONHOME|PYTHONPATH|QT_PLUGIN_PATH|QML2_IMPORT_PATH)=' "$tmp/env-$tool" || true)"
        check "$tool gets a clean host environment${leaked:+ (leaked: $(echo $leaked))}" test -z "$leaked"
    else
        fail "$tool was not started (see $tmp/children.log)"
        sed 's/^/  | /' "$tmp/children.log"
    fi
done

# Opt-in desktop integration, in a throwaway XDG_DATA_HOME.
data="$tmp/xdg-data"
env -i PATH=/usr/bin:/bin HOME="$tmp" XDG_DATA_HOME="$data" \
    "$appimage" --appimage-extract-and-run --install-desktop-entry > "$tmp/install.log" 2>&1 || true
sed 's/^/  | /' "$tmp/install.log"
entry="$data/applications/dogear.desktop"
check "--install-desktop-entry: desktop file validates" desktop-file-validate "$entry"
check "--install-desktop-entry: Exec and TryExec point at \$APPIMAGE" bash -c "
    grep -qxF 'Exec=\"$appimage\" %f' '$entry' && grep -qxF 'TryExec=$appimage' '$entry'"
check "--install-desktop-entry: 8 PNG sizes + SVG installed" \
    test "$(find "$data/icons/hicolor" -name 'dogear.*' | wc -l)" -eq 9
env -i PATH=/usr/bin:/bin HOME="$tmp" XDG_DATA_HOME="$data" \
    "$appimage" --appimage-extract-and-run --install-desktop-entry > /dev/null 2>&1
check "--install-desktop-entry again: idempotent" test "$(find "$data" -type f -name 'dogear.*' | wc -l)" -eq 10
env -i PATH=/usr/bin:/bin HOME="$tmp" XDG_DATA_HOME="$data" \
    "$appimage" --appimage-extract-and-run --remove-desktop-entry > "$tmp/remove.log" 2>&1 || true
check "--remove-desktop-entry: everything removed" test "$(find "$data" -type f -name 'dogear.*' | wc -l)" -eq 0
check "--install-desktop-entry from an extracted copy: refused, nothing written" bash -c "
    ! env -i PATH=/usr/bin:/bin HOME='$tmp' XDG_DATA_HOME='$tmp/xdg2' '$appdir/AppRun' --install-desktop-entry 2>/dev/null &&
    test ! -e '$tmp/xdg2/applications/dogear.desktop'"

echo "AppImage size: $(du -h "$appimage" | cut -f1) ($(stat -c %s "$appimage") bytes)"
if [[ $failures -gt 0 ]]; then
    echo "smoke: $failures check(s) FAILED"
    exit 1
fi
echo "smoke: all checks passed"
