// What the game needs to take leagues it was not made with (mods, docs/MODDING.md).
//
// League tiers: the game sorts its leagues into six hard-coded lists (sub_82C76400 returns a league's list, or -1
// when it is in none): the top five, the Championship's tier, second divisions, Europe's other first divisions,
// South America and Asia's, the rest. Most callers index a table with the result unchecked (sub_82C76710,
// sub_82C76830, sub_82C768B0, sub_82C766D8, sub_82D2FD18...), so a league in none (a mod's: Russia's 67) reads
// outside it and crashes when a Career starts or its season is simulated. The game's own leagues in no list (Rest
// of World, International, Free Agents...) are left as they are (the callers that check -1 are for them); any other
// league is given fifa19_mod_league_tier.
//
// Scouting regions: a new Career sets up its scouts by the region of the user's league's country
// (sub_82D826F8: the first of nine hard-coded lists of nations that has it, else -1), and indexes the region's list
// with the result unchecked (sub_82DAD6E0, its only caller): a league in a country of none (a mod's league in Rest
// of World, 211, or Wales, 50) read past them and the career never finished loading. Such a country is taken as in
// fifa19_mod_scout_region.

#include <cstdint>

#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/logging.h>

REXCVAR_DEFINE_INT32(fifa19_mod_league_tier, 3, "FIFA19",
                     "Mods: the tier (0-5) of a league the game doesn't have: 0 the top five, 1 the Championship's, 2 "
                     "second divisions, 3 Europe's other first divisions, 4 South America and Asia, 5 the rest");

REXCVAR_DEFINE_INT32(fifa19_mod_scout_region, 2, "FIFA19",
                     "Mods: the scouting region (0-8) of a league's country the game has in none: 2 is Northern "
                     "Europe's (England, Scandinavia, Russia)");

REX_EXTERN(__imp__sub_82C76400);
REX_EXTERN(__imp__sub_82D826F8);

namespace {

// The game's leagues that are in no tier, on purpose.
bool UntieredByDesign(int32_t league) {
  switch (league) {
    case 76:    // Rest of World
    case 78:    // International
    case 111:   // OTP Generics
    case 382:   // Free Agents
    case 383:   // Create Player League
    case 2000:  // Career saved teams
    case 2028:  // Youth squads
    case 2136:  // International Women
      return true;
    default:
      return false;
  }
}

}  // namespace

REX_HOOK_RAW(sub_82C76400) {
  const int32_t league = ctx.r4.s32;
  __imp__sub_82C76400(ctx, base);
  if (ctx.r3.s32 != -1 || league <= 0 || UntieredByDesign(league)) return;
  int32_t tier = REXCVAR_GET(fifa19_mod_league_tier);
  if (tier < 0 || tier > 5) tier = 3;
  ctx.r3.s64 = tier;
  static int32_t logged = 0;
  if (logged != league) {
    logged = league;
    REXLOG_INFO("fifa19: league {} is in none of the game's tiers; taken as tier {}", league, tier);
  }
}

REX_HOOK_RAW(sub_82D826F8) {
  const int32_t nation = ctx.r4.s32;
  __imp__sub_82D826F8(ctx, base);
  if (ctx.r3.s32 != -1) return;
  int32_t region = REXCVAR_GET(fifa19_mod_scout_region);
  if (region < 0 || region > 8) region = 2;
  ctx.r3.s64 = region;
  static int32_t logged = -1;
  if (logged != nation) {
    logged = nation;
    REXLOG_INFO("fifa19: country {} is in none of the scouting regions; taken as region {}", nation, region);
  }
}
