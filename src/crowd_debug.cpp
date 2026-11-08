// Development (C7, the crowd missing in close shots): the crowd's cell arrays, found through the routine that sets
// them up (sub_82A3ED30(crowd, ...): vectors of seats +16, cells +40, cell bounds +64, cell visibility +88, cell
// masks +112 and cell lods +136, each {begin, end, capacity, allocator, name}). fifa19_crowd_debug logs the crowd
// object's address at set-up; the dev pad's peek/dump then reads the arrays.
#include <cstdint>
#include <cstring>
#include <algorithm>

#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/logging.h>

REXCVAR_DEFINE_BOOL(fifa19_crowd_debug, false, "FIFA19",
                    "Development: log the crowd object's address when the game sets its cell arrays up");

REX_EXTERN(__imp__sub_82A3ED30);
void Fifa19CrowdDebugSeen(uint32_t crowd);

REX_HOOK_RAW(sub_82A3ED30) {
  const uint32_t crowd = ctx.r3.u32;
  __imp__sub_82A3ED30(ctx, base);
  if (REXCVAR_GET(fifa19_crowd_debug)) {
    REXLOG_INFO("fifa19: crowd cell arrays at {:08X}", crowd);
    Fifa19CrowdDebugSeen(crowd);
  }
}

#include <algorithm>
#include <atomic>
#include <map>
#include <vector>
#include <mutex>
#include <chrono>
#include <string>
#include <thread>

#include <fmt/format.h>

#include <rex/runtime.h>
#include <rex/system/xmemory.h>

void Fifa19CrowdWatchWriters(uint32_t crowd);

namespace {
std::mutex g_mutex;
std::vector<uint32_t> g_crowds;

uint32_t Load32(uint8_t* p) { return __builtin_bswap32(*reinterpret_cast<uint32_t*>(p)); }

// Every 250 ms: each array's length in bytes, and for the visibility, masks and lods how many bytes are not zero
// and the first 48 of them.
void Watch() {
  auto* memory = rex::Runtime::instance()->memory();
  for (;;) {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    std::vector<uint32_t> crowds;
    {
      std::lock_guard lock(g_mutex);
      crowds = g_crowds;
    }
    std::string line;
    for (uint32_t crowd : crowds) {
      uint8_t* object = memory->TranslateVirtual(crowd);
      line += fmt::format(" | {:08X}", crowd);
      // visibility +88, masks +112, lods +136: a histogram of their byte values.
      for (int v : {3, 4, 5}) {
        const uint32_t begin = Load32(object + 16 + 24 * v), end = Load32(object + 20 + 24 * v);
        const uint32_t bytes = end >= begin && end - begin < 4096 ? end - begin : 0;
        uint8_t* data = bytes ? memory->TranslateVirtual(begin) : nullptr;
        std::map<uint32_t, uint32_t> histogram;
        for (uint32_t i = 0; i < bytes; ++i) ++histogram[data[i]];
        if (v == 5) {
          // +136: a 64-bit batch mask per cell (the cull ORs the visible cells' into +216).
          uint32_t empty = 0, cells = bytes / 8;
          for (uint32_t c = 0; c < cells; ++c) {
            uint64_t m = 0;
            std::memcpy(&m, data + 8 * c, 8);
            empty += m == 0;
          }
          const uint32_t vis_begin = Load32(object + 88);
          std::string visible_masks;
          const uint8_t* levels = memory->TranslateVirtual(Load32(object + 112));
          for (uint32_t c = 0; c < cells; ++c) {
            if (memory->TranslateVirtual(vis_begin)[c] & 2) visible_masks += fmt::format(" L{}", levels[c]);
          }
          line += fmt::format(" batches: {} of {} cells none; visible cells'{} | used {:016X}", empty, cells,
                              visible_masks.substr(0, 120), __builtin_bswap64(*reinterpret_cast<uint64_t*>(object + 216)));
          continue;
        }
        line += v == 3 ? " vis" : " mask";
        for (auto [value, count] : histogram) line += fmt::format(" {:X}:{}", value, count);
      }
    }
    if (!line.empty()) REXLOG_INFO("fifa19: crowd{}", line);
    if (!crowds.empty()) {
      uint8_t* first = memory->TranslateVirtual(crowds.front());
      if (Load32(first + 92) > Load32(first + 88)) Fifa19CrowdWatchWriters(crowds.front());
    }
  }
}
}  // namespace

void Fifa19CrowdDebugSeen(uint32_t crowd) {
  if (!REXCVAR_GET(fifa19_crowd_debug)) return;
  static std::once_flag started;
  {
    std::lock_guard lock(g_mutex);
    if (std::find(g_crowds.begin(), g_crowds.end(), crowd) == g_crowds.end()) g_crowds.push_back(crowd);
  }
  std::call_once(started, [] { std::thread(Watch).detach(); });
}

