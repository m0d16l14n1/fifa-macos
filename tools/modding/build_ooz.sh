#!/bin/sh
# Builds out/tools/ooz-x86: powzix's ooz (an open Oodle decompressor: Kraken, Mermaid, Selkie, Leviathan), which
# fbmod.py runs on the Oodle blocks of PC FIFA mods. ooz is written for Windows and x86 (SSE), so it gets POSIX
# stand-ins for the Windows headers and a small main (Oodle blocks in, their bytes out), and is built for x86_64,
# run under Rosetta.
#
#   sh tools/modding/build_ooz.sh [OUTDIR]     (OUTDIR: out/tools)
set -e
here=$(cd "$(dirname "$0")" && pwd)
out="${1:-$here/../../out/tools}"
mkdir -p "$out"
src="$out/ooz"
[ -f "$src/kraken.cpp" ] || git clone -q --depth 1 https://github.com/powzix/ooz.git "$src"
cd "$src"
printf '#pragma once\n' > targetver.h
cat > stdafx.h <<'EOF'
// POSIX/clang stand-ins for the Windows headers ooz was written against (built x86_64, run under Rosetta).
#pragma once
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <assert.h>
#include <x86intrin.h>
#include <time.h>
typedef unsigned char byte;
typedef unsigned char uint8;
typedef unsigned int uint32;
typedef uint64_t uint64;
typedef int64_t int64;
typedef signed int int32;
typedef unsigned short uint16;
typedef signed short int16;
typedef unsigned int uint;
#define __forceinline inline __attribute__((always_inline))
static inline unsigned char _BitScanForward(unsigned long *i, unsigned long m) { if (!m) return 0; *i = __builtin_ctzl(m); return 1; }
static inline unsigned char _BitScanReverse(unsigned long *i, unsigned long m) { if (!m) return 0; *i = 63 - __builtin_clzl(m); return 1; }
#define _byteswap_ulong(x) __builtin_bswap32(x)
#define _byteswap_uint64(x) __builtin_bswap64(x)
#define _byteswap_ushort(x) __builtin_bswap16(x)
#define _rotl(x, n) ((uint32)(((uint32)(x) << ((n) & 31)) | ((uint32)(x) >> ((32 - ((n) & 31)) & 31))))
typedef union { struct { uint32 LowPart; int32 HighPart; }; int64 QuadPart; } LARGE_INTEGER;
static inline int QueryPerformanceCounter(LARGE_INTEGER *t) { struct timespec s; clock_gettime(CLOCK_MONOTONIC, &s); t->QuadPart = (int64)s.tv_sec * 1000000000 + s.tv_nsec; return 1; }
static inline int QueryPerformanceFrequency(LARGE_INTEGER *t) { t->QuadPart = 1000000000; return 1; }
EOF
# kraken.cpp up to its Windows-only part (the Oodle DLL's loader and the command line), then our main.
line=$(grep -n '^typedef int WINAPI OodLZ_CompressFunc' kraken.cpp | cut -d: -f1)
head -n $((line - 1)) kraken.cpp > kraken_mac.cpp
cat >> kraken_mac.cpp <<'EOF'
// ooz-x86 IN OUT SIZE: one raw Oodle block (Kraken, Mermaid, Selkie, Leviathan...) decompressed to SIZE bytes.
// Several blocks: IN holds them back to back as "u32 packed size, u32 unpacked size, data" (little-endian).
int main(int argc, char *argv[]) {
  if (argc != 4 && argc != 3) { fprintf(stderr, "ooz-x86 IN OUT [SIZE]\n"); return 2; }
  FILE *f = fopen(argv[1], "rb"); if (!f) return 1;
  fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
  byte *in = (byte *)malloc(n + 64); if (fread(in, 1, n, f) != (size_t)n) return 1; fclose(f);
  FILE *o = fopen(argv[2], "wb"); if (!o) return 1;
  if (argc == 4) {
    size_t size = strtoul(argv[3], 0, 10);
    byte *out = (byte *)malloc(size + 64);
    int got = Kraken_Decompress(in, n, out, size);
    if (got != (int)size) { fprintf(stderr, "decompress failed (%d)\n", got); return 1; }
    fwrite(out, 1, size, o);
  } else {
    long at = 0;
    while (at + 8 <= n) {
      uint32 packed, size; memcpy(&packed, in + at, 4); memcpy(&size, in + at + 4, 4); at += 8;
      byte *out = (byte *)malloc(size + 64);
      int got = Kraken_Decompress(in + at, packed, out, size);
      if (got != (int)size) { fprintf(stderr, "decompress failed at %ld (%d)\n", at, got); return 1; }
      fwrite(out, 1, size, o); free(out); at += packed;
    }
  }
  fclose(o);
  return 0;
}
EOF
clang++ -arch x86_64 -O2 -std=c++14 -w -o ../ooz-x86 kraken_mac.cpp bitknit.cpp lzna.cpp
echo "built $(cd .. && pwd)/ooz-x86"
