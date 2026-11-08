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

Not covered: `data/loc/locale.big` has no index (the game reads its table of names), so its files can't be
replaced this way. Use `data/loc/eng_us_upd.db`, the update database the game looks for (MOD4).

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

## Competitions

Leagues, cups and their seasons are text files in
`dlc/dlc_footballcompeng/dlc/footballcompeng/data/compdata` (data1.big): `compobj.txt` (the tree of
competitions), `settings.txt`, `schedule.txt`, `advancement.txt`, `initteams.txt`, `standings.txt`,
`tasks.txt`, `weather.txt`, `compids.txt`. A new league is rows in the database (`leagues`,
`leagueteamlinks`, its teams, players and links), entries in these files, and its names in the locale
database (MOD1).

## Tools

| Tool | What |
|---|---|
| `tools/modding/modgame.py` | `build`: the modded game; `list`, `extract`: archives |
| `tools/modding/db.sh` | the database to CSV, and CSV to a mod |
| `tools/modding/fifadb.py` | the database format: `info`, `export`, `import`, `check` |
| `tools/modding/unchunk.c` | chunkzip/chunklzx entries to plain bytes |
| `scripts/run_app.sh --game DIR` | a test run from another game folder, such as a modded game built by hand |

References: Rx3Tools (FIFA 12-16 PC RX3 models), [FrostyToolsuite](https://github.com/CadeEvs/FrostyToolsuite)
(Frostbite FIFA 17 on PC: a different engine, but its type names help), [soccerdata](https://github.com/probberechts/soccerdata)
(SoFIFA ratings for MOD3).