// fifa19_crowd_writers: which recompiled functions write the first crowd object's visibility array. Its host page
// is write-protected; a write there faults, our handler records the writer's PC and unprotects the page so the
// write goes on, and a thread protects it again every 2 ms. Logged every 2 s as function names (dladdr).
#include <dlfcn.h>
#include <signal.h>
#include <sys/mman.h>
#include <unistd.h>

REXCVAR_DEFINE_BOOL(fifa19_crowd_writers, false, "FIFA19",
                    "Development: log the functions that write the crowd's cell visibility (with fifa19_crowd_debug)");
REXCVAR_DEFINE_BOOL(fifa19_crowd_readers, false, "FIFA19",
                    "Development: log the functions that read or write the crowd object's +208..+224 (its 'a cell is "
                    "visible' flag and the visible cells' batch mask), with fifa19_crowd_debug");

namespace {
std::atomic<uintptr_t> g_watch_lo{0}, g_watch_hi{0}, g_watch_page{0};
std::atomic<bool> g_watch_armed{false};
std::atomic<int> g_watch_protection{PROT_READ};
constexpr int kPcSlots = 64;
std::atomic<uintptr_t> g_pcs[kPcSlots];
std::atomic<uint32_t> g_pc_counts[kPcSlots];
struct sigaction g_old_segv, g_old_bus;

void OnFault(int sig, siginfo_t* info, void* context) {
  const uintptr_t address = reinterpret_cast<uintptr_t>(info->si_addr);
  const uintptr_t page = g_watch_page.load();
  const size_t page_size = size_t(getpagesize());
  if (page && address >= page && address < page + page_size) {
    if (address >= g_watch_lo.load() && address < g_watch_hi.load()) {
      const uintptr_t pc = reinterpret_cast<ucontext_t*>(context)->uc_mcontext->__ss.__pc;
      for (int i = 0; i < kPcSlots; ++i) {
        uintptr_t expected = 0;
        if (g_pcs[i].load() == pc || g_pcs[i].compare_exchange_strong(expected, pc)) {
          if (g_pcs[i].load() == pc) { ++g_pc_counts[i]; break; }
        }
      }
    }
    mprotect(reinterpret_cast<void*>(page), page_size, PROT_READ | PROT_WRITE);
    g_watch_armed.store(false);
    return;
  }
  struct sigaction& old = sig == SIGBUS ? g_old_bus : g_old_segv;
  if (old.sa_flags & SA_SIGINFO) old.sa_sigaction(sig, info, context);
  else if (old.sa_handler != SIG_DFL && old.sa_handler != SIG_IGN) old.sa_handler(sig);
  else { signal(sig, SIG_DFL); raise(sig); }
}

void WatchWriters(uint8_t* host_begin, uint32_t bytes) {
  const size_t page_size = size_t(getpagesize());
  const uintptr_t lo = reinterpret_cast<uintptr_t>(host_begin);
  g_watch_lo = lo; g_watch_hi = lo + bytes; g_watch_page = lo & ~(page_size - 1);
  struct sigaction action {};
  action.sa_sigaction = OnFault;
  action.sa_flags = SA_SIGINFO;
  sigemptyset(&action.sa_mask);
  sigaction(SIGSEGV, &action, &g_old_segv);
  sigaction(SIGBUS, &action, &g_old_bus);
  std::thread([page_size] {
    auto last_log = std::chrono::steady_clock::now();
    for (;;) {
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
      if (!g_watch_armed.exchange(true))
        mprotect(reinterpret_cast<void*>(g_watch_page.load()), page_size, g_watch_protection.load());
      if (std::chrono::steady_clock::now() - last_log > std::chrono::seconds(2)) {
        last_log = std::chrono::steady_clock::now();
        std::string line;
        for (int i = 0; i < kPcSlots; ++i) {
          const uintptr_t pc = g_pcs[i].load();
          if (!pc) continue;
          Dl_info dl{};
          dladdr(reinterpret_cast<void*>(pc), &dl);
          line += fmt::format(" {}+{:X} x{}", dl.dli_sname ? dl.dli_sname : "?",
                              dl.dli_saddr ? pc - reinterpret_cast<uintptr_t>(dl.dli_saddr) : 0, g_pc_counts[i].load());
        }
        if (!line.empty()) REXLOG_INFO("fifa19: crowd watched accesses:{}", line);
      }
    }
  }).detach();
}
}  // namespace

