#!/usr/bin/env bash
# Build dist/dogear-<version>-x86_64.AppImage (+ .zsync and .sha256).
#
# Runs on Ubuntu 22.04 (CI, or tools/build-appimage.sh in Docker), as root or
# a user with the packages in apt-packages.txt installed. Builds the working
# tree. Every download is pinned and checked against its SHA-256.
#
#   packaging/appimage/build.sh
#
# Environment:
#   DOGEAR_APPIMAGE_CACHE   where downloads are kept (default build/appimage/cache)

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
pkg="$root/packaging"
work="$root/build/appimage"
cache="${DOGEAR_APPIMAGE_CACHE:-$work/cache}"
dist="$root/dist"
appdir="$work/Dogear.AppDir"

version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$root/src/dogear/__init__.py")"
[[ -n "$version" ]] || { echo "Could not read __version__ from src/dogear/__init__.py" >&2; exit 1; }
pyproject_version="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$root/pyproject.toml")"
[[ "$version" == "$pyproject_version" ]] || {
    echo "Version mismatch: __init__.py says $version, pyproject.toml says $pyproject_version" >&2; exit 1; }

# -- pinned tools ------------------------------------------------------------
# python-appimage publishes each minor version under a rolling tag; the file
# name pins the patch release and the hash pins the exact build.
PYTHON_URL="https://github.com/niess/python-appimage/releases/download/python3.12/python3.12.15-cp312-cp312-manylinux_2_28_x86_64.AppImage"
PYTHON_SHA256="929ce69b45955bfc74af81fd65a65c3ad240593c99b3574466a94ebf0f987ebf"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
# appimagetool would otherwise fetch the latest "continuous" runtime.
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64"
RUNTIME_SHA256="2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"

UPDATE_INFO="gh-releases-zsync|ninepointlabs|dogear|latest|dogear-*x86_64.AppImage.zsync"

fetch() {  # fetch URL SHA256 -> prints the cached path
    local url="$1" sha="$2" file="$cache/${1##*/}"
    mkdir -p "$cache"
    if [[ ! -f "$file" ]] || ! echo "$sha  $file" | sha256sum -c --quiet - 2>/dev/null; then
        curl -fsSL --retry 3 -o "$file.part" "$url"
        echo "$sha  $file.part" | sha256sum -c --quiet - || { echo "Checksum mismatch: $url" >&2; exit 1; }
        mv "$file.part" "$file"
    fi
    chmod +x "$file"
    echo "$file"
}

python_appimage="$(fetch "$PYTHON_URL" "$PYTHON_SHA256")"
appimagetool="$(fetch "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA256")"
runtime="$(fetch "$RUNTIME_URL" "$RUNTIME_SHA256")"

# -- Python ------------------------------------------------------------------
rm -rf "$appdir" "$work/python"
mkdir -p "$work/python" "$appdir"
(cd "$work/python" && "$python_appimage" --appimage-extract >/dev/null)
# Keep the relocatable interpreter and the libraries its extension modules
# load through RUNPATH (OpenSSL for hashlib, libffi, sqlite...). Its AppRun,
# desktop file, icon and Tcl/Tk are for running Python itself.
mkdir -p "$appdir/usr"
mv "$work/python/squashfs-root/opt" "$appdir/opt"
mv "$work/python/squashfs-root/usr/lib" "$appdir/usr/lib"
rm -f "$appdir"/usr/lib/{libtcl,libtk,libXft,libXrender}*.so*
rm -rf "$work/python" "$appdir/opt/_internal"

pyhome="$appdir/opt/python3.12"
python="$pyhome/bin/python3.12"
site="$pyhome/lib/python3.12/site-packages"

"$python" -I -m pip install --quiet --disable-pip-version-check --root-user-action=ignore \
    --no-deps --require-hashes --only-binary=:all: -r "$pkg/appimage/requirements.txt"

# Dogear itself: pure Python, QML and assets, the same files the wheel holds.
mkdir -p "$site/dogear"
cp -a "$root/src/dogear/." "$site/dogear/"
find "$site/dogear" -name __pycache__ -prune -exec rm -rf {} +

# -- prune -------------------------------------------------------------------
# Dogear uses QtCore, QtGui, QtQml, QtQuick (+ Controls Basic, Templates,
# Layouts, Shapes, Dialogs, Window) and QtPdf/QtQuick.Pdf. Everything else
# in PySide6-Essentials goes. check-bundle.sh then proves every library that
# stays still resolves.
ps="$site/PySide6"
qt="$ps/Qt"

