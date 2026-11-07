# The macOS launcher

A SwiftUI app without an Xcode project: `sh launcher/mac/build.sh` compiles `Sources/*.swift` with `swiftc`
(macOS 14 or later, Apple silicon), and `sh launcher/mac/make_app.sh` makes `out/FIFA 19.app` with the launcher as
its main program and the game (`fifa19`, its guest DLL libraries, the ReXGlue runtime and the GPU plugin) beside it
in `Contents/MacOS`. `scripts/make_mac.sh` runs both.

| File | What |
|---|---|
| `App.swift` | the window and its pages: Play (start, stop, the log), Game Files (choose or extract the game), About |
| `Settings.swift` | the game settings offered (Graphics, Controls), each a cvar with the game's default |
| `Game.swift` | where things are, starting and stopping the game, extracting a Games on Demand package |
| `TomlFile.swift` | edits `fifa19.toml` in place: only the lines the launcher sets change |

| Where | What |
|---|---|
| `~/Library/Application Support/FIFA 19/fifa19.toml` | the game's settings (a setting at its default is no line) |
| `~/Library/Application Support/FIFA 19/` | the profile and saves, the shader caches |
| `~/Library/Logs/FIFA 19/fifa19.log` | the game's log (stall reports beside it) |
| the launcher's user defaults (`local.fifa19-macos`) | its own preferences: the game folder, Metal HUD (on), background window, validation, extra options |

The game folder is passed on the command line (`--game_data_root`): the SDK resolves its paths before it reads
`fifa19.toml`.

On its own, outside the app: `FIFA19_DIR=out/build/mac-arm64-relwithdebinfo out/launcher-mac/fifa19-launcher`.
`FIFA19_LAUNCHER_PAGE=Graphics` opens a page, `FIFA19_LAUNCHER_PLAY=1` presses Play (tests and screenshots).
