#!/usr/bin/env bash
# Check that every ELF file in an AppDir resolves its libraries either inside
# the AppDir or from the short list of libraries every desktop Linux has
# (the AppImage excludelist plus the desktop stack: X11/xcb, Wayland, GL,
# fontconfig, glib, dbus). Run on the build host after pruning, with the
# packages in apt-packages.txt installed so the host side resolves.
#
#   packaging/appimage/check-bundle.sh path/to/Dogear.AppDir

set -euo pipefail
appdir="$(readlink -f "$1")"

# Host libraries the AppImage may use. Anything else must be bundled.
allowed='^(ld-linux-x86-64|linux-vdso|libc|libm|libdl|libpthread|librt|libutil|libresolv|libstdc\+\+|libgcc_s|libz|libzstd|liblzma|libbz2|libcrypt|libffi|libuuid|libexpat|libGL|libGLX|libGLdispatch|libEGL|libOpenGL|libgbm|libdrm|libX11|libX11-xcb|libXau|libXdmcp|libXext|libXrender|libXi|libxcb|libxcb-[a-z0-9]+|libwayland-(client|cursor|egl)|libfontconfig|libfreetype|libpng16|libbrotli(common|dec)|libharfbuzz|libgraphite2|libglib-2\.0|libgthread-2\.0|libgobject-2\.0|libgio-2\.0|libgmodule-2\.0|libpcre2?-8|libdbus-1|libsystemd|libcap|libgcrypt|libgpg-error|liblz4|libmount|libblkid|libselinux|libsqlite3|libssl|libcrypto|libtinfo|libncursesw|libreadline|libpanelw)\.so'

# Plugins that only load when the host has the matching desktop libraries:
# the GTK platform theme (native GTK file dialogs).
optional='/plugins/platformthemes/libqgtk3\.so$'

status=0
bundled_libs=0
host_libs=()
while IFS= read -r -d '' file; do
    head -c4 "$file" 2>/dev/null | grep -q $'\x7fELF' || continue
    bundled_libs=$((bundled_libs + 1))
    [[ "$file" =~ $optional ]] && continue
    out="$(ldd "$file" 2>&1)" || continue  # static or not a dynamic object
    # Only the file's own NEEDED entries count: what host libraries need in
    # turn is the host's business (a missing one still shows as not found).
    needed="$(readelf -d "$file" 2>/dev/null | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p')"
    while read -r line; do
        case "$line" in
            *"not found"*)
                echo "UNRESOLVED ${file#$appdir/}: ${line%% =>*}"
                status=1
                ;;
            *" => /"*)
                name="${line%% =>*}"
                grep -qxF "$name" <<< "$needed" || continue
                path="${line#*=> }"; path="${path%% (*}"
                [[ "$path" == "$appdir"/* ]] && continue
                if [[ ! "$name" =~ $allowed ]]; then
                    echo "HOST LIB NOT ALLOWED ${file#$appdir/}: $name ($path)"
                    status=1
                fi
                host_libs+=("$name")
                ;;
        esac
    done <<< "$out"
done < <(find "$appdir" -type f \( -name '*.so' -o -name '*.so.*' -o -perm -u+x \) -print0)

echo "check-bundle: $bundled_libs ELF files; host libraries used:"
printf '%s\n' "${host_libs[@]}" | sort -u | tr '\n' ' '
echo
[[ $status == 0 ]] && echo "check-bundle: OK" || echo "check-bundle: FAILED"
exit $status
