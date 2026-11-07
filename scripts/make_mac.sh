#!/usr/bin/env bash
# One command from your own FIFA 19 (Xbox 360, Games on Demand) to the game built for macOS on Apple silicon.
#
#   bash scripts/make_mac.sh --god /path/to/454109F9/00007000/<package file>
#
# Steps (each skipped when its result is there, so the script continues after a failure or a change):
#   1 build tools   2 SDK (scripts/sdk.sh)   3 extract the game into game/   4 codegen   5 build   6 app bundle
#
#   --god PATH      the Games on Demand package's header file (its .data folder beside it). Not needed once
#                   game/ holds default.xex.
#   --config NAME   RelWithDebInfo (default), Release or Debug (the game; the SDK is RelWithDebInfo)
#   --jobs N        parallel compile jobs (default: all cores)
#   --no-app        skip the FIFA 19.app bundle (out/FIFA 19.app)
#
# Nothing of the game is in this repository; what this script makes from your copy is yours, not to share.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
sdk="$repo/third_party/rexglue-sdk"
god= config=RelWithDebInfo jobs=$(sysctl -n hw.ncpu) app=1
while [ $# -gt 0 ]; do
  case $1 in
    --god) god=$2; shift 2 ;;
    --config) config=$2; shift 2 ;;
    --jobs) jobs=$2; shift 2 ;;
    --no-app) app=; shift ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
case $config in Debug|RelWithDebInfo|Release) ;; *) echo "--config: Debug, RelWithDebInfo or Release" >&2; exit 2 ;; esac
preset="mac-arm64-$(echo "$config" | tr '[:upper:]' '[:lower:]')"

step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nFAILED: %s\n' "$*" >&2; exit 1; }
logs="$repo/out/logs"; mkdir -p "$logs"
logged() {
  local name=$1; shift
  if ! "$@" > "$logs/$name.log" 2>&1; then
    tail -25 "$logs/$name.log" >&2
    fail "$name (full log: $logs/$name.log)"
  fi
}

[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || fail "this script is for macOS on Apple silicon"

step "1/6 build tools"
xcode-select -p > /dev/null 2>&1 || fail "no Xcode command line tools: run 'xcode-select --install'"
for tool in cmake ninja git python3; do command -v "$tool" > /dev/null || fail "missing $tool (brew install $tool)"; done
clang_major=$(clang --version | sed -n 's/.*clang version \([0-9]*\).*/\1/p' | head -1)
[ "${clang_major:-0}" -ge 18 ] || fail "the SDK needs Clang 18 or newer (Xcode 16 or newer); found ${clang_major:-none}"
free_gb=$(df -g "$repo" | awk 'NR==2 {print $4}')
[ "$free_gb" -ge 15 ] || echo "warning: ${free_gb} GB free; the game (6.6 GB), the SDK and the build need about 15 GB"

step "2/6 ReXGlue SDK"
bash "$repo/scripts/sdk.sh" --jobs "$jobs"
tool="$sdk/out/install/mac-arm64/bin/rexgluerd"
[ -x "$tool" ] || fail "the codegen tool was not installed at $tool"

step "3/6 your game"
if [ ! -f "$repo/game/default.xex" ]; then
  [ -n "$god" ] || fail "game/ is empty: give your Games on Demand package with --god"
  logged extract python3 -I "$repo/scripts/extract_god.py" "$god" "$repo/game"
fi
echo "game files: $repo/game"

step "4/6 recompile the game's code (about 2 minutes)"
(cd "$repo" && logged codegen "$tool" codegen fifa19_manifest.toml)

step "5/6 build the game ($config)"
logged game-configure cmake -S "$repo" --preset "$preset" -DCMAKE_PREFIX_PATH="$sdk/out/install/mac-arm64"
logged game-build cmake --build "$repo/out/build/$preset" -j "$jobs"
[ -x "$repo/out/build/$preset/fifa19" ] || fail "the game was not built at out/build/$preset/fifa19"

if [ -n "$app" ]; then
  step "6/6 FIFA 19.app"
  logged app bash "$repo/launcher/mac/make_app.sh" --config "$config"
  echo "app: $repo/out/FIFA 19.app"
fi
echo
echo "start it with:  bash scripts/play_mac.sh        (log: out/build/$preset/run.log)"
