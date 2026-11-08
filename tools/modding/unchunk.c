/* unchunk: EA's chunked archives entries (chunkzip: raw deflate; chunklzx: Xbox XMemCompress LZX) to their bytes.
 *
 *   unchunk <in> <out>          the whole entry, decompressed (an entry that is not chunked is copied)
 *
 * Header (big-endian): "chunkzip"/"chunklzx", u32 version (2), u32 total size, u32 chunk size, u32 chunk count,
 * u32 alignment (16), padding; then per chunk: u32 compressed size, u32 kind, the data, which starts 16-aligned. LZX chunks
 * are XMemCompress streams: blocks of [0xFF, u16 uncompressed][u16 compressed] LZX frames (32 KB unless said).
 * Built with libmspack's lzxd (the SDK's copy): sh tools/modding/build.sh. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>

#include "mspack.h"
#include "lzx.h"

typedef struct { struct mspack_system sys; } msys;
typedef struct { unsigned char* data; size_t size, pos; } mfile;

static int m_read(struct mspack_file* f, void* buf, int n) {
  mfile* m = (mfile*)f; size_t left = m->size - m->pos; if ((size_t)n > left) n = (int)left;
  memcpy(buf, m->data + m->pos, n); m->pos += n; return n;
}
static int m_write(struct mspack_file* f, void* buf, int n) {
  mfile* m = (mfile*)f; size_t left = m->size - m->pos; if ((size_t)n > left) n = (int)left;
  memcpy(m->data + m->pos, buf, n); m->pos += n; return n;
}
static void* m_alloc(struct mspack_system* s, size_t n) { (void)s; return calloc(n, 1); }
static void m_free(void* p) { free(p); }
static void m_copy(void* src, void* dst, size_t n) { memcpy(dst, src, n); }

static uint32_t be32(const unsigned char* p) { return (uint32_t)p[0] << 24 | p[1] << 16 | p[2] << 8 | p[3]; }

/* One XMemCompress stream (in, n) into out (outsize): headers stripped, frames decompressed by lzxd. */
static int unlzx(const unsigned char* in, size_t n, unsigned char* out, size_t outsize, int window_bits) {
  unsigned char* frames = malloc(n);
  size_t fn = 0, p = 0;
  while (p + 2 <= n) {
    size_t csize;
    if (in[p] == 0xFF) {
      if (p + 5 > n) break;
      csize = (size_t)in[p + 3] << 8 | in[p + 4];
      p += 5;
    } else {
      csize = (size_t)in[p] << 8 | in[p + 1];
      p += 2;
    }
    if (!csize || p + csize > n) break;
    memcpy(frames + fn, in + p, csize);
    fn += csize; p += csize;
  }
  struct mspack_system sys = {0};
  sys.read = m_read; sys.write = m_write; sys.alloc = m_alloc; sys.free = m_free; sys.copy = m_copy;
  mfile src = {frames, fn, 0}, dst = {out, outsize, 0};
  struct lzxd_stream* lzx = lzxd_init(&sys, (struct mspack_file*)&src, (struct mspack_file*)&dst, window_bits, 0,
                                      0x8000, (off_t)outsize, 0);
  int r = lzx ? lzxd_decompress(lzx, (off_t)outsize) : -1;
  if (lzx) lzxd_free(lzx);
  free(frames);
  return r;
}

int main(int argc, char** argv) {
  if (argc != 3) { fprintf(stderr, "usage: unchunk <in> <out>\n"); return 2; }
  FILE* f = fopen(argv[1], "rb"); if (!f) { perror(argv[1]); return 1; }
  fseek(f, 0, SEEK_END); long size = ftell(f); fseek(f, 0, SEEK_SET);
  unsigned char* data = malloc(size); fread(data, 1, size, f); fclose(f);
  FILE* o = fopen(argv[2], "wb"); if (!o) { perror(argv[2]); return 1; }
  int lzx = size >= 8 && !memcmp(data, "chunklzx", 8), zip = size >= 8 && !memcmp(data, "chunkzip", 8);
  if (!lzx && !zip) { fwrite(data, 1, size, o); fclose(o); return 0; }
  uint32_t total = be32(data + 12), chunk = be32(data + 16), count = be32(data + 20), align = be32(data + 24);
  (void)align;
  size_t p = 0x28, written = 0;
  unsigned char* out = malloc(chunk);
  for (uint32_t c = 0; c < count && p + 8 <= (size_t)size; ++c) {
    p = (p + 8 + 15) / 16 * 16 - 8;  /* each chunk's data starts 16-aligned, its 8-byte header just before */
    uint32_t csize = be32(data + p), kind = be32(data + p + 4);
    p += 8;
    size_t want = total - written < chunk ? total - written : chunk;
    int ok = 0;
    if (kind == 0 || csize == want) { memcpy(out, data + p, want); ok = 1; }
    else if (zip) {
      z_stream z = {0}; z.next_in = data + p; z.avail_in = csize; z.next_out = out; z.avail_out = (uInt)want;
      ok = inflateInit2(&z, -15) == Z_OK && inflate(&z, Z_FINISH) >= 0 && z.total_out == want;
      inflateEnd(&z);
    } else {
      for (int bits = 17; bits >= 15 && !ok; --bits) ok = unlzx(data + p, csize, out, want, bits) == 0;
      for (int bits = 18; bits <= 21 && !ok; ++bits) ok = unlzx(data + p, csize, out, want, bits) == 0;
    }
    if (!ok) { fprintf(stderr, "%s: chunk %u (kind %u, %u bytes) failed\n", argv[1], c, kind, csize); return 1; }
    fwrite(out, 1, want, o); written += want;
    p += csize;
  }
  fclose(o);
  return written == total ? 0 : 1;
}
