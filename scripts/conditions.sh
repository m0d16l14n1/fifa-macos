#!/bin/sh
# Plays quick matches (EA's auto match, booted straight into: no intro, no menus) in each of the given conditions,
# through the installed app, muted, in the background, and keeps per run: shots of the walk-out and of play, a
# burst of consecutive frames (flicker shows as frames that differ from both neighbours), the present log's
# summary (scripts/present_stats.py) and the game's log.
#
#   sh scripts/conditions.sh [--out DIR] [--wait SECONDS] [--teams HOME:AWAY] [--user-settings |
#                            --settings FILE] [--game "<options>"] STADIUM:TIME:WEATHER ...
#
# The same teams every run (default 11:9, Manchester United v Liverpool; -1 random) so runs compare. The game's
# default settings (scripts/run_app.sh); --user-settings: the player's fifa19.toml; --settings FILE: that
# fifa19.toml; --game "<options>": more game options, e.g. --game "--vsync=false --fifa19_temporal_aa=false".
#
#   STADIUM  the stadium's id (docs/DEBUGGING.md lists them; -1: the game picks)
#   TIME     1 day, 3 night (-1: the game picks)
#   WEATHER  0 clear, 1 rain, 2 snow, 3 overcast
#
# e.g. sh scripts/conditions.sh 1:3:1 1:1:0 13:3:2     (night rain, day clear, night snow)
# Results: out/conditions/<stadium>-<time>-<weather>/ (walkout.png, play.png; burst-*.ppm, 90 frames of the
# walk-out, and play-*.ppm, 120 of play; flicker-burst.txt and flicker-play.txt from scripts/flicker.py, with the
# flickering frames outlined in *.flicker.png; present.txt; log.txt). The raw frames are deleted after the
# analysis; sh scripts/clean.sh --yes removes the results.
set -e
repo="$(cd "$(dirname "$0")/.." && pwd)"
out="$repo/out/conditions" wait=55 home=11 away=9 settings="" extra=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) out=$2; shift 2 ;;
    --wait) wait=$2; shift 2 ;;
    --teams) home=${2%%:*} away=${2#*:}; shift 2 ;;
    --user-settings) settings=--user-settings; shift ;;
    --settings) settings="--settings $(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
    --game) extra="$extra $2"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) break ;;
  esac
done
mkdir -p "$out" && out="$(cd "$out" && pwd)"  # absolute: the game runs in its log folder
[ $# -gt 0 ] || { echo "give at least one STADIUM:TIME:WEATHER (see --help)" >&2; exit 2; }
log="$HOME/Library/Logs/FIFA 19/fifa19.log"
for spec in "$@"; do
  stadium=${spec%%:*} rest=${spec#*:}
  time=${rest%%:*} weather=${rest#*:}
  dir="$out/$stadium-$time-$weather"
  rm -rf "$dir"; mkdir -p "$dir"
  # The match is on about a minute after start (the walk-out first); then play from the kick-off.
  cat > "$dir/pad.txt" <<EOF
wait ${wait}s
shot walkout
burst burst 90
wait 40s
shot play
burst play 120
quit
EOF
  echo "== stadium $stadium, time $time, weather $weather"
  sh "$repo/scripts/run_app.sh" $settings --fifa19_pad_script="$dir/pad.txt" --fifa19_shot_dir="$dir" \
    --present_log="$dir/present.csv" --fifa19_quick_match=true --fifa19_match_stadium="$stadium" \
    --fifa19_match_time="$time" --fifa19_match_weather="$weather" --fifa19_match_home_team="$home" \
    --fifa19_match_away_team="$away" $extra > /dev/null 2>&1 || true
  cp "$log" "$dir/log.txt" 2>/dev/null || true
  python3 "$repo/scripts/ppm2png.py" "$dir/walkout.ppm" "$dir/play.ppm" --scale 2 > /dev/null 2>&1 || true
  [ -f "$dir/present.csv" ] && python3 "$repo/scripts/present_stats.py" "$dir/present.csv" --from 60 > "$dir/present.txt" 2>&1 || true
  for burst in burst play; do
    ls "$dir/$burst"-*.ppm > /dev/null 2>&1 || continue
    python3 "$repo/scripts/flicker.py" "$dir/$burst"-*.ppm --png > "$dir/flicker-$burst.txt" 2>&1 || true
    echo "   $burst: $(tail -1 "$dir/flicker-$burst.txt")"
  done
  # Pictures kept as PNG; the raw frames go (90 + 120 of them are 2.3 GB at 2560x1440).
  rm -f "$dir"/burst-*.ppm "$dir"/play-*.ppm "$dir"/walkout.ppm "$dir"/play.ppm
  grep -a "Unhandled guest\|dev pad: FAILED\|audio underrun" "$dir/log.txt" | head -3 || true
  echo "   $dir"
done
