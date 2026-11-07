#!/bin/sh
# Makes FIFA 19.app from the build (scripts/make_mac.sh first): a double-click opens the launcher, whose Play
# starts the game. The app holds copies of the game's program, its guest DLL libraries, the ReXGlue runtime and
# the GPU plugin, so it keeps working while the build folder is rebuilt; run this again after a build.
# Settings and saves: ~/Library/Application Support/FIFA 19; log: ~/Library/Logs/FIFA 19/fifa19.log.
#
#   sh launcher/mac/make_app.sh [--config RelWithDebInfo|Release|Debug] [where]   # default out/FIFA 19.app
set -e
root="$(cd "$(dirname "$0")/../.." && pwd)"
config=RelWithDebInfo
if [ "$1" = "--config" ]; then config=$2; shift 2; fi
build="$root/out/build/mac-arm64-$(echo "$config" | tr '[:upper:]' '[:lower:]')"
app="${1:-$root/out/FIFA 19.app}"
sdk_lib="$root/third_party/rexglue-sdk/out/install/mac-arm64/lib"

[ -x "$build/fifa19" ] || { echo "error: $build/fifa19 not found; build it first (bash scripts/make_mac.sh)" >&2; exit 1; }

macos="$app/Contents/MacOS" resources="$app/Contents/Resources"
mkdir -p "$macos" "$resources"
cp -f "$build/fifa19" "$macos/fifa19"
cp -fL "$build"/lib*.dylib "$macos/"            # the runtime and the guest DLLs' libraries
for lib in "$sdk_lib"/librexgpu-*.dylib; do [ -e "$lib" ] && cp -fL "$lib" "$macos/"; done
# The Vulkan loader and MoltenVK, for --fifa19_gpu_backend=vulkan (the build keeps them in vulkan/).
[ -d "$build/vulkan" ] && rm -rf "$macos/vulkan" && cp -RL "$build/vulkan" "$macos/vulkan"
cp -f "$root/scripts/extract_god.py" "$resources/extract_god.py"
sh "$root/launcher/mac/build.sh" "$macos/FIFA 19 Launcher"

version=$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo dev)
cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>FIFA 19</string>
  <key>CFBundleDisplayName</key><string>FIFA 19</string>
  <key>CFBundleIdentifier</key><string>local.fifa19-macos</string>
  <key>CFBundleExecutable</key><string>FIFA 19 Launcher</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$version</string>
  <key>CFBundleVersion</key><string>$version</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.sports-games</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>GCSupportsControllerUserInteraction</key><true/>
  <key>GCSupportsGameMode</key><true/>
  <key>LSSupportsGameMode</key><true/>
</dict>
</plist>
PLIST
# Built here and never quarantined: the bundle stays unsigned; each program keeps the linker's ad-hoc signature.
touch "$app"
echo "made $app ($version)"
