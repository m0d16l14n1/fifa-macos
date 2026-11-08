#!/usr/bin/env python3
"""Adds a league to the game's competitions (Career mode's seasons; the Football Competition Engine's text files in
dlc/dlc_footballcompeng/dlc/footballcompeng/data/compdata, in data1.big).

  compdata.py add SRCDIR OUTDIR CONFIG.json LEAGUE.json

SRCDIR: the game's compdata files (unpacked). The new country, its league, stage and group go after the last
country of the template's confederation (the ids after them move up, in every file), cloned from CONFIG's template league (compdata.template_nation /
template_league: Turkey's by default) and fitted to the league's team count: a double round robin (with an odd
count, a rest for one team each round), its schedule the template's match days (rounds beyond the new league's
dropped; more rounds than the template's spread over its season), its table, its start and end of season tasks
(fill from the database's league, update stats).

The files (all comma separated, ids are compobj.txt's first column):
  compobj.txt     id, level (0 root, 1 confederation, 2 country, 3 competition, 4 stage, 5 group), code, name
                  string, parent id
  settings.txt    id, key, value (a few values are ids: rule_suspension)
  schedule.txt    stage id, day (of the season's first year; past 365 into the next), round, the fewest and the
                  most of the round's matches played that day, kick-off time
  standings.txt   group id, position
  tasks.txt       id, start|end, action, ids and the database's league id
  weather.txt     country id, month, clear %, rain %, snow %, overcast %, sunset start, sunset end
  initteams.txt   competition id, slot, team id
  compids.txt     the competitions' ids
"""
import json
import os
import sys

FILES = ['compobj', 'settings', 'schedule', 'standings', 'tasks', 'weather', 'initteams', 'compids',
         'advancement', 'activeteams', 'dataver']


def load(src):
    out = {}
    for name in FILES:
        path = os.path.join(src, name + '.txt')
        text = open(path, encoding='utf-8', newline='').read() if os.path.exists(path) else ''
        out[name] = [line.split(',') for line in text.replace('\r\n', '\n').split('\n') if line]
    return out


def save(files, out, crlf):
    os.makedirs(out, exist_ok=True)
    for name, rows in files.items():
        text = (('\r\n' if crlf else '\n').join(','.join(r) for r in rows)) + ('\r\n' if crlf else '\n')
        open(os.path.join(out, name + '.txt'), 'w', encoding='utf-8', newline='').write(text)


# Columns that hold compobj ids, by file (and for tasks, by action; for settings, by key).
TASK_ID_ARGS = {'FillFromCompTable': (3, 4), 'FillFromCompTableBackup': (3, 4, 5),
                'FillFromCompTableBackupLeague': (3, 4), 'UpdateTable': (3, 4)}
SETTING_ID_KEYS = {'rule_suspension', 'advance_maxteamsstageref', 'advance_teamcompdependency',
                   'schedule_forcecomp', 'schedule_use_dates_comp', 'advance_pointskeep', 'advance_standingskeep',
                   'advance_standingsrank', 'standings_checkrank'}


def renumber(f, shift):
    """Applies shift (old id -> new id) to every id in the files."""
    for r in f['compobj']:
        r[0], r[4] = str(shift(int(r[0]))), str(shift(int(r[4]))) if int(r[4]) >= 0 else r[4]
    for name in ('settings', 'schedule', 'standings', 'weather', 'initteams', 'compids'):
        for r in f[name]:
            r[0] = str(shift(int(r[0])))
    for r in f['settings']:
        if r[1] in SETTING_ID_KEYS and r[2].isdigit():
            r[2] = str(shift(int(r[2])))
    for r in f['advancement']:
        r[0], r[2] = str(shift(int(r[0]))), str(shift(int(r[2])))
    for r in f['tasks']:
        r[0] = str(shift(int(r[0])))
        for col in TASK_ID_ARGS.get(r[2], (3,)):
            if r[col].lstrip('-').isdigit() and int(r[col]) > 0:
                r[col] = str(shift(int(r[col])))