# Tools, headers, stubs, build metadata.
rm -rf "$ps"/{include,typesystems,glue,scripts,doc} "$qt"/{libexec,metatypes,translations}
rm -f "$ps"/{assistant,designer,linguist,lrelease,lupdate,qmlformat,qmllint,qmlls,uic,rcc,balsam,balsamui}
find "$ps" -name '*.pyi' -delete
rm -rf "$site/shiboken6/include"
rm -f "$ps/svgtoqml"

# Python bindings Dogear never imports (QtQml and QtQuick need QtNetwork's and
# QtOpenGL's). QtTest and QtWidgets stay until Dogear's own test suite has run
# against this bundle (below).
for mod in QtConcurrent QtDBus QtDesigner QtHelp QtOpenGLWidgets \
           QtPdfWidgets QtPrintSupport QtSql QtSvg QtSvgWidgets QtUiTools QtXml \
           QtNetworkAuth QtStateMachine QtSerialPort QtLabsStyleKit QtQuickTest QtQuickWidgets; do
    rm -f "$ps/$mod.abi3.so"
done

# Qt libraries for modules nothing here loads.
for lib in Designer DesignerComponents Help UiTools Sql PrintSupport PdfWidgets \
           WaylandCompositor 'WaylandCompositor*' 'QuickControls2Material*' \
           'QuickControls2Universal*' 'QuickControls2Fusion*' 'QuickControls2Imagine*' \
           'QuickControls2FluentWinUI3*' 'LabsStyleKit*' Lottie 'QuickParticles' \
           QmlCompiler 'QmlLS*' 'QmlDom*' 'QmlToolingSettings' 'QuickTest' 'QuickEffects' \
           'LabsAnimation' 'LabsFolderListModel' 'LabsQmlModels' 'LabsSettings' \
           'LabsSharedImage' 'LabsWavefrontMesh' 'LabsPlatform' 'QuickTimeline*' \
           'QuickVectorImage*' 'SvgWidgets' 'OpenGLWidgets' 'Concurrent' 'Xml' \
           'EglFSDeviceIntegration' 'EglFsKmsSupport' 'EglFsKmsGbmSupport' 'LabsSynchronizer' \
           'Lottie*' 'QmlDesignSupport' 'QmlLocalStorage' 'QmlXmlListModel' 'QuickControls2Native' \
           'QuickShapesDesignHelpers' 'QuickWidgets' 'WaylandEglCompositorHwIntegration' \
           'WlShellIntegration' 'VirtualKeyboard*' 'StateMachine*'; do
    rm -f "$qt"/lib/libQt6$lib.so*
done

# QML modules.
rm -rf "$qt"/qml/{QtTest,QtWayland,QtNetwork,Qt}
rm -rf "$qt"/qml/QtQml/{DesignSupport,StateMachine,XmlListModel}
rm -rf "$qt"/qml/QtQuick/Shapes/DesignHelpers
rm -rf "$qt"/qml/QtQuick/{Particles,Effects,Timeline,VectorImage,Scene2D,Scene3D,NativeStyle,LocalStorage,Test,VirtualKeyboard,tooling}
rm -rf "$qt"/qml/QtQuick/Controls/{Material,Universal,Fusion,Imagine,FluentWinUI3,StyleKit,Native,designer,iOS,macOS,Windows}

# Plugins: keep platforms (xcb, wayland, offscreen, minimal), Wayland client
# integrations, xcb GL integration, platform themes (portal, GTK file dialogs),
# input contexts (compose, ibus), image formats and the SVG icon engine.
rm -rf "$qt"/plugins/{designer,egldeviceintegrations,generic,networkinformation,printsupport,qmltooling,qmlls,sqldrivers,tls,wayland-graphics-integration-server,vectorimageformats}
rm -f "$qt"/plugins/platforms/{libqeglfs.so,libqlinuxfb.so,libqvnc.so,libqvkkhrdisplay.so,libqminimalegl.so}
rm -f "$qt"/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so
rm -f "$qt"/plugins/wayland-graphics-integration-client/lib*-server.so
rm -f "$qt"/plugins/wayland-shell-integration/{libfullscreen-shell-v1.so,libivi-shell.so,libqt-shell.so,libwl-shell-plugin.so}
# libqpdf.so stays: QtQuick.Pdf renders pages through it.
rm -f "$qt"/plugins/imageformats/{libqicns.so,libqtga.so,libqtiff.so,libqwbmp.so}

# Interpreter parts a GUI app has no use for.
rm -rf "$pyhome"/lib/python3.12/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3}
rm -f "$pyhome"/lib/python3.12/lib-dynload/_tkinter*.so
rm -rf "$site"/{pip,build,packaging,pyproject_hooks,certifi}{,-*.dist-info}
rm -f "$pyhome"/bin/pip*

