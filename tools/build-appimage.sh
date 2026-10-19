#!/usr/bin/env bash
# Build the AppImage into dist/ in an Ubuntu 22.04 container, the same way CI
# does. Needs Docker; nothing is installed on this computer. Builds the
# working tree.
#
#   tools/build-appimage.sh [--test]
#
# --test   then run packaging/appimage/smoke.sh on it, in the same container.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test=0
case "${1:-}" in
    --test) test=1 ;;
    "") ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
esac

docker run --rm -v "$root:/src" -w /src -e OWNER="$(id -u):$(id -g)" -e TEST="$test" ubuntu:22.04 bash -euc '
    trap "chown -R \"\$OWNER\" build dist 2>/dev/null || true" EXIT
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null
    apt-get install -y -qq --no-install-recommends $(sed "s/#.*//" packaging/appimage/apt-packages.txt) >/dev/null
    packaging/appimage/build.sh
    if [[ "$TEST" == 1 ]]; then
        packaging/appimage/smoke.sh dist/dogear-*-x86_64.AppImage
    fi
'
