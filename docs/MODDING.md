# Modding

Mods change the game's files without touching them: the game folder stays as extracted, and a mod is a folder of
files laid out as on the disc. The launcher's **Mods** page lists the mods in
`~/Library/Application Support/FIFA 19/Mods` (one folder each, on unless turned off there) and puts them on when
the game starts.

```
Mods/
  Shirt numbers/
    data/db/fifa_ng_db.db                      replaces the database in data0.big
  New kits/
    data/sceneassets/kit0/kit_11_0_0.rx3       replaces Manchester United's home kit (data3.big)
    data/sceneassets/kit0/kit_999001_0_0.rx3   a new file: added
```

Mods go on in name order; where two change the same file, the later one wins.

## How it works

The game asks for its files by name (`d:\data\db\fifa_ng_db.db`). It looks a name up in its archives first:
each `dataN.big` has a `dataN.bh` index of name hashes. When no index has the name, it opens the file loose
from the disc. Found at run time: with an index's hashes zeroed, the game asked for `d:\data\ui\lua\nav.lreq`
loose. Every normal boot also asks for a few loose files no archive has: league logo `l-1.dds`, player
picture `p-1.dds`, `data\loc\eng_us_upd.db`, `dlc\...\info.dlc`.

So a mod's file is used as follows:

- **A new file**, in no archive, is found loose.
- **A file an archive has** is found loose once that archive's index loses its entry. The entry is found by
  its offset in the archive's own table of names, so the index's hash function needn't be known. It isn't
  known yet: not FNV-1/1a 32/64 under any seed, CRC-32, djb2, sdbm or x65599, of the path in any case, slash
  or prefix. `sub_8267FCC8`, the game's FNV-1 64, isn't called at boot.

`tools/modding/modgame.py build` makes the modded game: a folder of links to the game's files and folders and to
the mods' files, plus the rewritten indexes. It takes no space to speak of. The launcher builds it in
`Application Support/FIFA 19/Modded Game` at each start and runs the game from it (`--game_data_root`).

`data/loc/locale.big`, the game's text, has no index (the game reads its table of names), so its files can't
be replaced this way; the text has its own way in (Strings, below).

## The database

