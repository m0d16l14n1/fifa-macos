# FIFA 19 for macOS

The Xbox 360 FIFA 19 (title 454109F9), statically recompiled with [ReXGlue](https://github.com/rexglue/rexglue-sdk)
and drawn natively with Metal on Apple silicon. It boots, goes through the menus and plays Kick Off matches
uncapped (about 80 FPS in a match on an M5 MacBook Air, evenly paced) in a window, with MetalFX upscaling to the
window's size.

**Bring your own game**: a Games on Demand package of FIFA 19. Nothing of the game is in this repository.
Offline play only.

## Quick start

```bash
bash scripts/make_mac.sh --god /path/to/454109F9/00007000/<package file>
open "out/FIFA 19.app"            # the launcher; or: sh scripts/play_mac.sh
```

The first build takes about an hour (the SDK once, then the game); [docs/BUILDING.md](docs/BUILDING.md) has the
details. The first run shows the EA User Agreement and asks for a club; both are saved with the profile in
`~/Library/Application Support/FIFA 19`.

## Documentation

| | |
|---|---|
| [docs/BUILDING.md](docs/BUILDING.md) | building, what is where, cleaning |
| [docs/METAL.md](docs/METAL.md) | the Metal backend, FIFA's changes to it, MetalFX and Metal 4 status |
| [docs/DEBUGGING.md](docs/DEBUGGING.md) | test runs, the dev pad, screenshots, logs, stall reports, reverse engineering |
| [docs/PLAN.md](docs/PLAN.md) | milestones from here to a release |
| [docs/BACKLOG.md](docs/BACKLOG.md) | known issues and work items |
| [patches/README.md](patches/README.md) | the SDK's patches |
| [launcher/mac/README.md](launcher/mac/README.md) | the launcher |

## Running

`sh scripts/play_mac.sh` starts the build in a window, with the Metal HUD and a log (`run.log` in the build folder).
`FIFA19_BACKGROUND=1` keeps the window from ever taking focus (test runs on a Mac in use). Options go to the game,
for example `--fifa19_gpu_backend=vulkan` (MoltenVK, for comparison), `--fullscreen=true`,
`--metal_present_upscale=bilinear`.

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

## Status

- Kick Off matches play uncapped at about 80 FPS on an M5 MacBook Air (menus about 115); `--video_mode_refresh_rate=60`
  holds the console's 60. Other modes are untested (BACKLOG C2).
- MetalFX spatial upscaling is on; temporal AA, temporal upscaling and frame interpolation wait for FIFA's camera
  and depth to be found (BACKLOG T1-T5). Metal 4 is planned (PLAN M6).
- Online features, XeKeys, media verification and XHttp are stubs.

## Licence

MIT for this project's own code; the SDK patches are GPL-3.0-or-later. See [licenses/](licenses/README.md) and
[CREDITS.md](CREDITS.md). FIFA and EA SPORTS are trademarks of Electronic Arts; this project is not affiliated
with or endorsed by EA or Microsoft.
