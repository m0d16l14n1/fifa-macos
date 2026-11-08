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
| C7 | In some close cut-scene shots the stands are empty while a wide shot of the same stands is full (walk-out, 16 s in: `out/logs/walkout.txt` shot walk-c): the crowd's draws (VS 4136505AB17879F1, texture 1A71D000) are not submitted at all in that frame, the same in builds before 2026-11-08. Not occlusion queries or viz queries (none used). Find the crowd's culling in the game (who decides the crowd's draw list) | `crowdd` run, frame dumps of walk-c and walk-e | the crowd in every shot as on the console |

## Performance (M4)

| # | Item | Seen | Check |
|---|---|---|---|
| P5 | The main loop's step limiter (`sub_823686C0`, 1/200 s) spins a whole core (~97% of the main thread). A sleeping version (`src/native_frame_limiter.cpp`, `FIFA19_NATIVE_LIMITER=1`) makes another guest thread fault reading 0x1 in a loop: a race the spin's timing hides (seen with vsync off; a 4-minute run at the default 240 Hz pacing had no fault and no pacing gain). Find the racing thread (sample at the first fault) | sample of a match; limiter run | the hook on by default, no faults over a full match |
| P6 | Cut-scenes (walk-out, replays) run the game's own 25 ms minimum frame time and ~25 ms of command processor work (1,000-1,300 draws, ~70 resolves, ~100 render passes a frame): an even 30 FPS synced to a 60 Hz display. 60 needs the command processor near 16 ms there: texture lookups (`TextureSlow`, compose of the two scene tiles), encoder creation (many small passes), then lifting the game's 1/40 limiter | `walk*` runs, `scripts/sample_self.py` on a sample | 60 in the walk-out |
| P9 | The guest vblank worker checks the clock every 1+ ms, so vblanks are up to a millisecond late. `gpu_vblank_precise=true` (`patches/fifa/0017`) sleeps to each vblank: one quiet 60 Hz match p99 16.8 ms (17.7 polled); on a loaded machine (Spotlight indexing) 27 missed vblanks in 30 s against 13 polled and 9 for the build before the wait fix; at 240 Hz two alternating pairs split. Measure over several runs on a quiet machine before turning it on | `vb60`, `final60`, `base60` runs, 2026-11-07 | fewer missed vblanks than polled, over 3+ runs each |
| P10 | The heaviest moments of a match (replays) are the cut-scene path (P6) | | |
| P2 | GPU busy in menus is 4-9 ms, in the match 20+ ms of command buffer time a frame: find the passes (`metal_debug_profile` on a dumped frame) | tour log | GPU under 10 ms in a match |
| P3 | Command processor 4+ ms a frame in menus: profile with Instruments | tour log | |

## Audio, input (M3)

| # | Item | Check |
|---|---|---|
| A2 | Port LibertyRecomp's Core Audio driver (AUHAL, real-time thread, lock-free ring) without its GTA IV diagnostics; SDL as fallback. Only for latency now: the SDL path has no underruns (A1, D20) | lower latency, still no underruns |
| I1 | Controller hot-plug goes to pad one; DualSense/DualShock prompts where possible; rumble | plug/unplug mid-match |
| I2 | The launcher's Controls page edits the keyboard layout (`keybind_*` cvars) | |

## Temporal, frame generation, Metal 4 (M5, M6)

| # | Item |
|---|---|
| T8 | Frame generation: at some walk-out cuts one presented frame is a blend of the two shots (1 of 2 runs); either a cut still seen a frame late or the game's own dissolve. Bursts at the cuts with `temporal_aa_debug 11` | `cut3*` runs |
| T7 | The players' own motion in the vectors (their skinning with last frame's bone constants): not needed for the match camera (no trails on running players with temporal AA, 1:1 bursts), possibly for close cut-scene shots and frame generation | `tb1`, `wt*` bursts |
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
| D13 | Lost wakeups in multi-object waits (`patches/fifa/0016`): an event set and reset or pulsed between two polls of KeWaitForMultipleObjects was missed, and one boot in 18 stuck before the intro movie with the audio worker in such a wait. Multi-object waits are now registered on their events, Pulse is atomic, and they wake ~14 us after a set instead of ~650 us (`scripts/test_sdk.sh`); 15 boots since, all to the menu; matches at 60 Hz within the noise of the build before it | 2026-11-07 |
| D15 | Judder (seen as the crowd stuttering when the camera pans): the guest vblank on the display's refreshes (`gpu_vblank_display_sync`, `patches/fifa/0020`), FIFA's default. A match on a 60 Hz display: 60.0 frames shown a second, none repeated or dropped, each advancing 16.66 ms +-0.37 (uncapped at 240 Hz: ~80 FPS made, 12-24 ms a refresh). Measured from `present_log` with `scripts/present_stats.py` | 2026-11-08 |
| D16 | Cut-scenes cheaper (`patches/fifa/0018`): MSAA 2x drawn as 1x (the walk-out's scene tiles, a third of the GPU) and static linear textures hashed less (27 -> 5-8 MB a frame): the walk-out from 17-31 uneven FPS to an even 30 synced (P6 for 60) | 2026-11-08 |
| D17 | MetalFX temporal AA in FIFA (T1-T4): the scene, depth and camera found in a match frame (METAL.md), wired through the SDK's new title profile (`patches/fifa/0021`): `fifa19_temporal_aa` | 2026-11-08 |
| D18 | MetalFX frame interpolation in FIFA (T6): the cut-scenes (30 FPS) at 60 on a 60 Hz display, generated only when they can be shown; tone map and HUD marked by `guest_marker_rules`, cuts from the cameras, the notifier no longer counted as UI (`patches/fifa/0022`) | 2026-11-08 |
| D19 | MetalFX temporal AA no longer soft (T5): contrast-adaptive sharpening after it (`metal_taa_sharpness` 0.6, `patches/fifa/0023`): local contrast 11.2 against 10.4 without temporal AA, 5.2 before | 2026-11-08 |
| D20 | The SDL audio path measured (A1): no underruns in 8 runs (matches at 60 and uncapped, walk-outs, frame generation on), the underrun warnings of `sdl_audio_driver` silent | 2026-11-08 |
| D21 | Benchmark baseline (P4), M5 MacBook Air, `bench_mac.sh`, Kick Off, uncapped (`gpu_vblank_display_sync=false`), HUD on: 85.4 FPS (11.7 ms a frame, GPU busy 21.9 ms, CPU waiting 0.2 ms); with temporal AA 85.3 (no measurable cost: matches are bound by the command processor). The benchmark's pad script had a bad line that left it running; the dev pad now skips a failing line | 2026-11-08 |
| D9 | `cache:\` mounted (C1): `~/Library/Application Support/FIFA 19/cache-partition` | 2026-11-07 |
