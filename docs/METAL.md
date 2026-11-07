# The Metal backend

FIFA 19 is drawn by the SDK's native Xenos-on-Metal backend (`src/graphics/metal` in the SDK, from mcla-recomp's
`rexglue-metal-backend.patch`, plus FIFA's `patches/fifa/0005`). MoltenVK is still there for comparison
(`--fifa19_gpu_backend=vulkan`).

## How a frame goes

1. **The guest's command buffer** (PM4 packets) is read by the command processor thread (`MetalCommandProcessor`).
   Register writes go to the register file; draws, resolves and fence writes go to `MetalDraw`.
2. **Shaders**: each Xenos microcode shader is translated to MSL once (`metal_shader_translator.cpp`), kept in the
   shader storage (`~/Library/Application Support/FIFA 19/cache/shaders/metal/`) and compiled on worker threads;
   pipelines are kept in the pipeline storage, so a second run compiles almost nothing.
3. **EDRAM**: render targets are Metal textures keyed by their EDRAM base, format and pitch. MSAA 4x is drawn at one
   sample a pixel (`metal_4x_as_1x`), the way FIFA's 720p targets fit.
4. **Textures** are untiled on the GPU straight from guest memory (a no-copy buffer over the 512 MB), by a compute
   kernel, then blitted. A texture is kept until a CPU write (write watch) or a resolve over its memory drops it.
5. **Resolves** (EDRAM to memory) run as compute kernels that write guest memory on the GPU, and keep their own
   texture for a fetch of exactly what they wrote.
6. **Present**: the guest's front buffer is the guest output texture; the presenter scales it to the window
   (MetalFX spatial, or bilinear) and draws the ImGui overlays on top.

## FIFA 19's own changes

| Change | Why |
|---|---|
| Volume textures (tiled with the Xenos 3D tiling, or linear) into `MTLTextureType3D` | the tone map grades colour through two 32x32x32 LUTs; without them every match was black |
| Polygon offset | the pitch markings and decals over the grass |
| `metal_resolve_into_textures` | FIFA builds a 2048x2048 k_4_4_4_4 downsample chain level by level; each level's resolve dropped the texture and reloaded it (8 MB+ untiled), 31 ms of GPU a frame in a match before, 12 after (first port's measurement) |
| `metal_gpu_fences` (FIFA default on), written at once when no resolve preceded | the pitch's shadow textures are baked on the CPU from GPU resolves once the guest's fence says so: a fence written early gave dark bands or a black pitch |
| `metal_present_upscale=metalfx` (FIFA default) | the game draws 1280x720; MetalFX's spatial scaler is sharper than bilinear on a Retina window |
| `metal_hitch_log_ms`, `metal_stall_sample_ms` | a line per slow frame; every thread's stack when frames stop |

## Frame rate and pacing

Measured on an M5 MacBook Air, Kick Off match, background window, Metal HUD on (2026-11-07):

| Mode | Settings | Match | Menus | Even? |
|---|---|---|---|---|
| Uncapped (default) | `video_mode_refresh_rate=240`, `vsync=true` | ~80 FPS (p50 12 ms) | ~115 FPS | yes: frames on a 4 ms grid |
| Console | `video_mode_refresh_rate=60` | 60.0 FPS (p50 16.67 ms, p99 17.7 ms) | 60 | yes (vblanks up to 1 ms late: BACKLOG P9) |
| Unlimited | `vsync=false` (the guest's vblank every 1 ms) | ~85-90 FPS | | no: p95 17-19 ms at an 11 ms median |

The game paces its frames by the guest's vblank interrupt, so raising that clock is the smooth way to uncap it.
FIFA's simulation is time-based: the match clock runs 73 game seconds per 10 s at 60 and at 240 Hz alike.
The guest clock is exact since `patches/fifa/0015`: before it, each read rounded down and the game, which reads
the clock in a spin, ran 4% slow (60 Hz frames every 17.07 ms, movies 8.5 s for 8.17).
The presenter still shows whole frames in step with the display (no tearing).

What made matches fast (from 26-39 ms a frame before):

- **Resolves into loaded textures** (`metal_resolve_into_textures`): the game resolves into the corner of a 2048x2048
  texture and into targets fetched at sizes that are not multiples of 8; each resolve dropped the texture and the
  next fetch untiled it again (10 loads, 8 MB+, a frame). Now the resolve is blitted into the texture.
- **WAIT_REG_MEM polling** (`gpu_wait_poll_us`, 100): the command processor slept whole milliseconds while the
  render thread spun on its D3D fence, several times a frame.
- **Scheduling**: a latency-critical process activity, QoS user-interactive threads, and guest priorities as Mach
  precedence instead of a fixed `SCHED_FIFO` priority below every other thread.

`gpu_wait_stats`, `fifa19_limiter_stats` and the `Metal frame pacing` line (p50/p95/p99/max) show where time goes.

## Settings that matter

| Cvar | Default | What |
|---|---|---|
| `video_mode_refresh_rate` | 240 (FIFA) | the guest's vblank clock: 240 uncapped, 60 as on the console |
| `vsync` | on | off: the vblank every millisecond (unlimited, uneven) |
| `gpu_wait_poll_us` | 100 | WAIT_REG_MEM polling interval after 50 us of yielding |
| `metal_present_upscale` | `metalfx` | `bilinear` to compare |
| `metal_gpu_fences` / `metal_gpu_fences_all` | on / off | see above |
| `metal_resolve_into_textures` | on | off: every resolve drops what it overlaps |
| `metal_texture_mips` | on | the fetch's mip levels and anisotropic filtering |
| `metal_4x_as_1x` | on | MSAA 4x surfaces at one sample a pixel |
| `metal_shader_storage`, `metal_pipeline_storage`, `metal_async_compile` | on | no compile hitches after the first run |
| `metal_hitch_log_ms` | 250 | |
| `metal_stall_sample_ms` | 2000 (FIFA) | 0 off |
| `metal_debug_frame=<n>` | | everything about frame n in the log |

## Metal 3, Metal 4 and MetalFX: where things stand

| Feature | State in FIFA 19 |
|---|---|
| Metal 3 renderer (command buffers, render/compute/blit encoders, no-copy guest memory, shader/pipeline storage) | in use |
| MetalFX **spatial** upscaling at present | in use (FIFA's patch) |
| MetalFX **temporal** AA / upscaling (`MTLFXTemporalScaler`) | in the backend, keyed to MCLA's motion-blur shader for its camera matrices and depth: **not active in FIFA** until FIFA's scene pass, depth and camera constants are found (BACKLOG) |
| MetalFX **frame interpolation** (`MTLFXFrameInterpolator`, macOS 26) | in the backend, needs the temporal path (motion vectors, depth) and the UI drawn apart: **not active in FIFA** (BACKLOG) |
| HDR (EDR, HDR10 metadata) | in the backend, needs FIFA's tone map located (BACKLOG) |
| Metal 4 (`MTL4CommandQueue`, argument tables, residency sets, `MTL4FX`) | **not in this base**: MCLA's Metal 4 work came after `ef468c4` and is left out; planned again from scratch for FIFA (PLAN, M6) |

The temporal and frame-generation paths need three things from the game, per frame: the scene colour before
the UI and post effects, its depth, and the camera (this frame's and last frame's view-projection, and the jitter
if any). For MCLA those come from its motion-blur pass. For FIFA they are to be found by reverse engineering the
match renderer (`docs/DEBUGGING.md`: shader dumps by hash, `metal_debug_frame` texture lists); BACKLOG items T1-T4
track it.
