#!/bin/sh
# Starts the game through the installed app's launcher (/Applications/FIFA 19.app, or FIFA19_APP), as a player
# would, for test runs: the window stays in the background, audio is muted (--sound to keep it), and this waits
# until the game quits. Other options go to the game (a pad script, a present log...).
#
# Settings: the game's defaults, from a folder of the tests' own (out/test-support: no fifa19.toml, the rest a
# copy of the player's profile, saves and shader caches, made once), so a player's own fifa19.toml doesn't change
# what is measured; --user-settings runs with the player's (~/Library/Application Support/FIFA 19), to reproduce what they see.
#
#   sh scripts/run_app.sh [--sound] [--user-settings] --fifa19_pad_script=$PWD/scripts/pad/kickoff.txt ...
#
# Install the app after a build first: sh launcher/mac/make_app.sh "/Applications/FIFA 19.app"
# Log: ~/Library/Logs/FIFA 19/fifa19.log.
app="${FIFA19_APP:-/Applications/FIFA 19.app}"
mute="--audio_mute=true" support="$(cd "$(dirname "$0")/.." && pwd)/out/test-support"
user="$HOME/Library/Application Support/FIFA 19"
while [ $# -gt 0 ]; do
  case "$1" in
    --sound) mute=""; shift ;;
    --user-settings) support="$user"; shift ;;
    *) break ;;
  esac
done
[ -x "$app/Contents/MacOS/FIFA 19 Launcher" ] || { echo "no launcher in $app" >&2; exit 1; }
if [ "$support" != "$user" ]; then
  mkdir -p "$support"
  # The profile, its saves and the shader caches; not fifa19.toml.
  for item in "$user"/*; do
    name=$(basename "$item")
    [ "$name" = fifa19.toml ] && continue
    [ -e "$support/$name" ] || cp -R "$item" "$support/$name"
  done
fi
FIFA19_SUPPORT="$support" FIFA19_LAUNCHER_PLAY=1 FIFA19_LAUNCHER_BACKGROUND=1 FIFA19_LAUNCHER_ARGS="$mute $*" "$app/Contents/MacOS/FIFA 19 Launcher"