Players, teams, leagues, kits' colours, squads and transfers (`teamplayerlinks`) are in
`data/db/fifa_ng_db.db`, described by `fifa_ng_db-meta.xml` (EA's t3db, big-endian on the Xbox 360). The format
is written up in `tools/modding/fifadb.py`. A rebuilt database with nothing changed is byte for byte the
original (`fifadb.py check`).

```bash
sh tools/modding/db.sh export
```

That writes every table to `out/mod/csv/<table>.csv`, 114 of them. Copy the ones to change to a folder of their
own and edit them in a spreadsheet or a script, then:

```bash
sh tools/modding/db.sh mod my-csv "$HOME/Library/Application Support/FIFA 19/Mods/My squads"
```

Checked: every Manchester United player given number 99 in `teamplayerlinks.csv` wears 99 in a quick match.

Tables worth knowing:

| Table | What |
|---|---|
| `players` | one row per player: ratings, positions, looks (`headtypecode`, `hairtypecode`...), boots (`shoetypecode`), `firstnameid`/`lastnameid` into `playernames` |
| `playernames` | names (Huffman-coded in the file; plain text in the CSV) |
| `teams` | clubs and national teams: name, ratings, colours, stadium, tactics |
| `teamplayerlinks` | squads: who plays for whom, shirt numbers, positions; transfers are rows moved between teams |
| `leagues`, `leagueteamlinks` | leagues and which teams are in them |
| `teamkits` | kit colours and styles per team |
| `teamstadiumlinks`, `stadiums` | grounds |

## Strings

The game's text (team, league, player and stadium names, menus, news) is `data/loc/<language>.db` in
`locale.big`: one table, `LanguageStrings`, of string ids (`TeamName_11`, `TeamName_Abbr3_11`,
`LeagueName_13`...), their text and the id's hash, which the game looks a string up by. Beside it the game
opens `data/loc/<language>_upd.db` with `<language>_upd-meta.xml` when they are there, and takes a string from
it first. So an update needs only the strings it changes or adds.

A mod gives its strings as `strings/<language>.csv` (`eng_us`, `rus_ru`, `pol_pl`, `ara_sa`):

```
stringid,text
TeamName_11,Macintosh United
TeamName_Abbr3_11,MAC
TeamName_Abbr15_11,Macintosh Utd
```

The mods' strings go into one update per language when the game starts (later mods win). To find a string's
id:

```bash
sh tools/modding/db.sh strings
```

That writes `out/mod/strings-eng_us/LanguageStrings.csv`. Checked: the scoreboard reads MAC 0-0 MTL and the
line-up card MACINTOSH UTD.

What it took:

- **Name.** The update's meta must name its database `<language>_upd` (`sub_8382A8A0` opens it under that name).
  With the base's name the game crashes.
- **Hash.** The id's hash is CRC-32's table over the id's bytes with bit 5 cleared (upper case), from 0
  and without the final inversion (`sub_826191D8`). `fifadb.string_hash` computes it, so new ids work too.
  It matches 43,922 of the 43,935 English strings.

## Assets

All in `data/sceneassets` (RX3 files: models with their textures), named by id:

| What | Files |
|---|---|
| kits | `kit0` home, `kit1` away, `kit2` third, `kit` goalkeeper: `kit_<teamid>_<kind>_0.rx3` |
| faces and heads | `faces/face_<playerid>_..._textures.rx3`, `heads/head_<playerid>_0_0.rx3`, `hair/`, `hairlod/` |
| boots | `shoe/shoe_<id>_<colour>_textures.rx3` (477) |
| crests, flags, banners | `crest/`, `flag/`, `banner/`; in the menus `data/ui/imgassets/crest/l<teamid>.dds` |
| balls, gloves, numbers | `ball/`, `gkglove/`, `kitnumbers/` |

`modgame.py list data3.big` lists an archive and `modgame.py extract` takes a file out as stored. Most are
`chunkzip` or `chunklzx` (EA's chunked deflate or Xbox LZX): `out/tools/unchunk`, built by
`sh tools/modding/build.sh`, unpacks them. Loose files can be plain (the database is). RX3 editing is MOD2.

### PC kit mods

The PC game's kit packs are Frosty mods (`.fbmod`): Frostbite textures, BC1 and BC7, Oodle-compressed.
`tools/modding/fbkits.py` makes them the Xbox's, for the mods `leagues/kits.json` lists (git-ignored, in
`tools/modding/sources`), later ones winning:

- **Kits.** The PC kit's jersey (1024², the same layout as the Xbox's), shorts and socks (the PC's separate
  textures, put in the Xbox's 1024×512 sheet: shorts left, the socks' two panels right) and crest go into the
  game's own RX3 for that team, kind and number (`kit0`...`kit2`, `kit`), each mip encoded again (DXT1/DXT5,
  Pillow) and byte-swapped. A team without that kit in the game gets one on the game's first team's RX3.
- **Menu pictures.** `data/ui/imgassets/kits0`...: the jersey's front and sleeves on a shirt's silhouette (the
  game's own), shaded by its folds with the sponsor and crests filtered out.
- **Crowd flags and banners** (`flag_<team>.rx3`, four 128² textures; `banner_<team>.rx3`).
- **Teams.** EA keeps team ids from game to game, so a mod's ids are this game's; a mod that puts a club in
  another's slot (the RPL pack: Zenit in 111285) is mapped in `kits.json`, and its slots without a club here are
  skipped. Clubs the update made (from 125000) are found by name.
- **Not convertible.** Boots, gloves and balls are Frostbite meshes, a different model from the Xbox's; the game
  has no player pictures for minifaces. The far-distance kit textures stay the game's.

`fbmod.py` reads the mods (`list`, `info`, `extract`), `fbtex.py` their textures, `rx3.py` the game's (`list`,
`png`). Oodle has no open encoder, but powzix's ooz decodes it: `build_ooz.sh` builds it for x86_64 (its SSE),
run under Rosetta.

## Competitions

Leagues, cups and their seasons are text files in
`dlc/dlc_footballcompeng/dlc/footballcompeng/data/compdata` (data1.big): `compobj.txt` (the tree of
competitions), `settings.txt`, `schedule.txt`, `advancement.txt`, `initteams.txt`, `standings.txt`,
`tasks.txt`, `weather.txt`, `compids.txt`. `tools/modding/compdata.py` describes each file's columns.

## A new league

```bash
sh tools/modding/build_league.sh rus
```

That builds the Russian Premier League as a mod in `out/mods/rus`, from `tools/modding/leagues/rus.json`.
Put the folder (or a link to it) in the Mods folder. The steps:

