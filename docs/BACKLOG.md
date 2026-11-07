# Backlog

Numbered for reference in commits; grouped by milestone ([PLAN.md](PLAN.md)). Each item says how it was seen and
how it is checked. Done items move to the end with their date.

## Correctness (M1, M2)

| # | Item | Seen | Check |
|---|---|---|---|
| C2 | Every mode toured with shots: Kick Off is mapped; Career, Ultimate Team (CardsDLLzf), Tournaments, Skill Games, Women's, Champions League not yet | | `tour.txt` per mode, pictures compared |
| C3 | Stadium × time of day × weather matrix (`scripts/pad/match.sh`): shadows, rain, snow, night lighting | | a shot per combination |
| C5 | `Presenter: UI overlay painting isn't available with this graphics backend` at start: the presenter's separate UI layer (for frame generation) has no Metal implementation; the F3/F4 overlays still draw over the picture. Needed for T5 | every boot log | F3/F4 visible in a shot; the line gone once T5 lands |
| C6 | `gamecontrollerdb.txt` missing: SDL's built-in mappings are used; ship the community database for unusual pads | every boot log | a third-party pad maps right |

## Performance (M4)

| # | Item | Seen | Check |
|---|---|---|---|
| P5 | The main loop's step limiter (`sub_823686C0`, 1/200 s) spins a whole core (~97% of the main thread). A sleeping version (`src/native_frame_limiter.cpp`, `FIFA19_NATIVE_LIMITER=1`) makes another guest thread fault reading 0x1 in a loop: a race the spin's timing hides (seen with vsync off; a 4-minute run at the default 240 Hz pacing had no fault and no pacing gain). Find the racing thread (sample at the first fault) | sample of a match; limiter run | the hook on by default, no faults over a full match |
| P6 | Walk-out and other cut-scenes run the game's own 1/40 s limiter (25 ms steps) and heavier frames: 25-40 ms there | tour pacing lines, `fifa19_limiter_stats` | decide whether to lift the cut-scene cap when uncapped |
| P7 | Uncapped matches still show 3-36 frames in 5 s over 1.5x the median (p99 17-32 ms at a 12 ms median) | tour pacing lines | p99 under 1.5x the median |
| P10 | Some match sequences (seen 2026-11-07, 30 s into the scripted match: a replay or set piece) go to 82 resolves a frame and ~59 ms of GPU time: 17-25 FPS for 10 s. Find the scene and its passes (`metal_debug_frame` there) | `wf240` run | 60 FPS through it |
| P2 | GPU busy in menus is 4-9 ms, in the match 20+ ms of command buffer time a frame: find the passes (`metal_debug_profile` on a dumped frame) | tour log | GPU under 10 ms in a match |
| P3 | Command processor 4+ ms a frame in menus: profile with Instruments | tour log | |
| P4 | Benchmark baseline per build (`bench_mac.sh`, HUD on) | | numbers in this file |

## Audio, input (M3)

| # | Item | Check |
|---|---|---|
| A1 | Measure the SDL audio path in a match and in movies (`--audio_stats=true`): underruns, queue depth | no underruns in 10 min |
| A2 | Port LibertyRecomp's Core Audio driver (AUHAL, real-time thread, lock-free ring) without its GTA IV diagnostics; SDL as fallback | A1 numbers equal or better, lower latency |
| I1 | Controller hot-plug goes to pad one; DualSense/DualShock prompts where possible; rumble | plug/unplug mid-match |
| I2 | The launcher's Controls page edits the keyboard layout (`keybind_*` cvars) | |

## Temporal, frame generation, Metal 4 (M5, M6)

| # | Item |
|---|---|
| T1 | Locate the match's scene colour before UI and post effects (shader hash of the tone map or bloom composite) |
| T2 | Locate the scene depth and its format at that point |
| T3 | Locate the camera: view-projection this frame and last, jitter if any (constant logs of the scene shaders) |
| T4 | Wire T1-T3 into the backend's temporal path (as MCLA's motion-blur hook), behind `fifa19_temporal` |
| T5 | MetalFX temporal AA; then frame interpolation (macOS 26), UI drawn apart |
| R1 | A higher internal resolution than 1280x720 (EDRAM scaling) before any upscaler work |
| M1 | Metal 4 path beside Metal 3 (PLAN M6) |

## Done

| # | Item | Date |
|---|---|---|
| D1 | ReStreet tree removed; FIFA 19 at the repository root | 2026-11-07 |
| D2 | SDK reproducible from patches (MCLA `ef468c4` + `patches/fifa`), checked by `sdk.sh --check` | 2026-11-07 |
| D3 | FIFA's lost SDK changes rebuilt: codegen fixes, DLL loading, `function_table_base`, 3D textures, depth bias, resolves into mips, fences, MetalFX spatial present, stall reports | 2026-11-07 |
| D4 | In-process shots during play (presenter switches the layer off framebuffer-only while capturing) | 2026-11-07 |
| D5 | Settings, saves and caches in Application Support (old `~/.local/share/fifa19` moved) | 2026-11-07 |
| D6 | Match performance: resolves into loaded textures (texture reloads 10 a frame -> 0) and WAIT_REG_MEM polling in 100 us sleeps (each CPU-GPU handoff cost 1+ ms): a Kick Off match from 26-39 ms a frame to the 60 Hz cap | 2026-11-07 |
| D7 | Smoothness: latency-critical process activity, QoS user-interactive threads (guest priorities had been fixed below every other thread), polite polling when uncapped | 2026-11-07 |
| D8 | Uncapped by default as 240 Hz vblank pacing: ~80 FPS in a match, ~115 in menus, even frames; the match clock runs at the same rate as at 60 Hz (73 game seconds per 10 s, measured both ways) | 2026-11-07 |
| D10 | Movies play in real time at the 240 Hz pacing (C4): the boot intro (VP6, 245 frames at 30 fps, 8.17 s) ran 8.2-8.5 s at 240 Hz and at 60 Hz, timed by its per-frame plane hashing in the Metal stats on a first boot | 2026-11-07 |
| D11 | Linear (movie) textures re-hashed at most every 8 ms instead of every frame (P8): 3.4 -> 1.6 MB a frame while the intro plays at 240 Hz; the movie still plays right | 2026-11-07 |
| D12 | The guest clock ran 4% slow (P1): each update rounded its 24 MHz to 50 MHz conversion down, and the game reads the clock in a spin. With the remainder kept (`patches/fifa/0015`), 60 Hz is 60.0 FPS (p50 16.67 ms, was 58.6 FPS at 17.07) and everything timed by the guest runs at real speed | 2026-11-07 |
| D13 | Lost wakeups in multi-object waits (`patches/fifa/0016`): an event set and reset or pulsed between two polls of KeWaitForMultipleObjects was missed, and one boot in 18 stuck before the intro movie with the audio worker in such a wait. Multi-object waits are now registered on their events, Pulse is atomic, and they wake ~14 us after a set instead of ~650 us (`scripts/test_sdk.sh`); 10 boots since, all to the menu | 2026-11-07 |
| D14 | The guest vblank on time (P9, `patches/fifa/0017`, `gpu_vblank_precise`): the worker sleeps to the next vblank instead of checking every 1+ ms; a 60 Hz match's p99 17.0 ms (was 17.7). At 240 Hz no difference measurable over the noise of a loaded machine (two alternating pairs split) | 2026-11-07 |
| D9 | `cache:\` mounted (C1): `~/Library/Application Support/FIFA 19/cache-partition` | 2026-11-07 |