# -- host libraries ----------------------------------------------------------
# Qt's xcb platform plugin needs the xcb-util family, which minimal installs
# (and some desktops on Wayland) don't have, and QtNetwork (which QtQml
# links) needs Kerberos' GSSAPI, missing on e.g. a minimal Debian 12. They
# are small and ABI-stable, so bundle Ubuntu 22.04's next to Qt's own
# libraries, where RUNPATH finds them. libxcb itself, X11, GL/EGL,
# fontconfig, freetype, dbus, glib and Wayland come from the host, as the
# AppImage excludelist says.
for lib in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 libxcb-keysyms.so.1 \
           libxcb-render-util.so.0 libxcb-util.so.1 libxkbcommon.so.0 libxkbcommon-x11.so.0 \
           libgssapi_krb5.so.2 libkrb5.so.3 libk5crypto.so.3 libkrb5support.so.0 libcom_err.so.2 \
           libkeyutils.so.1; do
    src="$(ldconfig -p | awk -v l="$lib" '$1 == l && /x86-64/ {print $NF; exit}')"
    [[ -n "$src" ]] || { echo "Missing host library to bundle: $lib (see apt-packages.txt)" >&2; exit 1; }
    cp -L "$src" "$qt/lib/$lib"
    # They need each other (xcb-cursor needs xcb-render-util...): look here first.
    patchelf --set-rpath '$ORIGIN' "$qt/lib/$lib"
done

"$python" -I -m compileall -q -j0 "$site/dogear" >/dev/null

# -- Dogear's test suite, on the bundled Python and Qt -------------------------
# It imports the bundled copy of dogear (-I keeps the source tree off
# sys.path) and drives the real QML app offscreen, so a module pruned too
# far fails here. Then the test-only modules go.
log="$work/tests.log"
if ! (cd "$root" && QT_QPA_PLATFORM=offscreen "$python" -I -m unittest discover -s tests -t .) > "$log" 2>&1; then
    cat "$log"; echo "Dogear's tests failed on the bundled Python and Qt" >&2; exit 1
fi
tail -n 3 "$log"
rm -f "$ps"/{QtTest,QtWidgets}.abi3.so "$qt"/lib/libQt6{Test,Widgets}.so*

# -- desktop integration -----------------------------------------------------
mkdir -p "$appdir/usr/bin" "$appdir/usr/share/applications" "$appdir/usr/share/metainfo"
cat > "$appdir/usr/bin/dogear" <<'EOF'
#!/bin/sh
here="$(dirname -- "$(readlink -f -- "$0")")"
exec "$here/../../opt/python3.12/bin/python3.12" -I -m dogear "$@"
EOF
chmod 755 "$appdir/usr/bin/dogear"
install -m755 "$pkg/appimage/AppRun" "$appdir/AppRun"

desktop="$appdir/usr/share/applications/dogear.desktop"
{ cat "$pkg/dogear.desktop"; echo "X-AppImage-Version=$version"; } > "$desktop"
cp "$desktop" "$appdir/dogear.desktop"
install -m644 "$pkg/dogear.appdata.xml" "$appdir/usr/share/metainfo/dogear.appdata.xml"

for size in 16 24 32 48 64 128 256 512; do
    install -Dm644 "$pkg/icons/hicolor/${size}x${size}/apps/dogear.png" \
        "$appdir/usr/share/icons/hicolor/${size}x${size}/apps/dogear.png"
done
install -Dm644 "$pkg/icons/hicolor/scalable/apps/dogear.svg" \
    "$appdir/usr/share/icons/hicolor/scalable/apps/dogear.svg"
cp "$pkg/icons/hicolor/256x256/apps/dogear.png" "$appdir/dogear.png"
ln -sf usr/share/icons/hicolor/256x256/apps/dogear.png "$appdir/.DirIcon"

"$pkg/appimage/check-bundle.sh" "$appdir"

# -- AppImage ----------------------------------------------------------------
mkdir -p "$dist"
out="$dist/dogear-$version-x86_64.AppImage"
rm -f "$out" "$out.zsync" "$out.sha256"
(
    cd "$dist"
    ARCH=x86_64 VERSION="$version" "$appimagetool" --appimage-extract-and-run --no-appstream \
        --runtime-file "$runtime" -u "$UPDATE_INFO" --comp zstd "$appdir" "$out"
)
[[ -f "$out.zsync" ]] || { echo "appimagetool did not write $out.zsync" >&2; exit 1; }
(cd "$dist" && sha256sum "${out##*/}" > "${out##*/}.sha256")
ls -l "$out" "$out.zsync" "$out.sha256"
echo "AppImage size: $(du -h "$out" | cut -f1) ($(stat -c %s "$out") bytes)"