1. **Source.** `tools/modding/sources/espn.py` fetches the current squads, the table and every player's
   season statistics from ESPN's public JSON API (paced, cached in `out/moddata/espn`). SoFIFA answers
   automated clients with a CAPTCHA, which these tools don't get around. ClubElo was down.
2. **Database.** `tools/modding/league.py` adds the league, its 16 clubs and their squads:
   - **Players the game has**, matched by name and birth date (44 here), keep their id: face, hair, boots.
     Their ratings move to today's by age and playing time.
   - **New players** (444) are rated from:
     - the club's strength (the table);
     - their share of the club's minutes;
     - goals and assists for attackers.
   - **New players' attributes** come from the game's players of the same position and rating, their
     looks from a generic-head player of their nationality, and their stronger foot from the shots they
     took.
   - **Birth dates** move back 8 years, as the game's calendar starts in 2018 (the update's last step moves the
     calendar and every date forward again: below).
   - **Clubs** get numbers, a line-up, captain and kickers, prestige and budget.
   - **Clubs the game already has** (CSKA, Lokomotiv, Spartak in Rest of World) keep their ids, kits and
     crests. Their old players go to Free Agents.
   - **Career needs** referees, board objectives and the `competition` row (the league's ball). Those are
     added too.
3. **Assets.** `tools/modding/teamassets.py` makes:
   - the menus' crests from the clubs' logos, in all sizes;
   - the league's logo (`imgassets/league*`, `leaguelogos_*`);
   - kits, for now copied from a club with the nearest home colours.
4. **Competition.** `tools/modding/compdata.py` adds the country, league, stage and group:
   - cloned from Turkey's, as a 30-round double round robin with no European places;
   - placed after the last UEFA country, so every id after it moves up in every file. When the block was
     appended after the last id instead, Career's fixtures screen listed another competition's matches.

What the game needs that isn't in the files:

- **League tiers.** The game sorts its leagues into six hard-coded tiers (`sub_82C76400`), and most callers
  index a table with the result unchecked. A league in no tier crashes Career, at the start and when the
  season is simulated. `src/mod_support.cpp` gives a league the game doesn't have tier 3, Europe's other
  first divisions (`fifa19_mod_league_tier`). The game's own untiered leagues (Rest of World,
  International, Free Agents...) stay as they are.
- **Scouting regions.** A new Career sets up its scouts by the region of its league's country: the first of nine
  hard-coded lists of nations that has it (`sub_82D826F8`; England, Scandinavia and Russia are region 2), used
  unchecked (`sub_82DAD6E0`). A league in a country of none (Rest of World, Wales) never finished loading a
  Career. `src/mod_support.cpp` gives such a country region 2 (`fifa19_mod_scout_region`).
- **Ids in use.** Team ids from 120000: Russia's 120000 on, the Legends' 121000 on, new clubs 125000 on (130000 and 130001 already have crests). Player ids from 260000 (no
  face files there).

## How much the game takes

The meta's `maxinsert` is not a limit: the game boots and plays with 8,000 more players and links than its
tables have (`maxinsert` 3,282). What does limit it:

| What | Limit | Why |
|---|---|---|
| records in a table | 65,535 | the table's counts are 16-bit |
| player ids | 500,000 | 19 bits, the meta's range |
| team ids | 200,000 | 18 bits |
| league ids | 4,000 | 12 bits (so are the league-team links' keys: 4,095 links) |
| new names | 8,192 | `dcplayernames`, ids 34000-42191 (13 bits; the meta says 40000), 37 bytes each |
| names beyond those | any | `editedplayernames`: a player's names as text, as Edit Player keeps them (44 bytes each) |
| a club's squad | 33 kept | the game's own biggest; the PC game takes 51, but nothing needs more |
| free agents | 500 kept | the game has 250; an update's thousands are deleted, the best kept (and those also in a national team) |

**The names table** (`playernames`, Huffman-coded) stays as the game has it. Rewritten, it crashed the game at boot
(a null database handle in `sub_836C17A8`) for some contents and not others: the same table with three names
three letters longer booted. New names go to `dcplayernames` (as the PC game's updates add theirs), and past its
8,192 to `editedplayernames`. A name keeps to the characters the game's names use (`ț` as `t`, `ё` as `e`):
another crashed it too.

## The PC squads file and the Legends

```bash
sh tools/modding/build_update.sh ~/Downloads/Sostavy_na_25042026/Squads20260425161423
```

A community squads update for the PC game (a squads save, `Squads<date>`) has today's ratings and squads of a
year the game never had. `tools/modding/pcsquads.py` reads it into this game's database (`leagues/pc2026.json`).

- **The file.** The PC game's database, little-endian, its tables with their spare records (players: 26,000, of
  which 18,439 used), without the names table: names are ids into the PC game's own (put to text through the
  players both games have), plus the file's new ones (`dcplayernames`) and edited players' (`editedplayernames`).
  A few young players' names are only in the PC game's table: ESPN's player born that day of that nation names
  them, else the game's own names for the nation (as it names its youth players).
