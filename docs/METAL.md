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

## Settings that matter

| Cvar | Default | What |
|---|---|---|
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
