#!/bin/sh
# Builds the whole update as one mod (one database, as each mod's database replaces the game's whole):
#   1. a PC squads file's ratings and squads, and its Legends league (pcsquads.py, leagues/pc2026.json), when given;
#   2. today's squads from ESPN for the leagues in leagues/world.json (squads.py);
#   3. the leagues the game hasn't, from ESPN (league.py: leagues/rus.json);
#   4. their kits, crests and logos, the Legends' copied heads (teamassets.py), their competitions (compdata.py);
#   5. the free agents kept to the best 500, as the game's own pool (freeagents.py).
# Each step works on the tables the one before left. The mod lands in out/mods/update; put it (or a link to it) in
# ~/Library/Application Support/FIFA 19/Mods. ESPN's files are cached in out/moddata/espn (fetched when missing).
#
#   sh tools/modding/build_update.sh [SQUADFILE]     SQUADFILE: the PC game's Squads<date> (FBCHUNKS)
set -e
here="$(cd "$(dirname "$0")" && pwd)"; root="$(cd "$here/../.." && pwd)"
squadfile="$1"
game="${FIFA19_GAME_DIR:-$root/game}" espn="$root/out/moddata/espn"
work="$root/out/mod/update" mod="$root/out/mods/update" base="$root/out/mod/csv"
leagues="rus"
[ -f "$base/players.csv" ] || sh "$here/db.sh" export
rm -rf "${work:?}" "${mod:?}"
mkdir -p "$work/csv" "$work/changed" "$mod/strings"
cp "$base"/*.csv "$work/csv/"
pc=""

if [ -n "$squadfile" ]; then
  python3 "$here/pcsquads.py" "$here/leagues/pc2026.json" "$work/csv" "$squadfile" "$work/csv" \
    "$work/strings-pc.csv" "$espn"
  mv "$work/csv/pcsquads.json" "$work/csv/legends.json" "$work/"
  pc="$work/pcsquads.json"
fi

python3 - "$here/leagues/world.json" <<'PY' | while read -r code; do
import json, sys
print(*json.load(open(sys.argv[1]))['leagues'].values(), sep='\n')
PY
  python3 "$here/sources/espn.py" "$code" "$espn" none
done
python3 "$here/squads.py" "$here/leagues/world.json" "$work/csv" "$espn" "$work/csv" $pc
mv "$work/csv/squads.json" "$work/"

for name in $leagues; do
  cfg="$here/leagues/$name.json"
  league=$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c['source_league'], ' '.join(c['seasons']))" "$cfg")
  [ -f "$espn/${league%% *}-teams.json" ] || python3 "$here/sources/espn.py" ${league%% *} "$espn" ${league#* }
  python3 "$here/league.py" "$cfg" "$work/csv" "$espn" "$work/csv" "$work/strings-$name.csv" $pc
  mv "$work/csv/league.json" "$work/league-$name.json"
  python3 "$here/teamassets.py" "$work/league-$name.json" "$game" "$mod"
done
[ -f "$work/legends.json" ] && python3 "$here/teamassets.py" "$work/legends.json" "$game" "$mod"
python3 "$here/freeagents.py" "$work/csv" 500

# The database: the tables the steps changed.
for f in "$work/csv"/*.csv; do
  cmp -s "$f" "$base/$(basename "$f")" || cp "$f" "$work/changed/"
done
sh "$here/db.sh" mod "$work/changed" "$mod" | tail -1

# The competitions: the game's compdata (unpacked once), plus each league.
comp="$root/out/mod/compdata" dir=dlc/dlc_footballcompeng/dlc/footballcompeng/data/compdata
if [ ! -f "$comp/compobj.txt" ]; then
  mkdir -p "$comp"
  for f in compobj settings schedule advancement initteams standings tasks weather compids activeteams dataver; do
    python3 "$here/modgame.py" extract "$game/data1.big" "$dir/$f.txt" "$comp/$f.stored"
    "$root/out/tools/unchunk" "$comp/$f.stored" "$comp/$f.txt"
    rm -f "$comp/$f.stored"
  done
fi
src="$comp" n=0
for name in $leagues; do
  n=$((n + 1)); python3 "$here/compdata.py" add "$src" "$work/comp$n" "$here/leagues/$name.json" "$work/league-$name.json"
  src="$work/comp$n"
done
if [ -f "$work/legends.json" ]; then
  n=$((n + 1)); python3 "$here/compdata.py" add "$src" "$work/comp$n" "$here/leagues/pc2026.json" "$work/legends.json"
  src="$work/comp$n"
fi
mkdir -p "$mod/$dir"
cp "$src"/*.txt "$mod/$dir/"

# The names: every step's strings in one file.
{ echo "stringid,text"; for f in "$work"/strings-*.csv; do tail -n +2 "$f"; done; } > "$mod/strings/eng_us.csv"
echo "built $mod ($(du -sh "$mod" | cut -f1))"