- **Who is who.** The update reuses ids: 4,154 of the game's ids are someone else now (the game's Lafferty is the
  update's Woltemade). The same id and birth date is the same player (his face kept); another birth date is
  someone new with a generic head. Updates make young players older (a 2003 birthday as 2002): later steps take
  ESPN's date.
- **Ratings and squads.** Ratings, attributes, positions, work rates, height and weight from the file; squads and
  numbers for the 641 clubs and national teams it has as themselves. Line-ups are picked again for the game's
  formations. The clubs the update lent to others (Russia's in Ireland's and Norway's, Como in Brescia...) keep
  their own players; the guests go to free agents, where later steps find them.
- **Legends.** The update's MLS holds the 2010s squads of 23 great clubs (Arsenal in Chicago Fire, Barcelona in
  Colorado...). They become the Legends League (league 69, Rest of World): new teams (from 121000) with the
  clubs' kits, crests, flags, banners and grounds, and the players as the game has them, in 2018, the decade they
  stand for. A legend still playing today (Messi, Ronaldo, Neymar: 162) stays himself at his club, his 2018 self
  copied to a new id with his head, face and hair files. Legends referees (Collina, Webb...). The league has no
  competition, so it is Kick Off's (and the game's other one-off matches'), not Career's: Career lists only the
  leagues compdata has, as it leaves out Rest of World, and its AI buys only from the leagues `transfers.ini`
  lists, so neither the clubs nor their players are in a Career's leagues or transfers.

## The FC 27 ratings

`tools/modding/fc27.py` takes an FC 27 player dump (EA's public ratings, 12 September 2026: players.csv, one row a
player, put in `tools/modding/sources/stats-dump`, git-ignored) as the last word on ratings:

