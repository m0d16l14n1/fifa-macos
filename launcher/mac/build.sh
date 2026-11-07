#!/bin/sh
# Builds the macOS launcher (SwiftUI, no Xcode project) as a plain executable; make_app.sh puts it into
# FIFA 19.app as the app's main program, with the game (fifa19) beside it.
#
#   sh launcher/mac/build.sh [output]      # default out/launcher-mac/fifa19-launcher
#
# On its own it finds the game through FIFA19_DIR (the folder with fifa19); FIFA19_LAUNCHER_PAGE=graphics opens
# a page and FIFA19_LAUNCHER_PLAY=1 presses Play (tests, screenshots).
set -e
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
out="${1:-$root/out/launcher-mac/fifa19-launcher}"
mkdir -p "$(dirname "$out")"
xcrun swiftc -O -swift-version 5 -target arm64-apple-macos14.0 -parse-as-library \
  -framework SwiftUI -framework AppKit -o "$out" "$here"/Sources/*.swift
echo "built $out"
