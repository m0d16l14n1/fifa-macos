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

## Changing the SDK

Work in `third_party/rexglue-sdk`: the MCLA series is one commit tagged `mcla-base`, and FIFA's patches are
commits on branch `fifa` after it. Commit the change, then export the commits again:

```bash
rm patches/fifa/*.patch
git -C third_party/rexglue-sdk format-patch -q mcla-base..fifa -o "$PWD/patches/fifa"
```

A patch whose hash changed makes `scripts/sdk.sh` stop: delete `third_party/rexglue-sdk` and run it again to patch
afresh (or update `.fifa-patches` when the checkout already has the change).