void Fifa19CrowdWatchWriters(uint32_t crowd) {
  if (REXCVAR_GET(fifa19_crowd_readers)) {
    static std::once_flag once_readers;
    std::call_once(once_readers, [crowd] {
      auto* memory = rex::Runtime::instance()->memory();
      g_watch_protection = PROT_NONE;
      REXLOG_INFO("fifa19: watching accesses to the crowd {:08X}+208..224", crowd);
      WatchWriters(memory->TranslateVirtual(crowd + 208), 16);
    });
    return;
  }
  if (!REXCVAR_GET(fifa19_crowd_writers)) return;
  static std::once_flag once;
  std::call_once(once, [crowd] {
    auto* memory = rex::Runtime::instance()->memory();
    uint8_t* object = memory->TranslateVirtual(crowd);
    const uint32_t begin = Load32(object + 88), end = Load32(object + 92);
    if (!begin || end <= begin) return;
    REXLOG_INFO("fifa19: watching writes to the crowd visibility at {:08X}+{}", begin, end - begin);
    WatchWriters(memory->TranslateVirtual(begin), end - begin);
  });
}

// The crowd's cull (sub_829F6C80(crowd, frustum)): the frustum's six planes (vec4 each, big-endian floats) and the
// crowd's bounds (+176 min, +192 max), logged once a second with fifa19_crowd_debug.
REX_EXTERN(__imp__sub_829F6C80);

namespace {
std::atomic<uint64_t> g_perm_matches[6];
std::atomic<uint64_t> g_cells_tested{0}, g_cells_disagree{0}, g_cells_host_visible{0}, g_cells_game_visible{0};
}

