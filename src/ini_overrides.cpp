// FIFA's own settings (the engine's ini keys, "SECTION/KEY" names compiled into default.xex) answered from
// fifa19_ini, for EA's own test switches: FREE_ROAM_AUTOMATCH (a match straight from boot, at any stadium, time
// of day and weather), SKIP_BOOTFLOW and others. The engine reads integer keys through one getter,
// sub_8242ADF8(ini, key, default, flag) -> r3 (the key's value, or the default when the key is not set).
#include <cstdint>
#include <cstdlib>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>

#include <fmt/format.h>

#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/logging.h>

REXCVAR_DEFINE_STRING(fifa19_ini, "", "FIFA19",
                      "FIFA's own ini keys set to integers, comma separated: KEY=VALUE,... (e.g. "
                      "FREE_ROAM_AUTOMATCH/ENABLED=1). docs/DEBUGGING.md lists the useful ones");
REXCVAR_DEFINE_BOOL(fifa19_ini_log, false, "FIFA19",
                    "Development: logs each ini key the game reads (once), with its value");

// Quick match: the game boots past its intro movies and menus into the practice arena, whose idle timer starts
// EA's auto match (FREE_ROAM_AUTOMATCH: the CPU against the CPU) within seconds, set up from these. -1: the game
// picks (random teams, a stadium, its time of day).
REXCVAR_DEFINE_BOOL(fifa19_quick_match, false, "FIFA19",
                    "Boot straight into a match (EA's auto match: the CPU against the CPU) with the settings below; "
                    "for testing stadiums, times of day and weather without the menus")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_INT32(fifa19_match_stadium, -1, "FIFA19", "Quick match: the stadium's id (-1: the game picks)");
REXCVAR_DEFINE_INT32(fifa19_match_time, -1, "FIFA19",
                     "Quick match: 1 day, 3 night (the stadium's lighting, STADIUM_LIGHT_TYPE_ID: the two every "
                     "stadium has; -1: the game picks)");
REXCVAR_DEFINE_INT32(fifa19_match_weather, 0, "FIFA19", "Quick match: the weather (0 clear, 1 rain, 2 snow, 3 overcast)");
REXCVAR_DEFINE_INT32(fifa19_match_half_length, 4, "FIFA19", "Quick match: minutes a half");
REXCVAR_DEFINE_INT32(fifa19_match_home_team, -1, "FIFA19", "Quick match: the home team's id (-1: random)");
REXCVAR_DEFINE_INT32(fifa19_match_away_team, -1, "FIFA19", "Quick match: the away team's id (-1: random)");
REXCVAR_DEFINE_INT32(fifa19_match_seed, 1, "FIFA19",
                     "Quick match: the AI's random seed, so two runs play the same match (0: the game's own)");

REX_EXTERN(__imp__sub_8242ADF8);

