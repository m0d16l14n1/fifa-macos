#!/bin/sh
# Cleans what builds and test runs leave behind. A dry run unless --yes: it lists what it would remove and how
# big it is. Removed items go to the Trash (recoverable), never rm.
#
#   sh scripts/clean.sh [--yes] [what...]
#
#   runs      run logs, stall reports and dev pad shots in the build folders, benchmark results (out/bench)
#   game      the game's build folders (out/build) and the launcher's build (out/launcher-mac, out/FIFA 19.app)
#   generated the generated code (generated/; the next build reruns codegen, about 2 minutes)
#   sdk       the SDK's build (third_party/rexglue-sdk/out; the next scripts/sdk.sh rebuilds it, the long step)
#   (default: runs)
#
# Never touched: game/ (your game files), FIFA-19/, the SDK checkout itself, saves and settings
# (~/Library/Application Support/FIFA 19).
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
yes=
what=
for a in "$@"; do
  case $a in
    --yes) yes=1 ;;
    runs|game|generated|sdk) what="$what $a" ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown: $a (see --help)" >&2; exit 2 ;;
  esac
done
[ -n "$what" ] || what=runs

list=$(mktemp)
trap 'rm -f "$list"' EXIT
for w in $what; do
  case $w in
    runs)
      find "$root/out/build" -maxdepth 2 \( -name 'logs' -o -name 'shots' -o -name '*.log' -o -name 'stall-*.txt' \) \
        2>/dev/null >> "$list"
      [ -d "$root/out/bench" ] && echo "$root/out/bench" >> "$list" ;;
    game)
      for p in "$root/out/build" "$root/out/launcher-mac" "$root/out/FIFA 19.app"; do [ -e "$p" ] && echo "$p" >> "$list"; done ;;
    generated) [ -d "$root/generated" ] && echo "$root/generated" >> "$list" ;;
    sdk) [ -d "$root/third_party/rexglue-sdk/out" ] && echo "$root/third_party/rexglue-sdk/out" >> "$list" ;;
  esac
done
if [ ! -s "$list" ]; then echo "nothing to clean"; exit 0; fi
while IFS= read -r p; do du -sh "$p" 2>/dev/null; done < "$list"
if [ -z "$yes" ]; then echo "(dry run: --yes moves these to the Trash)"; exit 0; fi
stamp=$(date +%Y%m%d-%H%M%S)
while IFS= read -r p; do
  name=$(basename "$p")
  mv "$p" "$HOME/.Trash/fifa19-$stamp-$name" && echo "trashed $p"
done < "$list"