def add(src, out, cfg, league):
    comp = cfg['compdata']
    f = load(src)
    crlf = '\r\n' in open(os.path.join(src, 'compobj.txt'), encoding='utf-8', newline='').read(200)
    obj = {int(r[0]): r for r in f['compobj']}
    t_nation, t_league = comp['template_nation'], comp['template_league']
    t_stage = next(i for i, r in obj.items() if int(r[4]) == t_league and r[1] == '4')
    t_group = next(i for i, r in obj.items() if int(r[4]) == t_stage and r[1] == '5')
    t_db_league = int(next(r[2] for r in f['settings'] if int(r[0]) == t_league and r[1] == 'asset_id'))
    # The new country goes after the last of its confederation's (the game expects competitions in their
    # confederation's run of ids: appended after the last one, Career's fixtures listed another competition's).
    confederation = int(obj[t_nation][4])
    def ancestors(i):
        while i > 0:
            i = int(obj[i][4])
            yield i
    at = max(i for i in obj if i == confederation or confederation in ancestors(i)) + 1
    added = 4
    renumber(f, lambda i: i + added if i >= at else i)
    nation, lg, stage, group = at, at + 1, at + 2, at + 3
    ids = {t_nation: nation, t_league: lg, t_stage: stage, t_group: group}
    # The template's own ids moved too when they came after the insertion point.
    ids = {(k + added if k >= at else k): v for k, v in ids.items()}
    t_nation, t_league, t_stage, t_group = (k + added if k >= at else k for k in (t_nation, t_league, t_stage, t_group))
    obj = {int(r[0]): r for r in f['compobj']}
    db_league, teams = cfg['league_id'], [t['teamid'] for t in league['teams']]
    n = len(teams)
    rounds = 2 * (n if n % 2 else n - 1)  # an odd count: each round one team rests (Serie B's 19)
    new = {k: [] for k in f}

    new['compobj'] += [[str(nation), '2', comp['nation_code'], f"NationName_{cfg['nation_id']}", str(confederation)],
                       [str(lg), '3', f'C{db_league}', f'TrophyName_Abbr15_{db_league}', str(nation)],
                       [str(stage), '4', 'S1', obj[t_stage][3], str(lg)],
                       [str(group), '5', 'G1', ' ', str(stage)]]
    for r in [r for r in f['settings'] if int(r[0]) in ids]:
        key, value = r[1], r[2]
        if key in ('uefa_seeded_slots',) or key.startswith('info_color_slot_euro') or key == 'info_color_slot_champ_cup':
            continue  # no European places
        if key == 'nation_id':
            value = str(cfg['nation_id'])
        elif key == 'asset_id':
            value = str(db_league)
        elif key in SETTING_ID_KEYS and value.isdigit():
            value = str(ids.get(int(value), int(value)))
        elif key == 'schedule_year_real':
            # The template's real fixture list (schedules/c<league>_s1_<year>.txt); the new league has none, so its
            # fixtures are made from schedule.txt's slots (as for leagues without one: Poland's).
            continue
        new['settings'].append([str(ids[int(r[0])]), key, value])
    for pos in range(n):
        new['standings'].append([str(group), str(pos)])
    for r in [r for r in f['tasks'] if int(r[0]) in ids]:
        r = list(r)
        action = r[2]
        if action == 'UpdateTable' and int(r[5]) > n:
            continue
        r[0] = str(ids[int(r[0])])
        for col in TASK_ID_ARGS.get(action, (3,)):
            if r[col].lstrip('-').isdigit() and int(r[col]) in ids:
                r[col] = str(ids[int(r[col])])
        if action in ('FillFromLeague', 'ClearLeagueStats', 'UpdateLeagueStats') and int(r[4]) == t_db_league:
            r[4] = str(db_league)
        new['tasks'].append(r)
    # Schedule: a round's rows are its match days, each with the fewest and most of the round's matches played
    # that day. The template's rounds for as many as the league has; past those (more teams than the template's),
    # rounds spread evenly over the template's season, a Saturday-and-Sunday pair each.
    matches = n // 2
    # The match days: the template's, or another league's (compdata.schedule_from, a code such as C14: the
    # Championship's 49 rounds for a league with more than the template's).
    days_stage = t_stage
    if comp.get('schedule_from'):
        other = next(i for i, r in obj.items() if r[2] == comp['schedule_from'] and r[1] == '3')
        days_stage = min(i for i, r in obj.items() if int(r[4]) == other and r[1] == '4')
    by_round = {}
    for r in f['schedule']:
        if int(r[0]) == days_stage:
            by_round.setdefault(int(r[2]), []).append(r)
    if rounds <= len(by_round):
        for rnd in range(1, rounds + 1):
            rows = [list(r) for r in by_round[rnd]]
            left = matches
            for r in rows:
                r[3] = str(min(int(r[3]), left))
                left -= int(r[3])
            if sum(int(r[4]) for r in rows) < matches:
                rows[-1][4] = str(matches)
            new['schedule'] += [[str(stage), r[1], str(rnd), r[3], r[4], r[5]] for r in rows]
    else:
        first = min(int(r[1]) for r in by_round[min(by_round)])
        last = max(int(r[1]) for r in by_round[max(by_round)])
        for rnd in range(1, rounds + 1):
            day = first + round((last - 1 - first) * (rnd - 1) / (rounds - 1))
            new['schedule'] += [[str(stage), str(day), str(rnd), '1', str(matches), '1500'],
                                [str(stage), str(day + 1), str(rnd), '0', str(matches), '1700']]
    for r in [r for r in f['weather'] if int(r[0]) == t_nation]:
        w = comp.get('weather', {}).get(str(int(r[1])))
        new['weather'].append([str(nation), r[1]] + ([str(x) for x in w] if w else r[2:6]) + r[6:])
    for slot, tid in enumerate(teams):
        new['initteams'].append([str(lg), str(slot), str(tid)])
    new['compids'].append([str(lg)])
    for name, rows in new.items():
        if rows:  # into id order (the files are sorted by their first column; a stable sort keeps the rest)
            f[name] = sorted(f[name] + rows, key=lambda r: int(r[0]))
    save(f, out, crlf)
    return {'nation': nation, 'league': lg, 'stage': stage, 'group': group, 'rounds': rounds}


def main(argv):
    if len(argv) != 6 or argv[1] != 'add':
        print(__doc__, file=sys.stderr)
        return 2
    cfg = json.load(open(argv[4]))
    if 'compdata' not in cfg and 'compdata' in cfg.get('legends', {}):
        cfg = cfg['legends']  # pc2026.json: its Legends league
    league = json.load(open(argv[5]))
    made = add(argv[2], argv[3], cfg, league)
    print(f"compdata: country {made['nation']}, league {made['league']} (C{cfg['league_id']}), "
          f"{len(league['teams'])} teams, {made['rounds']} rounds")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
