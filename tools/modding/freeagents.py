#!/usr/bin/env python3
"""Keeps the free agents to a pool like the game's own: the best MAX (500 by default), the rest deleted.

  freeagents.py CSVDIR [MAX]

An update leaves many players without a club: those today's squads no longer list (loans, moves to leagues the
game hasn't, retirements) and the old squads' leftovers. The game has 250 free agents (the PC update 49); a club
of thousands is far past anything it was made with. Every player must be in a club, so the ones not kept are
deleted, with every row that refers to them (links, loans, previous teams, grudges). Players also in a national
team or one of the game's special squads (training, factory) stay. The tables change in place in CSVDIR.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import league as fifa  # noqa: E402

FREE_AGENTS = '111592'
REFERS = {'teamplayerlinks': 'playerid', 'playerloans': 'playerid', 'previousteam': 'playerid',
          'player_grudgelove': 'playerid', 'editedplayernames': 'playerid'}


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    csvdir, keep = argv[1], int(argv[2]) if len(argv) > 2 else 500
    t = {name: fifa.read(os.path.join(csvdir, name + '.csv'))
         for name in ['players', 'teams', 'trainingteamplayers', 'factory_teams'] + list(REFERS)}
    special = {x['playerid'] for x in t['trainingteamplayers']}
    for row in t['factory_teams'] + t['teams']:
        special |= {row[k] for k in row if k.endswith('takerid') or k == 'captainid'}
    elsewhere = {x['playerid'] for x in t['teamplayerlinks'] if x['teamid'] != FREE_AGENTS}
    players = {p['playerid']: p for p in t['players']}
    free = [x['playerid'] for x in t['teamplayerlinks'] if x['teamid'] == FREE_AGENTS]
    stay = {pid for pid in free if pid in elsewhere or pid in special}
    ranked = sorted((pid for pid in free if pid not in stay and pid in players),
                    key=lambda pid: (-int(players[pid]['overallrating']), int(pid)))
    gone = set(ranked[max(0, keep - len(stay)):])
    if not gone:
        print(f'free agents: {len(free)}, none deleted')
        return 0
    t['players'] = [p for p in t['players'] if p['playerid'] not in gone]
    for name, col in REFERS.items():
        t[name] = [x for x in t[name] if x[col] not in gone]
    for name in ['players'] + list(REFERS):
        if t[name]:
            fifa.write(os.path.join(csvdir, name + '.csv'), t[name])
    print(f'free agents: {len(free) - len(gone)} kept of {len(free)}; {len(gone)} players deleted')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
