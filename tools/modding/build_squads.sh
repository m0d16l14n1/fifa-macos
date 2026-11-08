#!/bin/sh
# Builds the current-squads mod from ESPN's cached public roster data.
#
#   sh tools/modding/build_squads.sh
set -e
here="$(cd "$(dirname "$0")" && pwd)"; root="$(cd "$here/../.." && pwd)"
cfg="$here/leagues/world.json" espn="$root/out/moddata/espn"
work="$root/out/mod/world" mod="$root/out/mods/world"
[ -f "$root/out/mod/csv/players.csv" ] || sh "$here/db.sh" export
python3 - "$cfg" <<'PY' | while read -r code; do
import json,sys
print(*json.load(open(sys.argv[1]))['leagues'].values(), sep='\n')
PY
  # espn.py keeps every cached file, so this is offline when the cache is complete and fills any gaps when not.
  python3 "$here/sources/espn.py" "$code" "$espn" none
done
rm -rf "$work" "$mod"
python3 "$here/squads.py" "$cfg" "$root/out/mod/csv" "$espn" "$work/csv"
sh "$here/db.sh" mod "$work/csv" "$mod" | tail -1
echo "built $mod ($(du -sh "$mod" | cut -f1))"
