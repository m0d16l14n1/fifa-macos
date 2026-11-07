// The game's step limiter without the busy wait.
//
// sub_823686C0 (default.xex) holds the main loop to a minimum step: it waits until the time base reaches
// start + frequency / divisor (r3: the timer, start at +0 and frequency at +24, both 64-bit; r4: the divisor, 200
// from the main loop, a 5 ms step), spinning on mftb with priority hints, then calls sub_82368638, which advances
// the timer. Recompiled, the spin is a whole host core reading the clock for the main thread's idle time: heat on a
// MacBook (fanless on an Air), which throttles the cores the game's other threads run on.
//
// This version waits for the same moment: it sleeps until about 1 ms before it, then yields until it, and calls
// the same continuation.
//
// Opt-in (FIFA19_NATIVE_LIMITER=1) until BACKLOG P5 is understood: with the main loop sleeping instead of spinning,
// another guest thread soon faults reading address 0x1 in a loop (a race the spin's timing hides). The original
// spin is the default.
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <thread>

#include <array>
#include <atomic>

#include <rex/chrono/clock.h>
#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/logging.h>

REXCVAR_DEFINE_BOOL(fifa19_limiter_stats, false, "FIFA19",
                    "Diagnostic: every 10 s, log how often the game's step limiter (sub_823686C0) ran for each "
                    "divisor (200: the main loop, 60 and 40: other loops) and how long it waited");

REX_EXTERN(__imp__sub_823686C0);  // the original, with its spin
REX_EXTERN(__imp__sub_82368638);  // advances the timer after the wait

namespace {

bool Enabled() {
  static const bool enabled = [] {
    const char* value = std::getenv("FIFA19_NATIVE_LIMITER");
    return value && value[0] == '1';
  }();
  return enabled;
}

int64_t LoadGuestS64(const uint8_t* base, uint32_t address) {
  uint64_t value;
  std::memcpy(&value, base + address, sizeof(value));
  return int64_t(__builtin_bswap64(value));
}

// Calls and waited microseconds by divisor (1..255; others counted at 0), from any thread.
struct Stats {
  std::array<std::atomic<uint64_t>, 256> calls{}, waited_us{};
  std::atomic<int64_t> last_log_us{0};

  void Add(int64_t divisor, uint64_t us) {
    const size_t slot = divisor > 0 && divisor < 256 ? size_t(divisor) : 0;
    calls[slot].fetch_add(1, std::memory_order_relaxed);
    waited_us[slot].fetch_add(us, std::memory_order_relaxed);
    const int64_t now = std::chrono::duration_cast<std::chrono::microseconds>(
                            std::chrono::steady_clock::now().time_since_epoch()).count();
    int64_t last = last_log_us.load(std::memory_order_relaxed);
    if (!last) {
      last_log_us.compare_exchange_strong(last, now);
      return;
    }
    if (now - last < 10'000'000 || !last_log_us.compare_exchange_strong(last, now)) return;
    std::string text;
    for (size_t i = 0; i < calls.size(); ++i) {
      const uint64_t n = calls[i].exchange(0, std::memory_order_relaxed);
      const uint64_t w = waited_us[i].exchange(0, std::memory_order_relaxed);
      if (n) text += fmt::format(" | 1/{}: {:.1f}/s, {:.2f} ms waited each", i, n / ((now - last) / 1e6), w / 1000.0 / n);
    }
    REXLOG_INFO("fifa19 step limiter:{}", text);
  }
};
Stats g_stats;

}  // namespace

REX_HOOK_RAW(sub_823686C0) {
  const int64_t divisor = ctx.r4.s32;
  if (!Enabled() || divisor <= 0) {
    if (!REXCVAR_GET(fifa19_limiter_stats)) {
      __imp__sub_823686C0(ctx, base);  // keeps the guest's own trap for a zero divisor
      return;
    }
    const auto start = std::chrono::steady_clock::now();
    __imp__sub_823686C0(ctx, base);
    g_stats.Add(divisor, uint64_t(std::chrono::duration_cast<std::chrono::microseconds>(
                                      std::chrono::steady_clock::now() - start).count()));
    return;
  }
  const uint32_t timer = ctx.r3.u32;
  const int64_t target = LoadGuestS64(base, timer + 0) + LoadGuestS64(base, timer + 24) / divisor;
  const uint64_t frequency = rex::chrono::Clock::guest_tick_frequency();
  for (;;) {
    const int64_t now = int64_t(rex::chrono::Clock::QueryGuestTickCount());
    const int64_t left = target - now;
    if (left <= 0) break;
    const int64_t left_us = left * 1'000'000 / int64_t(frequency ? frequency : 1);
    if (left_us > 1500) {
      std::this_thread::sleep_for(std::chrono::microseconds(left_us - 1000));
    } else {
      std::this_thread::yield();
    }
  }
  __imp__sub_82368638(ctx, base);  // r3 is still the timer
}
