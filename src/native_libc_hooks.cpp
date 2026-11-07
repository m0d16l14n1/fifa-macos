// Native replacements for the C runtime's memcpy, memset and memmove in default.xex.
//
// Adapted from ReStreet (FIFA Street 2012, the same EA engine family). The recompiled versions run as
// loops of byte-swapped guest loads and stores that the compiler cannot vectorise; their register contract
// is plain (r3 = destination, r4 = source or fill byte, r5 = byte count, r3 returned unchanged), so the
// host's own routines do the same work. Anything unusual runs the original recompiled body
// (__imp__sub_XXXXXXXX):
//   - ranges that touch the MMIO window (the MMIO handler only decodes plain loads and stores);
//   - ranges that straddle the 0xE0000000 physical alias (the host offset changes there);
//   - overlapping memcpy ranges (the original copies forward; memmove tail-calls it for dst < src).
// The three were identified in FIFA 19's CRT: memcpy saves r3 and prefetches with dcbt, memset fills a
// byte pattern a word at a time, memmove copies backward when dst >= src. FIFA19_NATIVE_LIBC=0 runs the
// original guest code (A/B testing).
#include <cstdint>
#include <cstdlib>
#include <cstring>

#include <rex/hook.h>

REX_EXTERN(__imp__sub_825A5C60);  // memcpy
REX_EXTERN(__imp__sub_825A69B0);  // memset
REX_EXTERN(__imp__sub_825A6C00);  // memmove

namespace {

bool HooksEnabled() {
  static const bool enabled = [] {
    const char* value = std::getenv("FIFA19_NATIVE_LIBC");
    return !(value && value[0] == '0');
  }();
  return enabled;
}

inline uint8_t* HostAddress(uint8_t* base, uint32_t address) {
  return base + address + (address >= 0xE0000000u ? 0x1000u : 0u);
}

// True when [address, address + size) is ordinary guest RAM that host code may touch directly.
inline bool PlainRange(uint32_t address, uint32_t size) {
  const uint64_t end = uint64_t(address) + size;
  if (end > 0x100000000ull) return false;
  if (address < 0x80000000u && end > 0x7F000000u) return false;  // MMIO 0x7F000000-0x7FFFFFFF.
  if (address < 0xE0000000u && end > 0xE0000000u) return false;
  return true;
}

inline bool Overlaps(uint32_t a, uint32_t b, uint32_t size) {
  return a < uint64_t(b) + size && b < uint64_t(a) + size;
}

}  // namespace

REX_HOOK_RAW(sub_825A5C60) {
  const uint32_t destination = ctx.r3.u32, source = ctx.r4.u32, size = ctx.r5.u32;
  if (HooksEnabled() && PlainRange(destination, size) && PlainRange(source, size) &&
      !Overlaps(destination, source, size)) {
    if (size) std::memcpy(HostAddress(base, destination), HostAddress(base, source), size);
    return;
  }
  __imp__sub_825A5C60(ctx, base);
}

REX_HOOK_RAW(sub_825A69B0) {
  const uint32_t destination = ctx.r3.u32, size = ctx.r5.u32;
  if (HooksEnabled() && PlainRange(destination, size)) {
    if (size) std::memset(HostAddress(base, destination), int(ctx.r4.u32 & 0xFF), size);
    return;
  }
  __imp__sub_825A69B0(ctx, base);
}

REX_HOOK_RAW(sub_825A6C00) {
  const uint32_t destination = ctx.r3.u32, source = ctx.r4.u32, size = ctx.r5.u32;
  if (HooksEnabled() && PlainRange(destination, size) && PlainRange(source, size)) {
    if (size && destination != source) {
      std::memmove(HostAddress(base, destination), HostAddress(base, source), size);
    }
    return;
  }
  __imp__sub_825A6C00(ctx, base);
}
