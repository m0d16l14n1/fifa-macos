# Backlog

Numbered for reference in commits; grouped by milestone ([PLAN.md](PLAN.md)). Each item says how it was seen and
how it is checked. Done items move to the end with their date.

## Correctness (M1, M2)

| # | Item | Seen | Check |
|---|---|---|---|
| C1 | `cache:` is not mounted: the game's `cache:\replay0.bin` fails to open (instant replays and highlights may need it). Mount it on `~/Library/Application Support/FIFA 19/cache-device` | every boot log (`ResolvePath(cache:\) failed`) | a replay in a match plays; no ResolvePath error |
| C2 | Every mode toured with shots: Kick Off is mapped; Career, Ultimate Team (CardsDLLzf), Tournaments, Skill Games, Women's, Champions League not yet | | `tour.txt` per mode, pictures compared |
| C3 | Stadium × time of day × weather matrix (`scripts/pad/match.sh`): shadows, rain, snow, night lighting | | a shot per combination |
| C4 | Intro and in-game movies: frame rate, audio-video sync, no tearing or stalls | | M2 measurements |
| C5 | `Presenter: UI overlay painting isn't available with this graphics backend` at start: the presenter's separate UI layer (for frame generation) has no Metal implementation; the F3/F4 overlays still draw over the picture. Needed for T5 | every boot log | F3/F4 visible in a shot; the line gone once T5 lands |
| C6 | `gamecontrollerdb.txt` missing: SDL's built-in mappings are used; ship the community database for unusual pads | every boot log | a third-party pad maps right |

## Performance (M4)

| # | Item | Seen | Check |
|---|---|---|---|
| P1 | Frames average 17.3 ms (57.8 FPS), not 16.7 at a 60 Hz display: pacing loses about one frame in 30 | `Metal frame time` lines in menus and matches | 16.7 ms average, even cadence (HUD frame graph flat) |
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
