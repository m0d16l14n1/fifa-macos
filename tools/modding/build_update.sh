#!/bin/sh
# Builds the whole update as one mod (one database, as each mod's database replaces the game's whole):
#   1. a PC squads file's ratings and squads, and its Legends league (pcsquads.py, leagues/pc2026.json), when given;
#   2. today's squads from ESPN for the leagues in leagues/world.json, with the clubs the game hasn't (Wrexham) made
#      in the places of those that left (squads.py, clubs.py);
#   3. the leagues the game hasn't, from ESPN (league.py: leagues/rus.json);
#   4. an FC 27 dump's ratings for every player it has, and its squads for the leagues ESPN hasn't (fc27.py,
#      leagues/fc27.json), when given;
#   5. their kits, crests and logos, the Legends' copied heads (teamassets.py), their competitions, and the
#      competitions of leagues with more or fewer clubs today, fitted to them (compdata.py);
#   6. PC kit mods' kits, menu pictures, crowd flags and banners, converted (fbkits.py, leagues/kits.json);
#   7. the free agents kept to the best 500, as the game's own pool (freeagents.py), and every league's table
#      places once each (tables.py: Career fills the tables of leagues under way from them);
#   8. the calendar 8 years on: Career starts in July 2026 (calendar_shift.py).
# Each step works on the tables the one before left. The mod lands in out/mods/update; put it (or a link to it) in
# ~/Library/Application Support/FIFA 19/Mods. ESPN's files are cached in out/moddata/espn (fetched when missing).
#
#   sh tools/modding/build_update.sh [SQUADFILE [FC27.csv]]
#     SQUADFILE: the PC game's Squads<date> (FBCHUNKS; by default the newest in out/moddata/pc-squads), or -
#     for none; FC27.csv: the FC 27 dump's players.csv
#     (by default tools/modding/sources/stats-dump/data/players.csv, git-ignored, when there)
set -e
here="$(cd "$(dirname "$0")" && pwd)"; root="$(cd "$here/../.." && pwd)"
squadfile="$1" fc27="${2:-$here/sources/stats-dump/data/players.csv}"
[ -f "$fc27" ] || fc27=""
if [ -z "$squadfile" ]; then  # by default the newest in out/moddata/pc-squads
  squadfile=$(ls -t "$root"/out/moddata/pc-squads/Squads[0-9]* 2>/dev/null | head -1)
fi
[ "$squadfile" = - ] && squadfile=""
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
mv "$work/csv/squads.json" "$work/csv/squads-clubs.json" "$work/"
mv "$work/csv/squads-strings.csv" "$work/strings-squads.csv"
python3 "$here/teamassets.py" "$work/squads-clubs.json" "$game" "$mod" | tail -1

for name in $leagues; do
  cfg="$here/leagues/$name.json"
  league=$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c['source_league'], ' '.join(c['seasons']))" "$cfg")
  [ -f "$espn/${league%% *}-teams.json" ] || python3 "$here/sources/espn.py" ${league%% *} "$espn" ${league#* }
  python3 "$here/league.py" "$cfg" "$work/csv" "$espn" "$work/csv" "$work/strings-$name.csv" $pc
  mv "$work/csv/league.json" "$work/league-$name.json"
  python3 "$here/teamassets.py" "$work/league-$name.json" "$game" "$mod"
done
[ -f "$work/legends.json" ] && python3 "$here/teamassets.py" "$work/legends.json" "$game" "$mod"
if [ -n "$fc27" ]; then
  python3 "$here/fc27.py" "$here/leagues/fc27.json" "$work/csv" "$fc27" "$work/csv" "${pc:--}" \
    "$work/squads.json" "$work"/league-*.json
  mv "$work/csv/fc27.json" "$work/csv/fc27-clubs.json" "$work/"
  mv "$work/csv/fc27-strings.csv" "$work/strings-fc27.csv"
  python3 "$here/teamassets.py" "$work/fc27-clubs.json" "$game" "$mod" | tail -1
fi
# PC kit mods (leagues/kits.json: Frosty .fbmod files, git-ignored, used when there): their kits, menu kit
# pictures, crowd flags and banners, converted to the Xbox's (fbkits.py; its Oodle decoder: build_ooz.sh).
if python3 -c "import json,os,sys; os.chdir(sys.argv[2]); sys.exit(not any(os.path.exists(m['path']) for m in json.load(open(sys.argv[1]))['mods']))" \
    "$here/leagues/kits.json" "$here"; then
  [ -x "$here/../../out/tools/ooz-x86" ] || sh "$here/build_ooz.sh"
  python3 "$here/fbkits.py" "$here/leagues/kits.json" "$game" "$mod" "$work/csv" \
    "$work/squads-clubs.json" "$work/fc27-clubs.json" "$work"/league-*.json | tail -1
fi
python3 "$here/freeagents.py" "$work/csv" 500
python3 "$here/tables.py" "$work/csv"
python3 "$here/calendar_shift.py" 8 "$work/csv"

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
# The Legends League has no competition: it is for Kick Off (and the game's other one-off matches), out of
# Career, as Rest of World is (Career lists only the leagues compdata has).
# The leagues that have more (or fewer) clubs today than the game's competition: fitted (MLS's 30 for 23).
resize=$(python3 -c "import json,sys; print(*json.load(open(sys.argv[1])).get('resize', []), *json.load(open(sys.argv[2])).get('resize', []))" \
  "$here/leagues/world.json" "$here/leagues/fc27.json")
n=$((n + 1)); python3 "$here/compdata.py" resize "$src" "$work/comp$n" "$work/csv" $resize
src="$work/comp$n"
mkdir -p "$mod/$dir"
cp "$src"/*.txt "$mod/$dir/"
python3 "$here/calendar_shift.py" 8 "$work/none" "$mod/$dir" "$game" | sed 's/ ()//'

# The names: every step's strings in one file.
{ echo "stringid,text"; for f in "$work"/strings-*.csv; do tail -n +2 "$f"; done; } > "$mod/strings/eng_us.csv"
echo "built $mod ($(du -sh "$mod" | cut -f1))"
