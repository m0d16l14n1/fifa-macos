#!/bin/sh
# Starts the macOS build of FIFA 19 from a terminal, windowed, with a log (run.log in the build folder; the ten
# before it in logs/). Options go to fifa19 (for example --fifa19_gpu_backend=vulkan, --log_level=debug).
#
#   FIFA19_BUILD=release       the build folder (default relwithdebinfo: out/build/mac-arm64-relwithdebinfo)
#   FIFA19_BACKGROUND=1        a window that never takes focus or the Dock (unattended runs on a Mac in use)
#   FIFA19_METAL_HUD=0         no Metal performance HUD (on by default)
#   FIFA19_METAL_VALIDATION=1  Metal API validation (slow; for rendering bugs)
#   FIFA19_LLDB=1              under lldb (stops at the first crash; 'bt all' for every thread)
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$root/out/build/mac-arm64-${FIFA19_BUILD:-relwithdebinfo}"

if [ ! -x "$build/fifa19" ]; then
  echo "error: $build/fifa19 not found; build it first (bash scripts/make_mac.sh)" >&2
  exit 1
fi
cd "$build"

# The SDK loads GPU plugins from the executable's folder only; the build copies the runtime there but not the
# plugins (librexgpu-xenos.dylib, "rd" before the dot for a RelWithDebInfo SDK).
for lib in "$root"/third_party/rexglue-sdk/out/install/mac-arm64/lib/librexgpu-*.dylib; do
  [ -e "$lib" ] && ln -sf "$lib" .
done

[ "${FIFA19_METAL_HUD:-1}" != 0 ] && export MTL_HUD_ENABLED=1
[ -n "$FIFA19_METAL_VALIDATION" ] && export MTL_DEBUG_LAYER=1 METAL_DEVICE_WRAPPER_TYPE=1
if [ -n "$FIFA19_BACKGROUND" ]; then
  # SDL: no activation, no Dock icon, and windows shown without taking focus.
  export SDL_MAC_BACKGROUND_APP=1 SDL_WINDOW_ACTIVATE_WHEN_SHOWN=0
fi

# The SDK's command line parser fails on a repeated option, so defaults are added only when not given.
has() { case " $ARGS " in *" --$1="*) return 0 ;; esac; return 1; }
ARGS="$*"
has log_level || set -- --log_level=info "$@"
has fullscreen || set -- --fullscreen=false "$@"
if ! has log_file; then
  set -- --log_file=run.log "$@"
  if [ -f run.log ]; then
    mkdir -p logs
    mv run.log "logs/run-$(date -r run.log +%Y%m%d-%H%M%S).log"
    ls -t logs/run-*.log | tail -n +11 | while read -r old; do rm -f "$old"; done
  fi
fi
if [ -n "$FIFA19_LLDB" ]; then
  exec lldb -o run -- ./fifa19 "$@"
fi
exec ./fifa19 "$@"