REX_HOOK_RAW(sub_829F6C80) {
  const uint32_t crowd = ctx.r3.u32, frustum = ctx.r4.u32;
  if (!REXCVAR_GET(fifa19_crowd_debug)) {
    __imp__sub_829F6C80(ctx, base);
    return;
  }
  // The cells this call writes: the others (the whole stand out of view: none) keep a sentinel, then their value.
  const uint32_t vis_begin = __builtin_bswap32(*reinterpret_cast<uint32_t*>(base + crowd + 88));
  const uint32_t vis_end = __builtin_bswap32(*reinterpret_cast<uint32_t*>(base + crowd + 92));
  std::vector<uint8_t> before;
  if (vis_end > vis_begin && vis_end - vis_begin < 4096) {
    before.assign(base + vis_begin, base + vis_end);
    std::memset(base + vis_begin, 0xEE, vis_end - vis_begin);
  }
  __imp__sub_829F6C80(ctx, base);
  std::vector<bool> written(before.size());
  for (size_t i = 0; i < before.size(); ++i) {
    written[i] = base[vis_begin + i] != 0xEE;
    if (!written[i]) base[vis_begin + i] = before[i];
  }
  {
    // The game's per-cell result (visibility byte bit 1) against the same box-frustum test in doubles: the corner
    // furthest along each plane's normal, min over the planes of n.corner + d (w = 1), minus 1e-4; culled below 0.
    auto rd = [&](uint32_t address) {
      uint32_t bits = __builtin_bswap32(*reinterpret_cast<uint32_t*>(base + address));
      float v;
      std::memcpy(&v, &bits, 4);
      return double(v);
    };
    auto rw = [&](uint32_t address) { return __builtin_bswap32(*reinterpret_cast<uint32_t*>(base + address)); };
    const uint32_t bounds = rw(crowd + 64), bounds_end = rw(crowd + 68), vis = rw(crowd + 88);
    const uint32_t cells = bounds_end > bounds ? (bounds_end - bounds) / 32 : 0;
    std::vector<uint8_t> host_bits(cells, 0);
    for (uint32_t c = 0; c < cells && c < written.size(); ++c) {
      if (!written[c]) continue;
      double lo[4], hi[4];
      for (int k = 0; k < 4; ++k) { lo[k] = rd(bounds + 32 * c + 4 * k); hi[k] = rd(bounds + 32 * c + 16 + 4 * k); }
      double worst = 1.0;
      for (int p = 0; p < 6; ++p) {
        double dot = 0.0;
        for (int k = 0; k < 4; ++k) {
          const double n = rd(frustum + 16 * p + 4 * k);
          dot += n * (n <= 0.0 ? lo[k] : hi[k]);
        }
        worst = std::min(worst, dot);
      }
      const bool host_visible = worst - 1e-4 >= 0.0;
      host_bits[c] = host_visible;
      const bool game_visible = (base[vis + c] & 2) != 0;
      ++g_cells_tested;
      g_cells_host_visible += host_visible;
      g_cells_game_visible += game_visible;
      if (host_visible != game_visible) {
        static std::atomic<int> logged{0};
        if (logged++ < 12)
          REXLOG_INFO("fifa19: crowd cell {} of {:08X}: host {} game {} margin {:.3f} box [{:.1f} {:.1f} {:.1f} {:.3f}]-"
                      "[{:.1f} {:.1f} {:.1f} {:.3f}] vis byte {:02X}", c, crowd, host_visible, game_visible, worst,
                      lo[0], lo[1], lo[2], lo[3], hi[0], hi[1], hi[2], hi[3], base[vis + c]);
        ++g_cells_disagree;
      }
    }
    // Groups of four (the game's batched path): which order of the host's results the game's match.
    static const int kPerm[6][4] = {{0, 1, 2, 3}, {3, 2, 1, 0}, {1, 2, 3, 0}, {2, 3, 0, 1}, {3, 0, 1, 2}, {1, 0, 3, 2}};
    for (uint32_t g = 0; g + 4 <= cells && g + 4 <= written.size(); g += 4) {
      if (!written[g]) continue;
      bool any_difference = false;
      for (int k = 0; k < 4; ++k) any_difference |= host_bits[g + k] != host_bits[g];
      if (!any_difference) continue;  // all alike: no order shows
      for (int p = 0; p < 6; ++p) {
        bool match = true;
        for (int k = 0; k < 4; ++k) match &= ((base[vis + g + k] & 2) != 0) == (host_bits[g + kPerm[p][k]] != 0);
        if (match) ++g_perm_matches[p];
      }
    }
  }
  static std::atomic<int64_t> last{0};
  const int64_t now = std::chrono::duration_cast<std::chrono::milliseconds>(
                          std::chrono::steady_clock::now().time_since_epoch()).count();
  if (now - last.load() < 200) return;
  last = now;
  auto f = [&](uint32_t address) {
    uint32_t bits = __builtin_bswap32(*reinterpret_cast<uint32_t*>(base + address));
    float v;
    std::memcpy(&v, &bits, 4);
    return v;
  };
  std::string planes;
  for (int p = 0; p < 6; ++p)
    planes += fmt::format(" [{:.3f} {:.3f} {:.3f} {:.1f}]", f(frustum + 16 * p), f(frustum + 16 * p + 4),
                          f(frustum + 16 * p + 8), f(frustum + 16 * p + 12));
  REXLOG_INFO("fifa19: crowd cells tested {}, visible by the host's test {}, by the game's {}, disagreeing {}",
              g_cells_tested.load(), g_cells_host_visible.load(), g_cells_game_visible.load(), g_cells_disagree.load());
  REXLOG_INFO("fifa19: crowd group orders matching: identity {}, reversed {}, rotate1 {}, rotate2 {}, rotate3 {}, "
              "pair swap {}", g_perm_matches[0].load(), g_perm_matches[1].load(), g_perm_matches[2].load(),
              g_perm_matches[3].load(), g_perm_matches[4].load(), g_perm_matches[5].load());
  REXLOG_INFO("fifa19: crowd cull {:08X} frustum {:08X}:{} box [{:.1f} {:.1f} {:.1f} {:.1f}]-[{:.1f} {:.1f} {:.1f} {:.1f}]",
              crowd, frustum, planes, f(crowd + 176), f(crowd + 180), f(crowd + 184), f(crowd + 188), f(crowd + 192),
              f(crowd + 196), f(crowd + 200), f(crowd + 204));
}

// The crowd's level of detail per visible cell (sub_829F6D98(stand, index, view-projection, ..., minimum level in
// r9)): the stand's maximum level less one for each on-screen size threshold (128, 64, 32, 16, 8) the cell passes,
// at least r9. Levels 0 and 1, which close cameras pick for the stands nearest them (the walk-out's warm-up and
// close shots), draw nothing here and hitch the frame (BACKLOG C7: an even 30 FPS walk-out at 2, against 83 ms
// presents and 14 ms of judder at the game's levels). Level 2 is the most detailed that draws: the default.
REXCVAR_DEFINE_INT32(fifa19_crowd_min_level, 2, "FIFA19",
                     "The crowd's most detailed level allowed (C7): 0 and 1 leave the stands empty in close shots and "
                     "hitch, 2 draws them; -1: the game's own choice")
    .range(-1, 6);
REX_EXTERN(__imp__sub_829F6D98);

REX_HOOK_RAW(sub_829F6D98) {
  const int32_t min_level = REXCVAR_GET(fifa19_crowd_min_level);
  if (min_level >= 0 && ctx.r9.s32 < min_level) ctx.r9.s64 = min_level;
  __imp__sub_829F6D98(ctx, base);
}
