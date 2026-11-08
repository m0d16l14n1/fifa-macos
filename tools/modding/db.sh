#!/bin/sh
# The game's database (players, teams, leagues, links...) as CSV files to edit, and a mod made from them.
#
#   sh tools/modding/db.sh export [DIR]          every table to DIR/<table>.csv (default out/mod/csv)
#   sh tools/modding/db.sh mod CSVDIR MODDIR     a mod with the tables whose CSV is in CSVDIR changed:
#                                                MODDIR/data/db/fifa_ng_db.db (the other tables as they are)
#
# Copy the CSV files you change to a folder of their own, edit them (a spreadsheet does), then make the mod and
# put MODDIR in ~/Library/Application Support/FIFA 19/Mods (or run it: sh scripts/run_app.sh --game, after
# python3 tools/modding/modgame.py build). The game folder is game/ (FIFA19_GAME_DIR to change it).
set -e
here="$(cd "$(dirname "$0")" && pwd)"; root="$(cd "$here/../.." && pwd)"
game="${FIFA19_GAME_DIR:-$root/game}" raw="$root/out/mod/raw"
db="$raw/fifa_ng_db.db" meta="$raw/fifa_ng_db-meta.xml"

unpack() {
  [ -f "$db" ] && [ -f "$meta" ] && return
  [ -x "$root/out/tools/unchunk" ] || sh "$here/build.sh"
  mkdir -p "$raw"
  for name in fifa_ng_db.db fifa_ng_db-meta.xml; do
    python3 "$here/modgame.py" extract "$game/data0.big" "data/db/$name" "$raw/$name.stored"
    "$root/out/tools/unchunk" "$raw/$name.stored" "$raw/$name"
    rm -f "$raw/$name.stored"
  done
}

case "$1" in
  export)
    unpack
    python3 "$here/fifadb.py" export "$db" "$meta" "${2:-$root/out/mod/csv}" ;;
  mod)
    [ -n "$2" ] && [ -n "$3" ] || { sed -n 2,11p "$0" >&2; exit 2; }
    unpack
    mkdir -p "$3/data/db"
    python3 "$here/fifadb.py" import "$db" "$meta" "$2" "$3/data/db/fifa_ng_db.db" ;;
  *)
    sed -n 2,11p "$0" >&2; exit 2 ;;
esac
