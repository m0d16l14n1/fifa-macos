# Building

macOS on Apple silicon, Xcode 16 or newer (Clang 18+), CMake 3.25+, Ninja, Git and Python 3.10+
(`brew install cmake ninja`). About 15 GB free: the game (6.6 GB), the SDK and the build.

## One command

```bash
bash scripts/make_mac.sh --god /path/to/454109F9/00007000/<package file>
```

`--god` is the Games on Demand package's header file, with its `.data` folder beside it. Every step is skipped
when its result is there, so after a failure or a change the same command continues. `--config Release` builds the
game without debug info; `--no-app` skips the app bundle.

| Step | What | Result | Time on an M5 |
|---|---|---|---|
| 1 | checks the tools | | |
| 2 | `scripts/sdk.sh`: clones ReXGlue v0.10.0, applies `patches/`, builds and installs it | `third_party/rexglue-sdk/out/install/mac-arm64` | 15-25 min, once |
| 3 | `scripts/extract_god.py`: the game's files out of the package | `game/` | 1-2 min |
| 4 | `rexgluerd codegen fifa19_manifest.toml`: the game's PowerPC code as C++ | `generated/` (470 MB) | 2 min |
| 5 | CMake, preset `mac-arm64-relwithdebinfo` | `out/build/mac-arm64-relwithdebinfo/fifa19` | 20-40 min first time |
| 6 | `launcher/mac/make_app.sh` | `out/FIFA 19.app` | 1 min |

Later builds: `cmake --build out/build/mac-arm64-relwithdebinfo`. The build reruns codegen by itself when a config
in `config/` or the game changes.

## By hand

```bash
bash scripts/sdk.sh
python3 -I scripts/extract_god.py <package file> game
third_party/rexglue-sdk/out/install/mac-arm64/bin/rexgluerd codegen fifa19_manifest.toml
cmake --preset mac-arm64-relwithdebinfo -DCMAKE_PREFIX_PATH="$PWD/third_party/rexglue-sdk/out/install/mac-arm64"
cmake --build out/build/mac-arm64-relwithdebinfo
```

## What is where

| Path | What |
|---|---|
| `fifa19_manifest.toml` | default.xex and the guest DLLs the game loads: CardsDLLzf (Ultimate Team), FootballCompEngzf and powdllzf (DLC) |
| `config/*.toml` | function boundary overrides for codegen, each pass commented; `cardsdll.toml` also moves that DLL's dispatch table |
| `src/` | the app (`Fifa19App`: paths, defaults, keyboard layout), native memcpy/memset/memmove, XUsbcam stubs, the dev pad |
| `scripts/` | build, run, benchmark, clean, extraction and capture tools (each says what it does in its header) |
| `scripts/pad/` | dev pad scripts: title screen to a match, the benchmark, `match.sh` for any stadium/time/weather |
| `launcher/mac/` | the SwiftUI launcher and the app bundler |
| `patches/` | the SDK's patches ([`patches/README.md`](../patches/README.md)) |
| `tests/sdk/` | checks of SDK behaviour the game depends on, run by `bash scripts/test_sdk.sh` |
| `third_party/rexglue-sdk` | the SDK checkout (not in git) |
| `game/` | your extracted game (not in git) |
| `out/` | builds, logs (`out/logs`), benchmark results (`out/bench`) |

## Cleaning

`sh scripts/clean.sh` lists what test runs left (logs, stall reports, shots, benchmark results); `--yes` moves
them to the Trash. `clean.sh game`, `generated` and `sdk` do the same for the builds, the generated code and the
SDK's build. Your game files, saves and settings are never touched.
