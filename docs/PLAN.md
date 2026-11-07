# Plan: FIFA 19 on macOS, start to end

Offline play only: no online, no multiplayer services (EA's servers are gone; online features stay stubs).
Priorities, in order: **no bugs**, **performance** (a locked 60 FPS in matches with headroom), then features.
Each milestone ends with its checks passing in a background test run (`scripts/pad/tour.txt`, the benchmark)
and the docs updated.

## M0: a clean, reproducible base (done 2026-11-07)

- Repository is FIFA 19 only: ReStreet's Windows installer, launchers, viewer and CI removed.
- SDK from patches: ReXGlue v0.10.0 + mcla-recomp at `ef468c4` + FIFA's patches (`scripts/sdk.sh`, hash records,
  `--check`); the FIFA changes that only lived in a lost SDK copy are rebuilt as `patches/fifa/0001-0007`.
- One-command build (`scripts/make_mac.sh`), run (`play_mac.sh`), benchmark (`bench_mac.sh`), cleanup
  (`clean.sh`), in-process screenshots (dev pad `shot`, `ppm2png.py`).
- Settings, saves and caches in `~/Library/Application Support/FIFA 19`; the SwiftUI launcher and `FIFA 19.app`.
- Test runs as background windows that never take focus; Metal HUD on.

## M1: every screen correct (bug mapping)

Goal: the intro movies, every menu, team management, loading screens, all stadiums, times of day and weathers,
replays and cut-scenes look as on the console, without hitches.

1. Tour each mode with shots (`tour.txt`, `match.sh` for stadium × time × weather) and keep the pictures per
   build in `out/shots/<build>/` for comparison.
2. Every wrong picture gets a BACKLOG item with its shot, the frame's `metal_debug_frame` log and the texture or
   shader involved.
3. Fix in the backend (format, resolve, blend, depth) or in the game (a hook), smallest correct change first.

## M2: video and cut-scenes

Goal: the EA intro and every in-game movie at their own frame rate, in sync with sound, no stutter.

1. Measure: movie frame times and audio-video drift (dev pad marks at known movie frames; `audio_stats`).
2. Movies are CPU-written linear textures (hashed once a frame, `metal_hash_linear_textures`): check each
   plane loads every frame it changes and no more.
3. Present interval: movies and replays may ask for a 2-vblank interval (FIFA Street did); measure FIFA's and
   keep the cadence even (no 1-2-1-3 vblank judder).

## M3: native audio and controllers

1. Audio: measure the SDL path first (underruns, latency, XMA decoder load with `audio_stats`). Port
   LibertyRecomp's Core Audio driver (an AUHAL output on a real-time thread, a lock-free block ring, silence that
   keeps the guest's clock) without its GTA IV diagnostics; keep SDL as the fallback (`audio_driver=sdl`).
2. Controllers: Game Controller framework devices through SDL already work (Xbox, DualSense, DualShock 4,
   Switch Pro). Add: hot-plug to pad one, the Xbox button prompts mapped for PlayStation pads where the game
   allows, rumble, DualSense light bar off/team colour.
3. Keyboard and mouse: already the Classic keyboard layout; the launcher's Controls page edits the keys.

## M4: performance (in progress: matches went from 26-39 ms to ~12 ms a frame uncapped, see METAL.md)

Goal: 60 FPS held in the heaviest match (rain, night, full stadium) with the GPU under 10 ms and the command
processor under 8 ms, on an M-series base chip.

1. `bench_mac.sh` baselines per build (HUD on, same thermal state); a regression stops a merge.
2. CPU: profile the command processor and the guest's hot functions (Instruments Time Profiler on a match);
   native hooks for the hottest guest routines (as memcpy/memset/memmove).
3. GPU: resolves and texture loads per frame from the stats line; pass merging; fewer render-target transfers.
4. Pacing: frames at exactly the display's 60 Hz cadence (today 17.3 ms a frame on average).

## M5: MetalFX temporal and frame interpolation

1. Find FIFA's match renderer: the scene colour before UI and post effects, its depth, the camera matrices and
   jitter (shader dumps by hash, constant logs). BACKLOG T1-T4.
2. MetalFX temporal AA, then temporal upscaling (render below 1280x720 internally? only if the game's own
   resolution can be raised: higher internal resolution first, BACKLOG R1).
3. MetalFX frame interpolation (macOS 26): generated frames between the game's, the UI drawn apart, pacing on
   the present thread; off by default until it is clean in motion.

## M6: Metal 4

A Metal 4 path (`MTL4CommandQueue`, command allocators, argument tables, residency sets, `MTL4FX` scalers) beside
the Metal 3 one, chosen at start, built step by step and measured against it; it replaces Metal 3 only when it is
both faster and bug-for-bug equal in the tour.

## M7: release quality

Launcher polish (first-run setup from a package, settings with the game's defaults, a log viewer), the app's icon,
crash reports in the log folder, documentation for players, and a clean-machine build from `make_mac.sh`.
