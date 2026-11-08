#!/bin/sh
# Starts the game through the installed app's launcher (/Applications/FIFA 19.app, or FIFA19_APP), as a player
# would, for test runs: the window stays in the background, audio is muted (--sound to keep it), and this waits
# until the game quits. Other options go to the game (a pad script, a present log...).
#
# Settings: the game's defaults, from a folder of the tests' own (out/test-support: no fifa19.toml, the rest a
# copy of the player's profile, saves and shader caches, made once), so a player's own fifa19.toml doesn't change
# what is measured; --user-settings runs with the player's (~/Library/Application Support/FIFA 19), to reproduce
# what they see; --settings FILE runs with that fifa19.toml (copied into the test folder for the run).
# --game DIR runs the game from another folder (a copy of game/ with changed files, for mods). Any game
# option goes on the command line as well, after these: --vsync=false --fifa19_temporal_aa=false ...
#
#   sh scripts/run_app.sh [--sound] [--user-settings | --settings FILE] [--game DIR] --fifa19_pad_script=$PWD/scripts/pad/kickoff.txt ...
#
# Install the app after a build first: sh launcher/mac/make_app.sh "/Applications/FIFA 19.app"
# Log: ~/Library/Logs/FIFA 19/fifa19.log.
app="${FIFA19_APP:-/Applications/FIFA 19.app}"
settings_file="" game_dir="" mute="--audio_mute=true" support="$(cd "$(dirname "$0")/.." && pwd)/out/test-support"
user="$HOME/Library/Application Support/FIFA 19"
while [ $# -gt 0 ]; do
  case "$1" in
    --sound) mute=""; shift ;;
    --user-settings) support="$user"; shift ;;
    --settings) settings_file=$2; shift 2 ;;
    --game) game_dir=$(cd "$2" && pwd) || exit 1; shift 2 ;;
    *) break ;;
  esac
done
[ -x "$app/Contents/MacOS/FIFA 19 Launcher" ] || { echo "no launcher in $app" >&2; exit 1; }
if [ "$support" != "$user" ]; then
  mkdir -p "$support"
  # The profile, its saves and the shader caches; not fifa19.toml, nor the player's mods (a test's mods come
  # with --game: the player's would go on over them).
  rm -rf "$support/Mods" "$support/Modded Game"
  for item in "$user"/*; do
    name=$(basename "$item")
    case "$name" in fifa19.toml|Mods|"Modded Game") continue ;; esac
    [ -e "$support/$name" ] || cp -R "$item" "$support/$name"
  done
  # The game's defaults, or the settings file asked for.
  rm -f "$support/fifa19.toml"
  if [ -n "$settings_file" ]; then cp "$settings_file" "$support/fifa19.toml" || exit 1; fi
fi
FIFA19_GAME="$game_dir" FIFA19_SUPPORT="$support" FIFA19_LAUNCHER_PLAY=1 FIFA19_LAUNCHER_BACKGROUND=1 FIFA19_LAUNCHER_ARGS="$mute $*" "$app/Contents/MacOS/FIFA 19 Launcher"