namespace {

std::mutex g_mutex;
std::string g_parsed_from;
std::unordered_map<std::string, int32_t> g_values;
std::set<std::string> g_logged;

// The quick match's keys, then fifa19_ini's (which win).
std::string Spec() {
  std::string spec;
  if (REXCVAR_GET(fifa19_quick_match)) {
    spec = fmt::format(
        "SKIP_BOOTFLOW=1,BOOT_TO_MENU=0,FREE_ROAM_AUTOMATCH/ON=1,FREE_ROAM_AUTOMATCH/ENABLED=1,"
        "FREE_ROAM_AUTOMATCH/TIMEOUT=1,FREE_ROAM_AUTOMATCH/STADIUM_ID={},{}"
        "FREE_ROAM_AUTOMATCH/WEATHER_TYPE={},FREE_ROAM_AUTOMATCH/HALF_LENGTH={},FREE_ROAM_AUTOMATCH/HOME_TEAM_ID={},"
        "FREE_ROAM_AUTOMATCH/AWAY_TEAM_ID={},{}",
        REXCVAR_GET(fifa19_match_stadium),
        REXCVAR_GET(fifa19_match_time) > 0 ? fmt::format("STADIUM_LIGHT_TYPE_ID={},", REXCVAR_GET(fifa19_match_time))
                                           : std::string(),
        REXCVAR_GET(fifa19_match_weather),
        REXCVAR_GET(fifa19_match_half_length), REXCVAR_GET(fifa19_match_home_team),
        REXCVAR_GET(fifa19_match_away_team),
        REXCVAR_GET(fifa19_match_seed) ? fmt::format("FREE_ROAM_AUTOMATCH/AI_RANDOMSEED={},", REXCVAR_GET(fifa19_match_seed))
                                       : std::string());
  }
  return spec + REXCVAR_GET(fifa19_ini);
}

// The overrides, parsed again when they change (the dev pad's `set` may change them while the game runs).
const int32_t* Override(const std::string& key) {
  const std::string spec = Spec();
  if (spec != g_parsed_from) {
    g_parsed_from = spec;
    g_values.clear();
    std::istringstream in(spec);
    for (std::string item; std::getline(in, item, ',');) {
      const size_t eq = item.find('=');
      if (eq == std::string::npos) continue;
      std::string name = item.substr(0, eq);
      while (!name.empty() && name.front() == ' ') name.erase(0, 1);
      while (!name.empty() && name.back() == ' ') name.pop_back();
      g_values[name] = int32_t(std::strtol(item.c_str() + eq + 1, nullptr, 0));
    }
    if (!g_values.empty()) REXLOG_INFO("fifa19: ini overrides: {}", spec);
  }
  const auto it = g_values.find(key);
  return it == g_values.end() ? nullptr : &it->second;
}

}  // namespace

REX_HOOK_RAW(sub_8242ADF8) {
  const uint32_t key_address = ctx.r4.u32;
  const std::string key = key_address ? reinterpret_cast<const char*>(base + key_address) : "";
  const int32_t fallback = ctx.r5.s32;
  {
    std::lock_guard lock(g_mutex);
    if (const int32_t* value = Override(key)) {
      if (REXCVAR_GET(fifa19_ini_log) && g_logged.insert(key).second)
        REXLOG_INFO("fifa19: ini {} = {} (set; default {})", key, *value, fallback);
      ctx.r3.s64 = *value;
      return;
    }
  }
  __imp__sub_8242ADF8(ctx, base);
  if (REXCVAR_GET(fifa19_ini_log)) {
    std::lock_guard lock(g_mutex);
    if (g_logged.insert(key).second) REXLOG_INFO("fifa19: ini {} = {} (default {})", key, ctx.r3.s32, fallback);
  }
}

// FREE_ROAM_AUTOMATCH/STADIUM_TOD (not the lighting: every stadium takes 1, 3 and 5, all daylight; the lighting
// is STADIUM_LIGHT_TYPE_ID, 1 day and 3 night, above) is checked against the stadium's own (timeofday1..4 in the
// game's database, sub_82AFA310(stadium, tod) -> bool); one it doesn't have is replaced by the stadium's pick
// (sub_82B00AB0). Logged with fifa19_ini_log.
REX_EXTERN(__imp__sub_82AFA310);
REX_EXTERN(__imp__sub_82B00AB0);

REX_HOOK_RAW(sub_82AFA310) {
  const int32_t tod = ctx.r4.s32;
  if (REXCVAR_GET(fifa19_ini_log)) {
    // Every value the stadium takes (the check only reads the game's database).
    std::string valid;
    for (int32_t value = 0; value < 9; ++value) {
      PPCContext probe = ctx;
      probe.r4.s64 = value;
      __imp__sub_82AFA310(probe, base);
      if (probe.r3.u32 & 0xFF) valid += fmt::format(" {}", value);
    }
    REXLOG_INFO("fifa19: the stadium's times of day:{}", valid);
  }
  __imp__sub_82AFA310(ctx, base);
  if (REXCVAR_GET(fifa19_ini_log)) REXLOG_INFO("fifa19: time of day {} for the stadium: {}", tod, ctx.r3.u32 & 0xFF ? "valid" : "not valid");
}

REX_HOOK_RAW(sub_82B00AB0) {
  __imp__sub_82B00AB0(ctx, base);
  if (REXCVAR_GET(fifa19_ini_log)) REXLOG_INFO("fifa19: the stadium's own time of day: {}", ctx.r3.s32);
}
