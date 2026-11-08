// EA's debug print, sub_826A1EB0(channel, format, ...): an empty function in the retail build, called from about
// 4,000 places (the compiler merged every empty function into it, so only calls whose r4 is printable text with a
// format are messages) (stadium names with their ids, the boot flow's states, the weather and time of day picked for a
// match...). fifa19_guest_log writes the messages to our log, formatted from the guest's arguments: on the Xbox
// 360 every variadic argument is a 64-bit integer register (r5-r10; a double as its bits), the rest on the stack.
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <string>

#include <fmt/format.h>

#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/logging.h>
#include <rex/runtime.h>
#include <rex/system/xmemory.h>

REXCVAR_DEFINE_STRING(fifa19_guest_log, "", "FIFA19",
                      "Development: the game's own debug messages to the log: * for all, or text a message must "
                      "contain (case sensitive), several separated by |");

namespace {

uint64_t Argument(PPCContext& ctx, uint8_t* base, int index) {
  switch (index) {
    case 0: return ctx.r5.u64;
    case 1: return ctx.r6.u64;
    case 2: return ctx.r7.u64;
    case 3: return ctx.r8.u64;
    case 4: return ctx.r9.u64;
    case 5: return ctx.r10.u64;
    default: {
      // The caller's parameter save area: 8 bytes a register, after the 0x50-byte linkage area... r3-r10 first.
      const uint32_t address = ctx.r1.u32 + 0x50 + 8 * uint32_t(index + 2);
      uint64_t value;
      std::memcpy(&value, base + address, 8);
      return __builtin_bswap64(value);
    }
  }
}

// Readable guest memory (a pointer from a call that is not a print may point anywhere, and reading an unmapped
// page faults).
bool Readable(uint32_t address) {
  if (address < 0x10000) return false;
  auto* memory = rex::Runtime::instance() ? rex::Runtime::instance()->memory() : nullptr;
  auto* heap = memory ? memory->LookupHeap(address) : nullptr;
  uint32_t protect = 0;
  return heap && heap->QueryProtect(address, &protect) && (protect & rex::memory::kMemoryProtectRead);
}

// The executable's image: where every format string is (pages a read never faults on).
bool InImage(uint32_t address) { return address >= 0x82000000u && address < 0x83CA0000u; }

std::string GuestString(uint8_t* base, uint32_t address) {
  if (!InImage(address) && !Readable(address)) return "(?)";
  const char* text = reinterpret_cast<const char*>(base + address);
  // Up to the end of its page, and into the next one only when that is readable too.
  size_t limit = 4096 - (address & 4095);
  if (limit < 512 && (InImage(address + limit) || Readable(address + uint32_t(limit)))) limit = 512;
  return std::string(text, strnlen(text, std::min<size_t>(limit, 512)));
}

std::string Format(PPCContext& ctx, uint8_t* base, const char* format) {
  std::string out;
  int next = 0;
  for (const char* p = format; *p; ++p) {
    if (*p != '%') {
      out += *p;
      continue;
    }
    if (p[1] == '%') { out += '%'; ++p; continue; }
    std::string spec = "%";
    ++p;
    while (*p && std::strchr("-+ #0123456789.lhzjtLI", *p)) spec += *p++;
    if (!*p) break;
    const char conversion = *p;
    if (next >= 14) { out += "?"; continue; }
    const uint64_t value = Argument(ctx, base, next++);
    char buffer[128];
    switch (conversion) {
      case 's': case 'S':
        out += GuestString(base, uint32_t(value));
        break;
      case 'f': case 'g': case 'e': case 'F': case 'G': case 'E': {
        double d;
        std::memcpy(&d, &value, 8);
        std::snprintf(buffer, sizeof(buffer), (spec + conversion).c_str(), d);
        out += buffer;
        break;
      }
      case 'c':
        out += char(value);
        break;
      case 'p': case 'x': case 'X': case 'u': case 'o':
        std::snprintf(buffer, sizeof(buffer), (std::string("%") + (spec.size() > 1 ? spec.substr(1) : "") + conversion)
                      .c_str(), unsigned(value));
        out += buffer;
        break;
      default:  // d, i and anything else as a signed 32-bit integer
        std::snprintf(buffer, sizeof(buffer), "%d", int32_t(value));
        out += buffer;
        break;
    }
  }
  while (!out.empty() && (out.back() == '\n' || out.back() == '\r')) out.pop_back();
  return out;
}

bool Wanted(const std::string& message, const std::string& filter) {
  if (filter == "*") return true;
  size_t start = 0;
  while (start <= filter.size()) {
    const size_t bar = filter.find('|', start);
    const std::string part = filter.substr(start, bar == std::string::npos ? std::string::npos : bar - start);
    if (!part.empty() && message.find(part) != std::string::npos) return true;
    if (bar == std::string::npos) break;
    start = bar + 1;
  }
  return false;
}

}  // namespace

REX_HOOK_RAW(sub_826A1EB0) {
  const std::string& filter = REXCVAR_GET(fifa19_guest_log);
  if (filter.empty() || !InImage(ctx.r4.u32)) return;
  const char* format = reinterpret_cast<const char*>(base + ctx.r4.u32);
  size_t length = 0;
  for (; length < 400 && format[length]; ++length) {
    const unsigned char c = format[length];
    if (c < 0x20 && c != '\n' && c != '\t' && c != '\r') return;
    if (c >= 0x7F) return;
  }
  if (length < 4 || format[length]) return;
  const std::string message = Format(ctx, base, format);
  if (Wanted(message, filter)) REXLOG_INFO("guest: {}", message);
}
