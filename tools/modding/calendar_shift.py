#!/usr/bin/env python3
"""Moves the game's calendar on by YEARS (8: Career starts in July 2026, season 2026/27, not 2018/19).

  calendar_shift.py YEARS CSVDIR [COMPDATADIR [GAMEDIR]]

Every date in the tables moves by YEARS, so everyone stays as old as the steps before made him:
- the update's players, whose births those steps moved back by age_shift_years (8) so that the game's 2018 made
  them as old as today, get their real birth dates back;
- the Legends stay the age they were in the 2010s they stand for; the game's own players and referees no update
  had stay as the game had them;
- contracts (a year), the day a player joined his club, the end of a loan move with them.
COMPDATADIR (the mod's compdata: Career's settings go beside it): the competitions keep the game's years. Their
fixtures are drawn for a season from its first year (schedule_year_start, the root's 2017: Career's first season
2018) and their match days (day numbers, moved to the same weekday in the year played); with those years moved on
too, the leagues whose season spans two years (England's, Germany's...: every one but the calendar year's, MLS's)
were drawn no fixtures at all in 2026/27, and a Career started before 1 July (MLS's) faulted when their season
began. Kept, the game simply plays its ninth season of them in 2026/27: YEARS must be a multiple of 4, so the
tournaments every four years (2026's World Cup as 2018's) keep their years. The real fixture lists of 2018
(compdata/schedules, schedule_year_real) are 2018's only, so 2026's are drawn from the clubs the leagues have.
GAMEDIR (with COMPDATADIR): Career's own settings, written beside compdata (as the mod's): its calendar's first
day (cmsettings.ini.patch: CALSTART_YEAR, 2018 in the game, what Career's first day is, not the competitions; and
CALSTART_MONTH, July for every league), and the
stadiums of the tournaments every four years (internationals.txt: the game's run to 2030 and 2032, so later ones
repeat them, each after the years its list covers).
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import league as fifa  # noqa: E402

DATES = {'players': ['birthdate', 'playerjointeamdate'], 'playerloans': ['loandateend'], 'referee': ['birthdate'],
         'physio': ['birthdate'], 'trainingteamplayers': ['birthdate', 'playerjointeamdate']}
YEARS = {'players': ['contractvaliduntil'], 'trainingteamplayers': ['contractvaliduntil']}
def moved(n, years):
    return str(fifa.days(fifa.shifted(fifa.from_days(n), -years)))


def tables(csvdir, years):
    changed = []
    for name in sorted(set(DATES) | set(YEARS)):
        path = os.path.join(csvdir, name + '.csv')
        if not os.path.exists(path):
            continue
        rows = fifa.read(path)
        for row in rows:
            for f in DATES.get(name, []):
                if row.get(f, '').isdigit() and int(row[f]) > 0:
                    row[f] = moved(row[f], years)
            for f in YEARS.get(name, []):
                if row.get(f, '').isdigit() and int(row[f]) > 1900:
                    row[f] = str(int(row[f]) + years)
        if rows:
            fifa.write(path, rows)
            changed.append(name)
    return changed


def career(game, data, years):
    """cmsettings.ini and internationals.txt, from the game, into data (the mod's footballcompeng/data)."""
    import re
    import subprocess
    import modgame
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    unchunk = os.path.join(root, 'out', 'tools', 'unchunk')
    inside = 'dlc/dlc_footballcompeng/dlc/footballcompeng/data/'
    out = {}
    for name in ('cmsettings.ini', 'internationals.txt'):
        target = os.path.join(data, name)
        modgame.main(['modgame.py', 'extract', os.path.join(game, 'data1.big'), inside + name, target + '.stored'])
        subprocess.run([unchunk, target + '.stored', target], check=True, stdout=subprocess.DEVNULL)
        os.unlink(target + '.stored')
        out[name] = open(target, 'rb').read()
    # Career's first day, as a patch of cmsettings.ini (modgame.py: only these keys, so a mod changing others of
    # Career's settings goes on beside it). Every Career from 1 July (the game's: 1 January, so a calendar year's
    # league, MLS's, began in February): with the competitions in the game's years, a Career begun before July has
    # no state for Europe's season then under way, and the game stopped itself (a fatal error) on 1 August.
    year = re.search(rb'CALSTART_YEAR\s*=\s*(\d+)', out['cmsettings.ini'])
    if not year:
        raise SystemExit('cmsettings.ini: no CALSTART_YEAR')
    os.unlink(os.path.join(data, 'cmsettings.ini'))
    open(os.path.join(data, 'cmsettings.ini.patch'), 'w', newline='\r\n').write(
        '[DEFAULTS]\nCALSTART_DAY = 1\nCALSTART_MONTH = 7\n'
        f'CALSTART_YEAR = {int(year.group(1)) + years}\n')
    text = out['internationals.txt']
    eol = b'\r\n' if b'\r\n' in text else b'\n'
    lines = text.split(eol)
    row = re.compile(rb'^(\d+),(\d{4}),(\w+),(\d+)\s*$')
    rows = [m.groups() for m in map(row.match, lines) if m]
    extra = []
    for comp in sorted({r[0] for r in rows}):
        mine = [r for r in rows if r[0] == comp]
        first, last = min(int(r[1]) for r in mine), max(int(r[1]) for r in mine)
        span = last - first + 4  # the years a four-yearly list covers (16 for 2018-2030), repeated after it
        for step in range(span, 2018 + years + 40 - first + span, span):
            extra += [(comp, str(int(r[1]) + step).encode(), r[2], r[3]) for r in mine
                      if last < int(r[1]) + step <= 2018 + years + 40]
    at = max(i for i, line in enumerate(lines) if row.match(line)) + 1
    lines[at:at] = [b','.join(r) for r in sorted(extra, key=lambda r: (r[0], int(r[1])))]
    text = eol.join(lines)
    open(os.path.join(data, 'internationals.txt'), 'wb').write(text)
    return len(extra)


def main(argv):
    if len(argv) not in (3, 4, 5):
        print(__doc__, file=sys.stderr)
        return 2
    years = int(argv[1])
    if years % 4:
        raise SystemExit('YEARS: a multiple of 4 (the tournaments every four years keep their years)')
    changed = tables(argv[2], years)
    msg = f"calendar: {years} years on ({', '.join(changed)})"
    if len(argv) > 4:
        msg += f'; Career from {2018 + years}, {career(argv[4], os.path.dirname(argv[3].rstrip("/")), years)} ' \
               'tournament stadiums more'
    first = datetime.date(2018 + years, 7, 1)
    print(msg + f'; Career starts {first:%B %Y}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
