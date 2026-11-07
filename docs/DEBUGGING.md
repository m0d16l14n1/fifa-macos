# Debugging, testing and reverse engineering

## Running for tests

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
