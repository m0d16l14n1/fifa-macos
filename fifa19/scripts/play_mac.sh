#!/bin/sh
# Starts the macOS build of FIFA 19 from a terminal, with a log (run.log in the build folder). Options are
# passed on to fifa19 (for example --fullscreen=false, --fifa19_gpu_backend=vulkan, --log_level=debug).
# FIFA19_BUILD picks the build folder (default relwithdebinfo).
#
#   FIFA19_LLDB=1      start under lldb (break on the first crash; 'bt all' for every thread)
#   FIFA19_METAL_HUD=1 Apple's Metal performance HUD over the game
#   FIFA19_METAL_VALIDATION=1  Metal API validation (slow; for rendering bugs)
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$root/out/build/mac-arm64-${FIFA19_BUILD:-relwithdebinfo}"

if [ ! -x "$build/fifa19" ]; then
  echo "error: $build/fifa19 not found; build it first (bash scripts/make_mac.sh)" >&2
  exit 1
fi
cd "$build"

# The SDK loads GPU plugins from the executable's folder only, and the build copies the runtime there but
# not the plugins (librexgpu-xenos.dylib, with "rd" before the dot for a RelWithDebInfo SDK).
sdk_lib="$root/third_party/rexglue-sdk/out/install/mac-arm64/lib"
for lib in "$sdk_lib"/librexgpu-*.dylib; do
  [ -e "$lib" ] || continue
  ln -sf "$lib" .
done

[ -n "$FIFA19_METAL_HUD" ] && export MTL_HUD_ENABLED=1
[ -n "$FIFA19_METAL_VALIDATION" ] && export MTL_DEBUG_LAYER=1 METAL_DEVICE_WRAPPER_TYPE=1

# The SDK's command line parser fails on a repeated option, so defaults are added only when not given.
case " $* " in *" --log_level="*) ;; *) set -- --log_level=info "$@" ;; esac
# The last run's log is kept in logs/ (ten of them), since each run starts run.log again.
case " $* " in *" --log_file="*) ;; *)
  set -- --log_file=run.log "$@"
  if [ -f run.log ]; then
    mkdir -p logs
    mv run.log "logs/run-$(date -r run.log +%Y%m%d-%H%M%S).log"
    ls -t logs/run-*.log | tail -n +11 | while read -r old; do rm -f "$old"; done
  fi ;;
esac
if [ -n "$FIFA19_LLDB" ]; then
  exec lldb -o run -- ./fifa19 "$@"
fi
exec ./fifa19 "$@"
