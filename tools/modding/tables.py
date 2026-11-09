#!/usr/bin/env python3
"""Every league's table positions once each, 1 to its size: the game's own database has them so, and Career
reads them.

  tables.py CSVDIR

leagueteamlinks has each club's place in its league's table (currenttableposition) and the year before's
(previousyeartableposition). The steps that move clubs between leagues, and the clubs made for leagues grown
(clubs.py: a copy of a club's row), leave places twice or missing: MLS grown to 30 had eight clubs 15th and none
24th-30th. A Career that starts while such a league's year is under way (MLS, Argentina: seasons in the calendar
year, started from Career's first day) fills its table from these places, so the clubs on a place taken twice
were left out ("TBD"), no league match was played, and the play-offs later read clubs that weren't there (access
violations in the competition code). Here each league whose places aren't 1 to its size once each has its clubs
numbered again in their order (by place, then the other place, then the database's); the rest are left.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import league as fifa  # noqa: E402

COLUMNS = ('currenttableposition', 'previousyeartableposition')
# Leagues without a table: Rest of World (all its clubs 1st in the game), the national teams, the Legends'.
NO_TABLE = {'76', '78', '69'}


def renumber(links):
    """Returns how many leagues had their places changed."""
    by_league = {}
    for i, link in enumerate(links):
        by_league.setdefault(link['leagueid'], []).append((i, link))
    changed = 0
    for lid, rows in by_league.items():
        if lid in NO_TABLE or len(rows) < 2:
            continue
        if sorted(int(link[COLUMNS[0]] or 0) for _, link in rows) == list(range(1, len(rows) + 1)):
            continue  # as the game has them (its previous places can repeat, England's; Brazil's skip numbers)
        before = [tuple(link[c] for c in COLUMNS) for _, link in rows]
        for col, other in (COLUMNS, COLUMNS[::-1]):
            order = sorted(rows, key=lambda r: (int(r[1][col] or 0) or 999, int(r[1][other] or 0) or 999, r[0]))
            for place, (_, link) in enumerate(order, 1):
                link[col] = str(place)
        changed += before != [tuple(link[c] for c in COLUMNS) for _, link in rows]
    return changed


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = os.path.join(argv[1], 'leagueteamlinks.csv')
    links = fifa.read(path)
    changed = renumber(links)
    fifa.write(path, links)
    print(f'tables: {changed} leagues\' places numbered again')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
