#!/bin/sh
# Builds a league mod from a config (tools/modding/leagues/<name>.json): squads and stats from ESPN, the
# database, the new teams' kits and crests, the competition, the names. The mod lands in out/mods/<name>;
# put it (or a link to it) in ~/Library/Application Support/FIFA 19/Mods.
#
#   sh tools/modding/build_league.sh rus [--fetch]     --fetch: fetch the source again (else what is cached)
set -e
here="$(cd "$(dirname "$0")" && pwd)"; root="$(cd "$here/../.." && pwd)"
name="$1"; cfg="$here/leagues/$name.json"
[ -f "$cfg" ] || { sed -n 2,7p "$0" >&2; exit 2; }
work="$root/out/mod/$name" mod="$root/out/mods/$name" espn="$root/out/moddata/espn"
game="${FIFA19_GAME_DIR:-$root/game}"
league=$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c['source_league'], ' '.join(c['seasons']))" "$cfg")
[ -f "$root/out/mod/csv/players.csv" ] || sh "$here/db.sh" export
if [ "$2" = "--fetch" ] || [ ! -f "$espn/${league%% *}-teams.json" ]; then
  python3 "$here/sources/espn.py" ${league%% *} "$espn" ${league#* }
fi
rm -rf "$work" "$mod"
python3 "$here/league.py" "$cfg" "$root/out/mod/csv" "$espn" "$work/csv" "$mod/strings/eng_us.csv"
python3 "$here/teamassets.py" "$work/csv/league.json" "$game" "$mod"
sh "$here/db.sh" mod "$work/csv" "$mod" | tail -1
# The competition: the game's compdata, unpacked once, plus this league.
comp="$root/out/mod/compdata" dir=dlc/dlc_footballcompeng/dlc/footballcompeng/data/compdata
if [ ! -f "$comp/compobj.txt" ]; then
  mkdir -p "$comp"
  for f in compobj settings schedule advancement initteams standings tasks weather compids activeteams dataver; do
    python3 "$here/modgame.py" extract "$game/data1.big" "$dir/$f.txt" "$comp/$f.stored"
    "$root/out/tools/unchunk" "$comp/$f.stored" "$comp/$f.txt"
    rm -f "$comp/$f.stored"
  done
fi
python3 "$here/compdata.py" add "$comp" "$mod/$dir" "$cfg" "$work/csv/league.json"
echo "built $mod ($(du -sh "$mod" | cut -f1))"
