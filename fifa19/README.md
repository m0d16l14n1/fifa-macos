# FIFA 19 (Xbox 360) on macOS, natively on Metal

A ReXGlue recompilation of the Xbox 360 FIFA 19 (title 454109F9), drawn with the native Metal backend from the
Midnight Club: Los Angeles port. It boots, goes through the menus and plays Kick Off matches at about 60 FPS on
an M5 (1280x720 internal, windowed).

Bring your own game: a Games on Demand package of FIFA 19. Neither the game nor its files are in this repository.

## Layout

| Path | What |
|---|---|
| `fifa19_manifest.toml` | default.xex plus the guest DLLs the game loads: CardsDLLzf (Ultimate Team), FootballCompEngzf and powdllzf (DLC) |
| `config/*.toml` | function boundary overrides for codegen (each pass is commented); `cardsdll.toml` also moves that DLL's dispatch table |
| `src/` | the app (`Fifa19App`), native memcpy/memset/memmove, XUsbcam stubs, the dev pad |
| `scripts/extract_god.py` | extracts a Games on Demand (SVOD) package, enhanced GDF layout included |
| `scripts/play_mac.sh` | runs the build, linking the SDK's GPU plugins next to it |
| `scripts/pad/kickoff.txt` | dev pad script: title screen to a Kick Off match |
| `scripts/pad/match.sh` | writes a dev pad script for a match with a given stadium, season, time of day and weather |
| `third_party/rexglue-sdk` | the SDK (not in git): MCLA's patched v0.10.0 tree plus the changes below |

## Building

1. Extract the game into `game/` (about 6.6 GB):
   ```bash
   python3 scripts/extract_god.py ../FIFA-19/454109F9/00007000/<package file> game
   ```
2. Build and install the SDK (RelWithDebInfo) in `third_party/rexglue-sdk`, as for MCLA. Then remove the
   `~/.cmake/packages/rexglue/` entry the install registers, so other projects don't find this SDK.
3. Generate the code (about 8 minutes) and build:
   ```bash
   third_party/rexglue-sdk/out/install/mac-arm64/bin/rexglue codegen fifa19_manifest.toml
   cmake --preset mac-arm64-relwithdebinfo && cmake --build out/build/mac-arm64-relwithdebinfo -j 8
   ```
   Later builds rerun codegen by themselves when a config or the game changes.

## Running

```bash
scripts/play_mac.sh --fullscreen=false
```

- `--fifa19_gpu_backend=metal` (default), `vulkan` (MoltenVK) or `any`.
- `FIFA19_METAL_HUD=1` shows Apple's Metal performance HUD; `FIFA19_METAL_VALIDATION=1` turns on the Metal
  validation layer; `FIFA19_LLDB=1` runs under lldb.
- `FIFA19_NATIVE_LIBC=0` turns off the native memcpy/memset/memmove.
- The log goes to `out/build/mac-arm64-relwithdebinfo/run.log`.

The first run shows the EA User Agreement and asks for a club; both are saved with the profile.

Defaults the app sets (each can still be changed in the config or on the command line):

- `metal_gpu_fences=true`. FIFA builds the pitch's shadow textures on the CPU at match load, from GPU resolves,
  as soon as the guest's fence says they are done. Fences the command processor wrote at once came before the
  GPU had done those resolves, so the pitch got dark bands, or went black, depending on load timing.
- `metal_present_upscale=metalfx`. The game draws 1280x720; MetalFX's spatial upscaler scales it to the
  window, sharper than bilinear (`bilinear` to compare). SDR output only.

## Controls

A controller works as is. The keyboard plays too, as pad one together with any controller. The layout follows
FIFA's keyboard-only Classic layout on PC: arrows move, and W/A/S/D are the four face buttons. The game shows
Xbox 360 button prompts; the pad column says which key that is.

| Key | Pad | In a match | In menus |
|---|---|---|---|
| Arrow keys | Left stick | Move | Move the highlight |
| S | A | Short pass / header; contain (hold) when defending | Accept |
| A | X | Lob pass / cross / header; slide tackle | |
| W | Y | Through ball; rush the goalkeeper out (hold) | |
| D | B | Shoot / volley / header; tackle, push or pull | Back |
| E | RT | Sprint | |
| Q | LB | Change player; chip shot (Q+D), lobbed through ball (Q+W), player run | Previous tab |
| C | RB | Finesse shot (C+D), driven pass (C+S); teammate contain (hold) | Next tab |
| Z | LT | Protect the ball, jockey, slow dribble | |
| Numpad 8/2/4/6, or I/K/J/L | Right stick | Skill moves | |
| T | Right stick press (R3) | Flick up for volley; cover far post (hold) | |
| F | Left stick press (L3) | | |
| Shift + arrow keys | D-pad | Team tactics (up: attacking, down: defending; left/right: game plan) | Move the highlight |
| Esc or Space | Start | Pause | "Press START" on the title screen |
| Enter | A | | Accept |
| Backspace | B | | Back |
| Tab | Back | | |

