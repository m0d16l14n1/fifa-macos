# Debugging, testing and reverse engineering

## Running for tests

Test runs go through the installed app, as a player starts it: install it after a build
(`sh launcher/mac/make_app.sh "/Applications/FIFA 19.app"`), then `sh scripts/run_app.sh <game options>` starts
the game through its launcher with the window in the background and the audio muted (`--sound` keeps it), and
waits until the game quits. The launcher passes `FIFA19_LAUNCHER_ARGS` to the game and quits with it
(`FIFA19_LAUNCHER_PLAY=1`, `FIFA19_LAUNCHER_BACKGROUND=1`). The log is `~/Library/Logs/FIFA 19/fifa19.log`.

### Quick matches: any stadium, time of day and weather in a minute

FIFA has EA's own test switches compiled in: ini keys the engine reads through one getter (`sub_8242ADF8`), which
`src/ini_overrides.cpp` answers from `fifa19_ini=KEY=VALUE,...`. `fifa19_quick_match=true` sets the ones for EA's
auto match: no intro movies or menus (`SKIP_BOOTFLOW=1`, `BOOT_TO_MENU=0`), the practice arena's idle timer
starts `FREE_ROAM_AUTOMATCH` a second later, and the match (the CPU against the CPU, walk-out and all) is on about
a minute after start. Its settings:

| Option | Key | Values |
|---|---|---|
| `fifa19_match_stadium` | `FREE_ROAM_AUTOMATCH/STADIUM_ID` | the stadium's id (1 Old Trafford; the ids are those of `data/ui/imgassets/stadiumsbig/stadium_<id>_<lighting>.dds`); -1 the game picks |
| `fifa19_match_time` | `STADIUM_LIGHT_TYPE_ID` | 1 day, 3 night: the two lightings every stadium has (`crowdplacement/crowd_<id>_<1\|3>.dat`; 0, 2 and 4 draw placeholder textures). `FREE_ROAM_AUTOMATCH/STADIUM_TOD` is something else: every stadium takes 1, 3 and 5, all daylight |
| `fifa19_match_weather` | `FREE_ROAM_AUTOMATCH/WEATHER_TYPE` | 0 clear, 1 rain, 2 snow, 3 overcast (the game's own order: CLR, RAN, SNW, OCS) |
| `fifa19_match_half_length` | `FREE_ROAM_AUTOMATCH/HALF_LENGTH` | minutes |
| `fifa19_match_home_team`, `_away_team` | `FREE_ROAM_AUTOMATCH/HOME_TEAM_ID`, `AWAY_TEAM_ID` | team ids; -1 random |

The launcher's Quick Match page sets them and starts one. `sh scripts/conditions.sh 1:3:2 1:0:0` plays one per
STADIUM:TIME:WEATHER and keeps shots, a burst of consecutive frames and the present log's summary of each in
`out/conditions/`. `fifa19_ini_log=true` logs every ini key the game reads with its value (about 500 at boot:
`DISABLE_FRAMERATE`, `FORCE_RENDER_30`, `MSAA_MODE`, `CROWD/...`); `fifa19_guest_log=<text>|<text>` logs the
game's own debug labels (EA's print, `sub_826A1EB0`, empty in the retail build; `*` for all).