- **Who.** EA keeps a player's id from game to game: the same id and birthday (the year within one) is the same
  player (4,051 of the game's own); else name and birthday, as the other steps match.
- **What.** The overall, the 33 attributes the game has (FC's defensive awareness as marking; composure it
  hasn't), positions (main and up to three more), foot, skill moves, weak foot. The potential stays when higher
  (young players), else follows the age. The dump has no heights.
- **Squads ESPN hasn't.** `leagues/fc27.json`'s leagues (3. Liga, Ekstraklasa, Ireland, Korea) get the dump's
  squads: a club is the game's team of that name or, in that league, the one most of its players are in.
  Clubs the game hasn't are made (below), with the colours `fc27.json` gives them and a drawn crest.

## League sizes

A league's size is its competition's: compdata's standings give each group its places, which a `FillFromLeague`
task fills from the database's league, and the schedule has the rounds for that many. Leagues with more clubs
today than the game's 2018 (MLS 30 for 23, Argentina 30 for 26, Brazil's Série B, Chile, Colombia...), or fewer
(the Bundesliga's 2. and 3. Liga as 18), are listed in `world.json`'s (and `fc27.json`'s) `resize`:
`compdata.py resize` gives their groups today's places (from the clubs the steps put in the league; MLS's two
conferences split by longitude) and the rounds that many need, its match days spread over the season again.
The rest keep the game's sizes: a division gets ESPN's clubs up to its places.

## New clubs

In a league whose size stays (most of them), a club the game hasn't (Wrexham, Elversberg, Como) comes in only as
one of the game's leaves; in a resized one, in a place of its own. `tools/modding/clubs.py` makes it in the place of a club its division's source doesn't
list (the weakest such): that club's row is the template (level, prestige, budget, tactics), and it goes to Rest
of World, as the game keeps clubs it has no league for (playable, out of Career's leagues). The new club's kits are
a club's of the nearest colours, its crest its logo (ESPN's), or its initials on a shield in its colours; ids from
125000. `squads.py` makes ESPN's (121 for 2026/27: Wrexham for Scunthorpe in the Championship); `fc27.py` the
dump's. A club ESPN names differently from the game is given by id in `world.json`'s `team_ids` (LAFC,
Basaksehir), else it would be made twice.

## The calendar

The game's Career starts on 1 July 2018. `tools/modding/calendar_shift.py` moves it to 2026:

- **Career's first day** is `CALSTART_YEAR` in `footballcompeng/data/cmsettings.ini` (2018), not the competitions:
  moving compdata's years alone left Career in July 2018.
- **The competitions' years** (`schedule_year_start`) move 8 years, so the tournaments every four years keep
  theirs (2030's World Cup as 2022's). The match days stay as written for 2018: `schedule_year_real` tells the
  game which year they are for, and it moves them to the same weekday.
- **The tournaments' stadiums** (`internationals.txt`) run to 2030 and 2032 in the game; they repeat after the
  years their lists cover.
- **Every date in the database** moves 8 years: the update's players, whose births the steps keep 8 years back
  (as the game's 2018 needed), get their real ones; the Legends stay the age they were in their decade.

## The whole update

Each mod's database replaces the game's whole, so a league and the squads must be built together:
`tools/modding/build_update.sh` makes one mod, `out/mods/update`:

1. the PC squads file, when given (above);
2. today's squads from ESPN (`squads.py`, `leagues/world.json`), with promotion and relegation: each division
   gets the clubs ESPN has in it (82 moves for 2026/27: Sunderland, Leeds, Coventry and Hull up, Wolves, Burnley,
   West Ham down...), its size kept; the clubs the game hasn't are made (above);
3. the leagues the game hasn't (`league.py`: Russia's);
4. the FC 27 ratings and the squads ESPN hasn't (`fc27.py`), when the dump is there;
5. kits, crests, logos, the legends' copied heads (`teamassets.py`), the competitions (`compdata.py`: the new
   leagues', and the resized);
6. the PC kit mods' kits, menu pictures, flags and banners (`fbkits.py`), when they are there;
7. the free agents kept to the best 500 (`freeagents.py`);
8. the calendar, 8 years on (`calendar_shift.py`).

A player the file rated keeps its ratings in the ESPN steps; they only move him to his club. Matching ESPN's
players to the game's: name and birth date, the birth year within three, a near spelling (the update's
Branthwate), and within a club its own players by birthday. The Legends' clubs have no transfer budget, so
Career's AI doesn't buy for them.

## Tools

| Tool | What |
|---|---|
| `tools/modding/modgame.py` | `build`: the modded game; `list`, `extract`: archives |
| `tools/modding/db.sh` | the database to CSV, and CSV to a mod; the game's text to CSV (`strings`) |
| `tools/modding/build_update.sh` | the whole update as one mod: the PC squads file, ESPN's squads, new leagues |
| `tools/modding/pcsquads.py` | a PC squads file's ratings, squads and Legends League |
| `tools/modding/squads.py`, `build_squads.sh` | today's squads and divisions from ESPN (alone: `out/mods/world`) |
| `tools/modding/fc27.py` | an FC 27 dump's ratings, and its squads for the leagues ESPN hasn't |
| `tools/modding/clubs.py` | new clubs in the places of those that leave (for `squads.py` and `fc27.py`) |
| `tools/modding/calendar_shift.py` | the calendar 8 years on: Career from July 2026 |
| `tools/modding/freeagents.py` | the free agents kept to the best 500 |
| `tools/modding/compdata.py` | the competitions: `add` a league, `resize` leagues to today's clubs |
| `tools/modding/fbkits.py` | PC kit mods (`leagues/kits.json`) to the game's kits, menu pictures, flags, banners |
| `tools/modding/fbmod.py`, `fbtex.py` | Frosty mods: `list`, `info`, `extract`; their textures as images |
| `tools/modding/rx3.py` | the game's RX3 textures: `list`, `png` |
| `tools/modding/build_ooz.sh` | `out/tools/ooz-x86`, the Oodle decoder `fbmod.py` uses |
| `tools/modding/fifadb.py` | the database format: `info`, `export`, `import`, `check`; the locale's string hash and update files |
| `tools/modding/unchunk.c` | chunkzip/chunklzx entries to plain bytes |
| `scripts/run_app.sh --game DIR` | a test run from another game folder, such as a modded game built by hand |

References: Rx3Tools (FIFA 12-16 PC RX3 models), [FrostyToolsuite](https://github.com/CadeEvs/FrostyToolsuite)
(Frostbite FIFA 17 on PC: a different engine, but its type names help), [soccerdata](https://github.com/probberechts/soccerdata)
(SoFIFA ratings for MOD3).