Notes:

- Combinations work as on a pad: hold the modifier key, then press the action key (C then D for a finesse shot).
- Holding Shift turns the arrow keys into the D-pad, so the player stops while Shift is down.
- The app keeps F3 (debug overlay), F4 (settings, which can change these keys), F7 and the backtick (console).
- Each key is a cvar with a comma-separated list of keys, e.g. `--keybind_right_trigger=E,R`.
  - The names are `keybind_a`, `_b`, `_x`, `_y`, `_left_shoulder`, `_right_shoulder`, `_left_trigger`,
    `_right_trigger`, `_lstick_up` (and `_down`, `_left`, `_right`, `_press`), the same for `_rstick_*` and
    `_dpad_*`, `_start` and `_back`.
  - A bind like `Shift+Up` needs exactly that modifier held, and a bind without one needs none held. So Shift,
    Ctrl and Alt can't be action keys by themselves.
- `--mnk_mode=false` turns the keyboard off. The mouse isn't used: `--mnk_mouse=true` makes it the right stick.

### Dev pad

A scripted controller for unattended runs, merged with any real pad:

- `--fifa19_pad_script=scripts/pad/kickoff.txt` runs a script.
- `scripts/pad/match.sh --stadium 3 --time 7 --weather 2 > match.txt` writes one for a match at another
  stadium, time of day or weather; its header lists the steps it knows.
- `--fifa19_pad_pipe=<path>` reads commands from a named pipe, e.g. `echo "press a" > <path>`.

Commands: `press`, `hold`, `down` and `up` for buttons, `trigger`, `stick`, `release`, `wait`, `log`, `quit`.
`set <cvar> <value>` changes a cvar while the game runs: `set metal_debug_capture true` dumps a frame's
resolves into `--metal_debug_dir`.

## SDK changes on top of MCLA's tree

- **Codegen fixes from ReStreet:** targets classified by function base, shared-tail entries, gprlr inline.
- **Function registration:** walks `PPCFuncMappings`. One call per function made a function clang needed
  over 30 minutes for.
- **DLL loading:**
  - Modules match by file name when the registry path differs (`dlc\...\powdllzf.xex.dll`).
  - On macOS the DLL is loaded as `lib<name>.dylib` from the executable's folder.
- **`function_table_base`** (codegen config): moves a module's indirect-call table away from its image.
  - CardsDLLzf's table (0x4271E8 bytes after 0x89330000) would cover powdllzf's image at 0x89700000, so it is
    at 0x87000000.
  - The module exports `ReXModule_GetFunctionTableBase` for the loader.
  - The runtime's overlap check covers images and tables separately.
- **Metal 3D textures:** volume textures load, tiled or linear. FIFA's tone map grades colour through two
  32x32x32 LUTs; sampled as zero, they left every match black.
- **Metal resolves into mip levels:** a resolve that lands exactly on the base or a mip of a loaded texture
  is copied into that level (`metal_resolve_into_mips`).
  - FIFA builds a 2048x2048 k_4_4_4_4 downsample chain level by level.
  - Before, each level dropped the texture and untiled 8 MB+ from memory: 31 ms of GPU a frame in a match,
    now 12 ms.
- **Metal GPU fences:** written by the command processor at once when no resolve came before them (none of
  FIFA's do; `metal_gpu_fences_all` writes every one on the GPU), and the per-frame stats line counts both.
- **MetalFX spatial upscaling at present** (`metal_present_upscale`).
- **Metal depth bias:** the polygon offset registers are applied, as the other backends do.
- **Diagnostics:** an `XexLoadImage` result log, and register state on an invalid indirect call.
- **Metal debug cvars:**
  - `metal_debug_constants` logs each draw's float constants.
  - `metal_debug_dump_address=<addr>` dumps the next resolve into that address.
  - `metal_debug_texture_address=<addr>` logs the draws that bind a texture and dumps it, with its guest bytes.
  - `metal_debug_white_address=<addr>` binds white in its place.

## Known issues

- `cache:` is not mounted. The SDK leaves it out on purpose, and the game carries on without it.
- MCLA's MetalFX temporal AA, upscaling and frame generation are not on. They read MCLA's camera matrices
  from its motion-blur shader. FIFA would need its own scene shader and constants found first.
- Online features, XeKeys, XamMediaVerification* and XHttp are stubs.
- Only Kick Off has been played through; Ultimate Team (CardsDLLzf) and the career modes are untested.
