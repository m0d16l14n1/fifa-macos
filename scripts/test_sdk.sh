#!/usr/bin/env bash
# Runs the SDK checks in tests/sdk against the installed SDK (third_party/rexglue-sdk/out/install/mac-arm64):
# small programs on the runtime library for behaviour the game depends on and the SDK's own tests don't cover.
#
#   bash scripts/test_sdk.sh
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
sdk=$repo/third_party/rexglue-sdk/out/install/mac-arm64
out=$repo/out/tests
[ -d "$sdk/lib" ] || { echo "test_sdk.sh: no installed SDK in $sdk (bash scripts/sdk.sh first)" >&2; exit 1; }
mkdir -p "$out"
status=0
for src in "$repo"/tests/sdk/*.cpp; do
  name=$(basename "$src" .cpp)
  echo "==> $name"
  clang++ -std=c++20 -O1 -I"$sdk/include" "$src" -L"$sdk/lib" -lrexruntimerd -Wl,-rpath,"$sdk/lib" -o "$out/$name"
  "$out/$name" || status=1
done
exit $status
