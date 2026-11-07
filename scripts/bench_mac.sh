#!/bin/sh
# Match frame-rate benchmark on macOS: one run per variant, each a fresh start that a dev pad script drives into
# a Kick Off match (scripts/pad/bench-match.txt) and measures for about 30 s of play. Each variant is a quoted
# list of options for fifa19; "" is the baseline.
#
#   sh scripts/bench_mac.sh "" "--metal_resolve_into_mips=false" "--metal_present_upscale=bilinear"
#
# The game runs as a background window (never takes focus) with the Metal HUD on, as in every test run.
# Prints one line per variant: frames per second, GPU busy and CPU wait per frame, and the thermal pressure at
# the start (a warm Mac moves the game to slower cores; compare runs at the same pressure). Results:
# out/bench/<n>.log, out/bench/<n>.png (the picture at the end).
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$root/out/build/mac-arm64-${FIFA19_BUILD:-relwithdebinfo}"
out="$root/out/bench"; mkdir -p "$out"
n=0
for variant in "$@"; do
  n=$((n + 1))
  thermal=$(notifyutil -g com.apple.system.thermalpressurelevel 2>/dev/null | awk '{print $2}')
  rm -f "$build/shots/bench.ppm"
  # shellcheck disable=SC2086 # the variant is a list of options
  FIFA19_BACKGROUND=1 sh "$root/scripts/play_mac.sh" --log_file=bench.log \
    --fifa19_window_title="FIFA 19 (benchmark run $n)" \
    --fifa19_pad_script="$root/scripts/pad/bench-match.txt" $variant > "$out/$n.stdout" 2>&1 || true
  cp "$build/bench.log" "$out/$n.log"
  [ -f "$build/shots/bench.ppm" ] && python3 -I "$root/scripts/ppm2png.py" "$build/shots/bench.ppm" > /dev/null &&
    mv "$build/shots/bench.png" "$out/$n.png"
  python3 -I - "$out/$n.log" "$n" "${variant:-baseline}" "${thermal:-?}" <<'PY'
import re, sys
log, n, variant, thermal = sys.argv[1:]
inside, frames, gpu, wait = False, [], [], []
for line in open(log, errors='replace'):
    if 'dev pad: bench_start' in line: inside = True
    elif 'dev pad: bench_end' in line: inside = False
    elif inside and 'Metal frame time:' in line:
        m = re.search(r'Metal frame time: ([\d.]+) ms a frame, GPU busy ([\d.]+) ms, CPU waiting for the GPU ([\d.]+) ms', line)
        if m: frames.append(float(m[1])); gpu.append(float(m[2])); wait.append(float(m[3]))
if frames:
    ms = sum(frames) / len(frames)
    print(f"{n}: {1000 / ms:.1f} FPS ({ms:.2f} ms a frame, GPU busy {sum(gpu) / len(gpu):.2f} ms, "
          f"CPU waiting {sum(wait) / len(wait):.2f} ms; {len(frames) * 150} frames)  [{variant}]  thermal {thermal}")
else:
    print(f"{n}: no result (the script did not reach the measured part; see out/bench/{n}.log)  [{variant}]")
PY
done