Test runs never take the screen: `FIFA19_BACKGROUND=1 sh scripts/play_mac.sh` starts the game windowed, without
focus or a Dock icon (SDL's background-app mode; the window is ordered in without being activated). The Metal
performance HUD is on in every run (`FIFA19_METAL_HUD=0` turns it off).

| Variable | What |
|---|---|
| `FIFA19_BACKGROUND=1` | a window that never takes focus |
| `FIFA19_METAL_HUD=0` | no Metal HUD |
| `FIFA19_METAL_VALIDATION=1` | Metal API validation (slow) |
| `FIFA19_LLDB=1` | under lldb: stops at the first crash, `bt all` for every thread |
| `FIFA19_NATIVE_LIBC=0` | the game's own memcpy/memset/memmove instead of the host's |
| `FIFA19_NATIVE_LIMITER=1` | the main loop's step limiter sleeps instead of spinning (experimental, BACKLOG P5) |
| `FIFA19_BUILD=release` | another build folder |

The log is `run.log` in the build folder (the ten before it in `logs/`).

## SDK checks

`bash scripts/test_sdk.sh` builds and runs the programs in `tests/sdk/` against the installed SDK: behaviour the
game depends on that the SDK's own tests don't cover (today: guest event and multi-object wait semantics).

## The dev pad

A scripted controller merged with the real ones, for unattended runs:

- `--fifa19_pad_script=scripts/pad/kickoff.txt`: title screen to a Kick Off match.
- `scripts/pad/match.sh --stadium 3 --time 7 --weather 2 > match.txt`: a match anywhere, at any time and weather.
- `--fifa19_pad_pipe=<path>`: commands from a named pipe (`echo "press a" > <path>`).

Commands: `press`, `hold`, `down`, `up` (buttons `a b x y lb rb back start ls rs up down left right`), `trigger
lt|rt <0..1> [duration]`, `stick lx|ly|rx|ry <-1..1> [duration]`, `release`, `wait`, `log <text>`, `set <cvar>
<value>`, `shot <name>`, `burst <name> <count>` (consecutive frames), `quit`.

Reading the screen (macOS Vision on the presented frame): `ocr` logs each line of text with its place and the
colour behind it, `waitfor <timeout> <text>`, `expect <text>`, `select <button> <max> <text>` (presses until the
item is highlighted), `choose <max> <row> = <value>` (presses right until the row shows the value), `ifscreen <text>
: <command>`. Guest memory: `dump <address> <size> <name>` (hex; the image is `dump 82000000 1CA0000 image`, whose
strings list the ini keys), `peek <address> [size]`, `poke <address> <bytes>`.

## Screenshots

`shot <name>` writes the next presented frame (game and overlays) to `shots/<name>.ppm` in the working folder,
in-process: no screen recording permission, and the window may be covered. `python3 scripts/ppm2png.py
shots/*.ppm` converts them. `--metal_present_capture=<file.ppm>` writes one every 2 s for a whole run.

## When something is wrong

| Symptom | First look |
|---|---|
| a slow frame | `Metal hitch: N ms between swaps` lines (`metal_hitch_log_ms`, 250 by default) |
| the game stops presenting | `stall-<time>.txt` in the working folder: every thread's stack after 2 s without a frame (`metal_stall_sample_ms`) |
| steady-state cost | the `Metal frame time` line every 150 frames: GPU busy, CPU waiting, texture loads, resolves into textures, passes |
| choppiness | the `Metal frame pacing` line every 5 s: p50/p95/p99/max frame interval, frames over 1.5x the median |
| judder (what reaches the screen) | `--present_log=<file.csv>`, then `python3 scripts/present_stats.py <file.csv> --from <s>`: frames shown a second, repeats, frames never shown, and the motion step (game time per refresh) |
| where the GPU's time goes | `xctrace record --template 'Metal System Trace' --attach <pid> --time-limit 3s --output x.trace`, then `python3 scripts/gpu_intervals.py x.trace` (GPU time by channel and pass; `metal_debug_labels=true` names the passes by their targets) |
| where the command processor's time goes | `/usr/bin/sample <pid> 5 -file s.txt`, then `python3 scripts/sample_self.py s.txt "GPU Commands"` (self time per function) |
| a GPU frame in Metal's own debugger | launch with `MTL_CAPTURE_ENABLED=1`; `gpucapture boundaries --pid <pid>`, `gpucapture start --pid <pid> --boundary <the "rexglue guest" queue> --count 40` (a frame is ~16 command buffers; a trace of 40 is ~30 GB, kept in `$TMPDIR` too), then `gpudebug -t <trace>` |
| the GPU waiting on the game | `--gpu_wait_stats=true`: what WAIT_REG_MEM polled and for how long |
| the game's own frame limiters | `--fifa19_limiter_stats=true`: calls and waits per divisor of `sub_823686C0` |
| a resolve reloading a texture | `--metal_resolve_into_textures_log=true`: why a resolve was not copied into a loaded texture |
| what every thread is doing | `/usr/bin/sample <pid> 5` during play; `Sort by top of stack` at its end |
| fences | `Metal fences: N a frame written by the GPU, M by the command processor at once` |
| a wrong texture | `metal_debug_frame=<n>` logs every draw, texture load and resolve of frame n; `metal_debug_capture=true` (dev pad `set`) dumps a frame's resolves to `metal_debug_dir` |
| temporal AA, frame generation | `--temporal_aa_debug=4` (every 120 frames: whether the pass ran, scene draws jittered), `11` (the camera cut check every frame), `--metal_taa_debug_vectors=true` (the motion vectors in place of the picture); the `Metal frame generation` lines (generated, presented, held back and why) |
| a Metal error | `FIFA19_METAL_VALIDATION=1` |
| a crash | `FIFA19_LLDB=1`, or the `.ips` report in `~/Library/Logs/DiagnosticReports` |
| a GPU frame in detail | Xcode's Metal frame capture: `MTL_CAPTURE_ENABLED=1`, then capture from Xcode attached to the process |

## Reverse engineering

- The game's functions keep their guest addresses: `sub_825A5C60` is the code at 0x825A5C60 in default.xex
  (`generated/default/`). A hook replaces one with `REX_HOOK_RAW(sub_XXXXXXXX)` (see `src/native_libc_hooks.cpp`).
- Codegen reports what it could not place (`out/logs/codegen.log`: "target not in any function"); the passes in
  `config/fifa19.toml` say how each kind was resolved.
- Shaders: `metal_shader_dump_dir=<dir>` writes every translated shader (MSL) with its guest hash; the hash is what
  a draw policy keys on.
- Textures: `metal_debug_frame` lists each texture by guest address, format and size; FIFA's important ones are
  noted in [`METAL.md`](METAL.md).
