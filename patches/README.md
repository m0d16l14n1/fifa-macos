# Patches to the ReXGlue SDK

FIFA 19 runs on ReXGlue **v0.10.0** (`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`) with two layers of patches.
`scripts/sdk.sh` clones the SDK into `third_party/rexglue-sdk`, applies both in order, records each patch's
hash in `third_party/rexglue-sdk/.fifa-patches`, and builds and installs it. `scripts/sdk.sh --check` tells
whether a checkout still matches this folder.

| Folder | What | Order |
|---|---|---|
| `mcla/` | mcla-recomp's series at its commit `ef468c4` (2026-11-02): the native Metal backend, MetalFX, macOS audio threads, POSIX fixes and the rest (79 patches) | `mcla/series`, one per line; a second column is the submodule a patch applies in |
| `fifa/` | FIFA 19's own, on top | file name order (`git format-patch` numbering) |

## Why MCLA at `ef468c4`

That is the tree FIFA 19 was first ported on. Later mcla-recomp commits (Metal 4 by default, ray tracing,
shader inlining and others) are left out on purpose: they brought regressions. A later MCLA fix comes forward only
on its own, as a patch in `fifa/`, after it has been tested in FIFA.

## `fifa/`

| Patch | What and why |
|---|---|
| `0001` codegen fixes | From ReStreet (FIFA Street 2012, the same EA engine): `__savegprlr_N`/`__restgprlr_N` inlined; branch targets classified against the owning function's base (a shared tail can overlap another function's blocks); an external branch into another function's middle gets its own entry; a conditional branch out of a function calls the target and returns instead of returning silently; jump tables may dispatch to registered case functions; vector packs keep aliased sources. |
| `0002` registration loop | A module's registration walks `PPCFuncMappings` instead of one `SetFunction` call per function (CardsDLLzf's took clang over 30 minutes). |
| `0003` DLL loading | A recompiled DLL matches by file name when the game loads it by another path (`dlc\...\powdllzf.xex.dll`), and its library is `<exe folder>/lib<name>.dylib`. |
| `0004` `function_table_base` | A codegen config can move a module's indirect-call table. CardsDLLzf's (0x4271E8 bytes after 0x89330000) would cover powdllzf's image at 0x89700000; `config/cardsdll.toml` puts it at 0x87000000. The dispatcher checks images and tables of all modules against each other. |
| `0005` Metal | Volume (3D) textures, tiled or linear (FIFA's tone map grades colour through two 32³ LUTs: without them every match was black). Polygon offset (decals, pitch markings). `metal_resolve_into_textures`: a resolve that lands exactly on a mip level of a loaded texture is blitted into it (FIFA's 2048² downsample chain reloaded 8 MB+ per level). `metal_gpu_fences` writes a fence at once when no resolve came before it (`metal_gpu_fences_all` for every one on the GPU). `metal_present_upscale=metalfx`: MetalFX spatial upscaling to the window. `metal_hitch_log_ms`, `metal_stall_sample_ms`: slow-frame lines and a `sample` of every thread when frames stop. |
| `0006` install | The codegen tool, the Vulkan loader and MoltenVK are installed for RelWithDebInfo SDKs too (only Release had them, so a game built against a RelWithDebInfo SDK failed to configure, then to copy them). |
| `0007` present capture | A capture asked for during play (the dev pad's `shot`) can read the drawable: the layer is framebuffer-only only while nothing is captured. |
| `0008` resolves into textures | Generalizes 0005's resolve into mips: any loaded tiled 2D level at a resolve's address with the same pitch and format takes the resolve by a GPU blit at its offset (FIFA resolves into the corner of a 2048x2048 texture and into targets fetched at sizes that are not multiples of 8). Texture reloads in a match: 10 a frame to none. `metal_resolve_into_textures`, `_log`. |
| `0009` WAIT_REG_MEM polling | The command processor polled in sleeps of `wait/0x100` ms; it now yields 50 us, then sleeps `gpu_wait_poll_us` (100). Each CPU-to-GPU handoff cost a millisecond or more: a match went from 26-39 ms a frame to the 60 Hz cap. `gpu_wait_stats` logs where waits go. |
| `0010` access violation log | An unhandled guest access violation is logged 32 times, then once in 100000 with a count (a stuck guest faulted 10000 times a second and rotated the log away). |
| `0011` frame pacing | The stats line's frame-interval percentiles (p50/p95/p99/max, frames over 1.5x the median): choppiness in numbers. |
| `0012` thread priorities (macOS) | Threads are created QoS user-interactive; a guest priority is a Mach precedence, never `SCHED_FIFO`. The POSIX scale (normal = 16) as a fixed FIFO priority put the game's threads below every ordinary thread on the Mac (31). |
| `0013` WAIT_REG_MEM with vsync off | The short-sleep polling of 0009 also when uncapped (it spun, taking a core from the threads it waited for). |
| `0014` linear texture hashing | CPU-written (linear) textures are re-hashed at most every 8 ms (`metal_linear_hash_us`), not every guest frame: a 30 fps movie's planes were hashed 240 times a second at the 240 Hz pacing. |
| `0015` guest clock remainder | The guest time base (50 MHz) is advanced from the host's (24 MHz on Apple silicon) with the fraction carried between updates. Each update rounded down, and a game polling the clock in a spin lost part of a tick every read: 0.96 guest seconds per real second, so FIFA's 60 Hz vblank came every 17.07 ms and everything timed by the guest ran 4% slow. |
| `0016` multi-object waits | `WaitMultiple` (KeWaitForMultipleObjects, NtWaitForMultipleObjectsEx) takes a ticket on every event for its whole length, as single waits do, so an event set and reset (or pulsed) while it waits still releases it; `Pulse` releases the current waiters and leaves the event reset in one step (it was Set, 10 us, Reset); a multi-object wait sleeps on its own condition variable, woken by the objects it waits for (~14 us after a set instead of ~650 us). A lost pulse stuck one boot in 18 before the intro movie. Checked by `scripts/test_sdk.sh`. |
| `0017` precise vblank (off) | `gpu_vblank_precise`: the guest vblank worker sleeps to the next vblank instead of checking every 1+ ms (vblanks are up to a millisecond late). Experimental and off: one quiet 60 Hz match gave p99 16.8 ms (17.7 polled), a loaded machine missed more vblanks with it (BACKLOG P9). |
| `0018` cheaper cut-scenes | `metal_2x_as_1x`: MSAA 2x surfaces at one sample a pixel (FIFA's walk-out and replays draw their scene at 2x in two predicated tiles: 1280x1440 pixels shaded, a third of the GPU); `metal_linear_hash_max_us`: a linear texture found unchanged is hashed again less and less often, up to 100 ms (27 MB of static faces and kits hashed a frame before); a texture cache flush is logged. |
| `0019` burst capture | `metal_present_capture_burst`: the next N presented frames each captured (the dev pad's `burst`), for what shows for a frame or two. |
| `0020` display-synced vblank | `gpu_vblank_display_sync` (macOS): the guest vblank from a CoreVideo display link, one per display refresh, so each refresh shows the next game frame (FIFA's default; a 60 Hz match: none repeated or dropped, 16.66 ms +-0.37 a refresh). |
| `0021` temporal AA title profile | `temporal_aa_anchor_ps`, `temporal_aa_camera`: temporal AA for a title without guest markers. The scene is the MSAA 2x draws (jittered, predicated tiles included), the camera the view-projection in named vertex shaders' constants (last frame's kept), the pass runs before the anchor pixel shader with the frame's last depth resolve; Metal takes the depth map from the viewport and the scene's own colour format; `metal_taa_debug_vectors` shows the vectors. |
| `0022` frame generation without guest markers | `guest_marker_rules` (a title's tone map and UI by pixel shader), several temporal anchors, the camera from the scene's last matching draw, camera cuts from the cameras (`temporal_aa_debug 11` logs them), UI drawers with nothing to show (the achievement notifier between toasts) no longer hold generated frames back, and the Metal presenter generates frames only when they can be shown. |
| `0023` sharpening after temporal AA | `metal_taa_sharpness`: contrast-adaptive sharpening (AMD CAS's weights) of MetalFX's temporal output, which is soft at the native size. |

## Changing the SDK

Work in `third_party/rexglue-sdk`: the MCLA series is one commit tagged `mcla-base`, and FIFA's patches are
commits on branch `fifa` after it. Commit the change, then export the commits again:

```bash
rm patches/fifa/*.patch
git -C third_party/rexglue-sdk format-patch -q mcla-base..fifa -o "$PWD/patches/fifa"
```

A patch whose hash changed makes `scripts/sdk.sh` stop: delete `third_party/rexglue-sdk` and run it again to patch
afresh (or update `.fifa-patches` when the checkout already has the change).
