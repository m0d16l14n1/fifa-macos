// Guest wait semantics the game depends on (scripts/test_sdk.sh): a multi-object wait is released by a Set+Reset
// or a Pulse that happens while it waits, a Pulse with nobody waiting leaves nothing behind, and a wait wakes soon.
#include <rex/thread.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <thread>
using namespace rex::thread;
using namespace std::chrono;
static int failures = 0;
static void check(bool ok, const char* what) { std::printf("%s %s\n", ok ? "ok  " : "FAIL", what); failures += !ok; }

// Starts a WaitAny on {a, b} in another thread, runs `wake` after 20 ms; true if the wait returned index 0 in time.
template <typename F> bool any_released(WaitHandle* a, WaitHandle* b, F wake) {
  std::atomic<int> got{-1};
  std::thread t([&] {
    auto r = WaitAny({a, b}, false, milliseconds(500));
    got = r.first == WaitResult::kSuccess ? int(r.second) : -2;
  });
  std::this_thread::sleep_for(milliseconds(20));
  wake();
  t.join();
  return got == 0;
}

int main() {
  for (int round = 0; round < 50; ++round) {
    auto m = Event::CreateManualResetEvent(false), other = Event::CreateManualResetEvent(false);
    if (!any_released(m.get(), other.get(), [&] { m->Set(); m->Reset(); })) { check(false, "manual Set+Reset releases a WaitAny"); break; }
    auto p = Event::CreateManualResetEvent(false);
    if (!any_released(p.get(), other.get(), [&] { p->Pulse(); })) { check(false, "manual Pulse releases a WaitAny"); break; }
    auto ap = Event::CreateAutoResetEvent(false);
    if (!any_released(ap.get(), other.get(), [&] { ap->Pulse(); })) { check(false, "auto Pulse releases a WaitAny"); break; }
    auto as = Event::CreateAutoResetEvent(false);
    if (!any_released(as.get(), other.get(), [&] { as->Set(); as->Reset(); })) { check(false, "auto Set+Reset releases a WaitAny"); break; }
    if (round == 49) check(true, "50 rounds: Set+Reset and Pulse release WaitAny (manual and auto)");
  }
  {  // Pulse with nobody waiting: nothing left signaled.
    auto m = Event::CreateManualResetEvent(false), a = Event::CreateAutoResetEvent(false);
    m->Pulse(); a->Pulse();
    check(Wait(m.get(), false, milliseconds(0)) == WaitResult::kTimeout, "manual Pulse with no waiter leaves it reset");
    check(Wait(a.get(), false, milliseconds(0)) == WaitResult::kTimeout, "auto Pulse with no waiter leaves it reset");
  }
  {  // Auto-reset: one Set releases exactly one of two waiters (one WaitAny, one single wait).
    auto a = Event::CreateAutoResetEvent(false), other = Event::CreateManualResetEvent(false);
    std::atomic<int> released{0};
    std::thread t1([&] { if (WaitAny({a.get(), other.get()}, false, milliseconds(200)).first == WaitResult::kSuccess) ++released; });
    std::thread t2([&] { if (Wait(a.get(), false, milliseconds(200)) == WaitResult::kSuccess) ++released; });
    std::this_thread::sleep_for(milliseconds(20));
    a->Set();
    t1.join(); t2.join();
    check(released == 1, "auto-reset Set releases one of two waiters");
    check(Wait(a.get(), false, milliseconds(0)) == WaitResult::kTimeout, "and is consumed");
  }
  {  // WaitAll: both needed.
    auto a = Event::CreateManualResetEvent(false), b = Event::CreateManualResetEvent(false);
    a->Set();
    check(WaitAll({a.get(), b.get()}, false, milliseconds(20)) == WaitResult::kTimeout, "WaitAll waits for both");
    b->Set();
    check(WaitAll({a.get(), b.get()}, false, milliseconds(20)) == WaitResult::kSuccess, "WaitAll with both set");
  }
  {  // A timed-out WaitAny leaves an auto-reset event's later Set for the next waiter.
    auto a = Event::CreateAutoResetEvent(false), other = Event::CreateManualResetEvent(false);
    WaitAny({a.get(), other.get()}, false, milliseconds(5));
    a->Set();
    check(Wait(a.get(), false, milliseconds(0)) == WaitResult::kSuccess, "Set after a timed-out WaitAny stays for the next wait");
  }
  {  // Wake-up latency of a WaitAny after a Set (it polled in 1 ms sleeps: ~0.5-1 ms on average).
    double total_us = 0;
    for (int i = 0; i < 200; ++i) {
      auto a = Event::CreateAutoResetEvent(false), other = Event::CreateManualResetEvent(false);
      std::atomic<long long> woke{0};
      std::thread t([&] {
        WaitAny({a.get(), other.get()}, false, milliseconds(500));
        woke = duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
      });
      std::this_thread::sleep_for(microseconds(300 + (i * 37) % 900));
      const long long set_at = duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
      a->Set();
      t.join();
      total_us += double(woke - set_at);
    }
    std::printf("info WaitAny wake-up after Set: %.0f us on average\n", total_us / 200);
    check(total_us / 200 < 250, "WaitAny wakes within 250 us of a Set on average");
  }
  std::printf("%s\n", failures ? "FAILED" : "all passed");
  return failures != 0;
}
