#!/bin/sh
# Starts the game through the installed app's launcher (/Applications/FIFA 19.app, or FIFA19_APP), as a player
# would, for test runs: the window stays in the background, audio is muted (--sound to keep it), and this waits
# until the game quits. Other options go to the game (a pad script, a present log...).
#
#   sh scripts/run_app.sh [--sound] --fifa19_pad_script=$PWD/scripts/pad/kickoff.txt ...
#
# Install the app after a build first: sh launcher/mac/make_app.sh "/Applications/FIFA 19.app"
# Log: ~/Library/Logs/FIFA 19/fifa19.log.
app="${FIFA19_APP:-/Applications/FIFA 19.app}"
mute="--audio_mute=true"
while [ $# -gt 0 ]; do
  case "$1" in
    --sound) mute=""; shift ;;
    *) break ;;
  esac
done
[ -x "$app/Contents/MacOS/FIFA 19 Launcher" ] || { echo "no launcher in $app" >&2; exit 1; }
FIFA19_LAUNCHER_PLAY=1 FIFA19_LAUNCHER_BACKGROUND=1 FIFA19_LAUNCHER_ARGS="$mute $*" "$app/Contents/MacOS/FIFA 19 Launcher"
