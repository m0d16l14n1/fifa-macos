#!/bin/sh
# Cleans what builds and test runs leave behind. A dry run unless --yes: it lists what it would remove and how
# big it is. Test outputs (runs) are deleted for good: they are only measurements and pictures, and the Trash
# would keep the space taken. Builds (game, generated, sdk) go to the Trash.
#
#   sh scripts/clean.sh [--yes] [what...]
#
#   runs      test outputs: run logs and captures in out/ (out/logs, out/shots, out/conditions*, the build
#             folders' logs, shots and stall reports, out/bench), the game's stall reports in ~/Library/Logs/FIFA 19,
#             and Instruments / GPU traces of fifa19 in the temporary folder
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
    -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
      for p in "$root"/out/logs "$root"/out/shots "$root"/out/conditions* "$root"/out/cond* "$root"/out/bench; do
        [ -e "$p" ] && echo "$p" >> "$list"
      done
      find "$HOME/Library/Logs/FIFA 19" -maxdepth 1 \( -name 'stall-*.txt' -o -name 'fifa19.*.log' \) 2>/dev/null >> "$list"
      find "${TMPDIR:-/tmp}" -maxdepth 1 \( -name 'instruments*.ktrace' -o -name 'fifa19*.gputrace' -o -name '*.trace' \) \
        2>/dev/null >> "$list" ;;
    game)
      for p in "$root/out/build" "$root/out/launcher-mac" "$root/out/FIFA 19.app"; do [ -e "$p" ] && echo "$p" >> "$list"; done ;;
    generated) [ -d "$root/generated" ] && echo "$root/generated" >> "$list" ;;
    sdk) [ -d "$root/third_party/rexglue-sdk/out" ] && echo "$root/third_party/rexglue-sdk/out" >> "$list" ;;
  esac
done
if [ ! -s "$list" ]; then echo "nothing to clean"; exit 0; fi
while IFS= read -r p; do du -sh "$p" 2>/dev/null; done < "$list"
if [ -z "$yes" ]; then echo "(dry run: --yes removes these)"; exit 0; fi
stamp=$(date +%Y%m%d-%H%M%S)
case " $what " in *" runs "*) runs=1 ;; *) runs= ;; esac
while IFS= read -r p; do
  case "$p" in
    "$root/out/build"*|"$root/out/launcher-mac"*|"$root/generated"|"$root/third_party/rexglue-sdk/out")
      if [ -n "$runs" ] && [ "$(dirname "$p")" != "$root/out" ] && [ "$p" != "$root/generated" ] &&
         [ "$p" != "$root/third_party/rexglue-sdk/out" ] && [ "$p" != "$root/out/build" ]; then
        rm -rf "$p" && echo "deleted $p"   # a build folder's logs and shots
      else
        mv "$p" "$HOME/.Trash/fifa19-$stamp-$(basename "$p")" && echo "trashed $p"
      fi ;;
    *) rm -rf "$p" && echo "deleted $p" ;;
  esac
done < "$list"
