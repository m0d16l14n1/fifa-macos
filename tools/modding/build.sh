#!/bin/sh
# Builds the modding tools' C helpers into out/tools (libmspack from the SDK checkout, zlib from macOS).
set -e
here="$(cd "$(dirname "$0")" && pwd)"; root="$(cd "$here/../.." && pwd)"
ms="$root/third_party/rexglue-sdk/thirdparty/libmspack/libmspack/mspack"
mkdir -p "$root/out/tools"
clang -O2 -w -I"$ms" -o "$root/out/tools/unchunk" "$here/unchunk.c" "$ms/lzxd.c" -lz
echo "built $root/out/tools/unchunk"
