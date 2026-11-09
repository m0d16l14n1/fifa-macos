#!/usr/bin/env python3
"""Ratings from an FC 27 player dump (EA's public ratings, one row per player), and the squads of the leagues ESPN
hasn't, onto the game's database.

  fc27.py CONFIG.json CSVDIR FC27.csv OUTCSVDIR [PCSQUADS.json] [FIXED.json ...]

FC27.csv: the dump's players.csv (player_id, names, overall_rating, position, alternate_positions, club, league,
preferred_foot, skill_moves, weak_foot, birthdate DD-MM-YYYY, the 34 attributes...). The men's rows are used.

- Matching: the same EA id and birthday (EA keeps a player's id from game to game; updates give some ids to other
  people, so the birthday must agree, the year within one), else name and birthday as the other steps match.
- A matched player gets the dump's overall, attributes, positions, foot, skill moves and weak foot; his potential
  stays when higher (young players), else follows his age. His birth date becomes the dump's (moved back by
  age_shift_years like every birth date here).
- CONFIG's squad_leagues ({game league id: the dump's league name}): those leagues' clubs get the dump's squads
  (a club is the game's team whose players most of the dump's club are, or the nearest name, or CONFIG's
  club_ids: the dump's name to the game's team id, for a renamed club). Players the dump
  has that the game hasn't are made (league.py's new_player, with the dump's attributes).
- FIXED.json: reports of the steps before (squads.py's squads.json, league.py's league.json): their clubs' squads
  are newer than the dump's (ESPN's, today's), so their players stay where those steps put them.
Writes the changed tables to OUTCSVDIR and OUTCSVDIR/fc27.json (what was done).
"""
import collections
import csv
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import league as fifa  # noqa: E402
import squads  # noqa: E402

POSITIONS = {'GK': fifa.GK, 'RB': fifa.RB, 'CB': fifa.CB, 'LB': fifa.LB, 'CDM': fifa.CDM, 'RM': fifa.RM,
             'CM': fifa.CM, 'LM': fifa.LM, 'CAM': fifa.CAM, 'ST': fifa.ST, 'RW': fifa.RW, 'LW': fifa.LW,
             'CF': 21, 'RWB': 2, 'LWB': 8}
# The game's attribute: the dump's column.
ATTRIBUTES = {
    'crossing': 'attacking_crossing', 'finishing': 'attacking_finishing',
    'headingaccuracy': 'attacking_heading_accuracy', 'shortpassing': 'attacking_short_passing',
    'volleys': 'attacking_volleys', 'dribbling': 'skill_dribbling', 'curve': 'skill_curve',
    'freekickaccuracy': 'skill_fk_accuracy', 'longpassing': 'skill_long_passing', 'ballcontrol': 'skill_ball_control',
    'acceleration': 'movement_acceleration', 'sprintspeed': 'movement_sprint_speed', 'agility': 'movement_agility',
    'reactions': 'movement_reactions', 'balance': 'movement_balance', 'shotpower': 'power_shot_power',
    'jumping': 'power_jumping', 'stamina': 'power_stamina', 'strength': 'power_strength',
    'longshots': 'power_long_shots', 'aggression': 'mentality_aggression',
    'interceptions': 'mentality_interceptions', 'positioning': 'mentality_positioning',
    'vision': 'mentality_vision', 'penalties': 'mentality_penalties', 'marking': 'defending_awareness',
    'standingtackle': 'defending_standing_tackle', 'slidingtackle': 'defending_sliding_tackle',
    'gkdiving': 'goalkeeping_diving', 'gkhandling': 'goalkeeping_handling', 'gkkicking': 'goalkeeping_kicking',
    'gkpositioning': 'goalkeeping_positioning', 'gkreflexes': 'goalkeeping_reflexes'}


def born_of(row):
    try:
        d, m, y = map(int, row['birthdate'].split('-'))
        return datetime.date(y, m, d)
    except ValueError:
        return None


def athlete_of(row):
    """The row as the other steps' athletes (league.Builder.match, new_player)."""
    first, last = row['first_name'].strip(), row['last_name'].strip()
    shown = row['common_name'].strip() or f'{first} {last}'.strip()
    return {'id': 'fc' + row['player_id'], 'firstName': first, 'lastName': last, 'displayName': shown}


def same_day(p, born, shift):
    b = fifa.from_days(p['birthdate'])
    return any((b.month, b.day) == (w.month, w.day) and abs(b.year - w.year) <= 1
               for w in (born, fifa.shifted(born, shift)))


def apply(builder, p, row, born, today, shift):
    """The dump's player onto the game's row."""
    for ours, theirs in ATTRIBUTES.items():
        if row.get(theirs, '').isdigit():
            p[ours] = str(max(1, min(99, int(row[theirs]))))
    rating = int(row['overall_rating'])
    age = (today - born).days // 365
    p['overallrating'] = str(rating)
    p['potential'] = str(max(rating, builder.potential_for(rating, age),
                             int(p['potential']) if age < 24 else 0))
    p['potential'] = str(min(int(p['potential']), 95))
    main = POSITIONS.get(row['position'], fifa.CM)
    others = [POSITIONS[x] for x in row['alternate_positions'].split() if x in POSITIONS and POSITIONS[x] != main]
    for n, pos in enumerate([main] + others[:3] + [-1] * 3):
        if n < 4:
            p[f'preferredposition{n + 1}'] = str(pos)
    p['preferredfoot'] = '2' if row['preferred_foot'].lower().startswith('l') else '1'
    if row['skill_moves'].isdigit():
        p['skillmoves'] = str(max(0, min(4, int(row['skill_moves']) - 1)))
    if row['weak_foot'].isdigit():
        p['weakfootabilitytypecode'] = str(max(1, min(5, int(row['weak_foot']))))
    p['internationalrep'] = str(1 + (rating >= 74) + (rating >= 79) + (rating >= 84) + (rating >= 88))
    p['birthdate'] = str(fifa.days(fifa.shifted(born, shift)))


def main(argv):
    if len(argv) < 5:
        print(__doc__, file=sys.stderr)
        return 2
    cfg = json.load(open(argv[1]))
    csvdir, dump, outdir = argv[2], argv[3], argv[4]
    pcsquads = argv[5] if len(argv) > 5 and argv[5] != '-' else None
    fixed_reports = argv[6:]
    common = {'age_shift_years': 8, 'today': datetime.date.today().isoformat(), 'nation_id': 14,
              'free_agents_team_id': 111592, 'first_player_id': 260000}
    common.update(cfg)
    shift = common['age_shift_years']
    today = datetime.date.fromisoformat(common['today'])
    b = fifa.Builder(common, csvdir, None)
    b.use_pcsquads(pcsquads)
    b.changed = {'players', 'teamplayerlinks', 'teams', 'dcplayernames', 'editedplayernames', 'playerloans'}
    b.index_players()
    b.templates()
    b._feet = {}
    b.next_player = max(common['first_player_id'], max(b.players) + 1)

    rows = []
    with open(dump, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row.get('gender', '').startswith('Men') and row['overall_rating'].isdigit() and born_of(row):
                rows.append(row)
    rows.sort(key=lambda r: -int(r['overall_rating']))

    protected = {x['playerid'] for x in b.t['teamplayerlinks'] if x['teamid'] in b.protected}
    matched, taken = {}, set()
    by_id = 0
    for row in rows:
        born = born_of(row)
        p = b.players.get(int(row['player_id']))
        if p is not None and (p['playerid'] in protected or not same_day(p, born, shift)):
            p = None
        if p is None:
            p = b.match(athlete_of(row), born)
            if p is not None and p['playerid'] in protected:
                p = None
        else:
            by_id += 1
        if p is not None and p['playerid'] not in taken:
            taken.add(p['playerid'])
            matched[row['player_id']] = p
            apply(b, p, row, born, today, shift)

    # The squads of the leagues ESPN hasn't.
    fixed = set(map(str, b.protected))
    for path in fixed_reports:
        if os.path.exists(path):
            r = json.load(open(path))
            fixed |= {str(t['teamid']) for t in r.get('teams', [])}
    links = b.t['teamplayerlinks']
    national = {x['teamid'] for x in b.t['leagueteamlinks'] if x['leagueid'] in ('78', '2136')}
    club_of = {}
    for x in links:
        if x['teamid'] not in national:
            club_of.setdefault(x['playerid'], x['teamid'])
    teams = {x['teamid']: x for x in b.t['teams']}
    leagues = {x['leagueid']: x for x in b.t['leagues']}
    free_agents = str(common['free_agents_team_id'])
    next_key = max(int(x['artificialkey']) for x in links) + 1
    report_clubs, made = [], 0
    import clubs as clubs_mod
    made_clubs = clubs_mod.Clubs(b)
    for league_id, dump_league in common.get('squad_leagues', {}).items():
        league_id = str(league_id)
        country = leagues[league_id]['countryid']
        country_leagues = {lid for lid, x in leagues.items() if x['countryid'] == country}
        in_league = {x['teamid'] for x in b.t['leagueteamlinks'] if x['leagueid'] == league_id}
        # The country's clubs, and those of Rest of World (a club an earlier step sent there may be back).
        row_nation = {x['teamid']: x['nationid'] for x in b.t['rowteamnationlinks']}
        candidates = {x['teamid'] for x in b.t['leagueteamlinks']
                      if x['leagueid'] in country_leagues or x['leagueid'] == clubs_mod.REST_OF_WORLD and
                      row_nation.get(x['teamid']) == country} - fixed
        clubs = collections.defaultdict(list)
        for row in rows:
            if row['league'] == dump_league:
                clubs[row['club']].append(row)
        proposals = []
        forced = {k: str(v) for k, v in common.get('club_ids', {}).items()}
        for club, members in clubs.items():
            if club in forced and forced[club] not in fixed:
                proposals.append((3.0, club, forced[club]))  # renamed (Sangju Sangmu now Gimcheon Sangmu)
                continue
            votes = collections.Counter(club_of.get(matched[r['player_id']]['playerid'])
                                        for r in members if r['player_id'] in matched)
            for tid in candidates:
                name = squads.name_score(club, teams[tid]['teamname'])
                vote = votes.get(tid, 0) / max(len(members), 1)
                # The same name; or, in this league, most of the club's players (Jagiellonia, Cracovia).
                if name >= 0.78 or (vote >= 0.4 and tid in in_league):
                    proposals.append((name + vote, club, tid))
        found, used_teams = {}, set()
        for score, club, tid in sorted(proposals, reverse=True):
            if club not in found and tid not in used_teams:
                found[club] = (tid, score)
                used_teams.add(tid)
        # A club found elsewhere (Rest of World, another division) comes into this league in the place of one
        # the dump hasn't here; a club not found is made, in such a place.
        spare = sorted((t for t in in_league if t not in used_teams and t not in fixed),
                       key=lambda t: int(teams[t].get('overallrating') or 0))
        colors = common.get('club_colors', {})
        for club in sorted(clubs, key=lambda c: -len(clubs[c])):
            if club in found and found[club][0] in in_league:
                continue
            members = [x['teamid'] for x in b.t['leagueteamlinks'] if x['leagueid'] == league_id]
            grow = not spare and league_id in map(str, common.get('resize', [])) and len(members) < len(clubs)
            if not spare and not grow:
                found.pop(club, None)
                continue
            place = spare.pop(0) if spare else min(members, key=lambda t: int(teams[t].get('overallrating') or 0))
            if club in found:
                tid = found[club][0]
                old = next(x for x in b.t['leagueteamlinks'] if x['teamid'] == tid)
                gone = made_clubs.leave(place) if not grow else dict(old)
                old['prevleagueid'], old['leagueid'] = old['leagueid'], league_id
                b.t['rowteamnationlinks'] = [x for x in b.t['rowteamnationlinks'] if x['teamid'] != tid]
                for k in ('previousyeartableposition', 'currenttableposition'):
                    old[k] = gone[k]
            else:
                c = colors.get(club, {})
                team = made_clubs.add(c.get('name', club), c.get('short', club), c.get('abbr3'),
                                      c.get('colors', ['808080', 'ffffff']), league_id, place,
                                      logo=c.get('logo'), source_id=f'fc27-{club}', leave=not grow)
                tid = team['teamid']
                teams[tid] = team
                found[club] = (tid, 0)
        for club in forced:  # a renamed club's new name (club_colors' name, short, abbr3)
            c = colors.get(club, {})
            if club in found and c.get('name'):
                tid, team = found[club][0], teams[found[club][0]]
                team['teamname'] = c['name']
                short = c.get('short', c['name'])
                b.strings.update({f'TeamName_{tid}': c['name'], f'TeamName_Abbr15_{tid}': c['name'][:15],
                                  f'TeamName_Abbr10_{tid}': short[:10], f'TeamName_Abbr7_{tid}': short[:7],
                                  f'CT_TeamName_{tid}': short})
                if c.get('abbr3'):
                    b.strings[f'TeamName_Abbr3_{tid}'] = c['abbr3']
        for club, (tid, score) in sorted(found.items()):
            squad = []
            for row in clubs[club]:
                born = born_of(row)
                p = matched.get(row['player_id'])
                if p is not None and club_of.get(p['playerid']) in fixed:
                    continue  # ESPN's club (today's) wins
                if p is None:
                    pos = POSITIONS.get(row['position'], fifa.CM)
                    p = b.new_player(athlete_of(row), fifa.shifted(born, shift), pos, int(row['overall_rating']),
                                     b.nation_by_name.get(fifa.fold(row['nationality']), common['nation_id']),
                                     fifa.stable('fc27', row['player_id']))
                    p['potential'] = '0'  # not the template's
                    apply(b, p, row, born, today, shift)
                    p['playerjointeamdate'] = str(fifa.days(fifa.shifted(today, shift)) - 120)
                    p['contractvaliduntil'] = str(2019 + fifa.stable('contract', row['player_id']) % 4)
                    matched[row['player_id']] = p
                    made += 1
                squad.append({'player': p, 'rating': int(p['overallrating']), 'pos': int(p['preferredposition1']),
                              'age': (today - born).days // 365})
            if len(squad) < 14:
                continue  # too few to be the club's squad: the game's stays
            squad = sorted(squad, key=lambda e: -e['rating'])[:squads.MAX_SQUAD]
            ids = {e['player']['playerid'] for e in squad}
            leaving = [x['playerid'] for x in links if x['teamid'] == tid and x['playerid'] not in ids]
            links[:] = [x for x in links if x['teamid'] != tid and
                        not (x['playerid'] in ids and x['teamid'] not in national)]
            b.t['playerloans'] = [x for x in b.t['playerloans'] if x['playerid'] not in ids]
            formation = b.formation_for(tid, True, 0)
            chosen = b.line_up(squad, [int(formation[f'position{i}']) for i in range(11)])
            for n, e in enumerate(squad, 1):
                links.append(b.link(next_key, tid, e['player']['playerid'],
                                    chosen.get(id(e), 28 if e.get('bench') else 29), n))
                next_key += 1
                club_of[e['player']['playerid']] = tid
            for pid in leaving:
                if not any(x['playerid'] == pid and x['teamid'] not in national for x in links):
                    links.append(b.link(next_key, free_agents, pid, 29, 0))
                    next_key += 1
            starters = [e for e in squad if id(e) in chosen]
            team = teams[tid]
            team['overallrating'] = team['matchdayoverallrating'] = str(round(sum(e['rating'] for e in starters) / 11))
            outfield = [e for e in sorted(starters, key=lambda e: -e['rating']) if e['pos'] != fifa.GK]
            team['captainid'] = max(starters, key=lambda e: (e['age'] > 25, e['rating']))['player']['playerid']
            for k in ('penaltytakerid', 'freekicktakerid', 'longkicktakerid', 'leftcornerkicktakerid',
                      'rightcornerkicktakerid'):
                team[k] = outfield[0]['player']['playerid']
            report_clubs.append({'club': club, 'teamid': tid, 'team': team['teamname'], 'players': len(squad),
                                 'score': round(score, 2)})
        for club in sorted(set(clubs) - set(found)):
            report_clubs.append({'club': club, 'teamid': None})

    os.makedirs(outdir, exist_ok=True)
    for name in sorted(b.changed):
        fifa.write(os.path.join(outdir, name + '.csv'), b.t[name])
    with open(os.path.join(outdir, 'fc27-strings.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['stringid', 'text'])
        for k, v in sorted(b.strings.items()):
            w.writerow([k, v])
    json.dump(made_clubs.report(), open(os.path.join(outdir, 'fc27-clubs.json'), 'w'), indent=1, ensure_ascii=False)
    # The dump's player id -> the game's player id. Most are equal (EA keeps ids), but players matched by name
    # or made fresh have this game's ids; their FC pictures are copied under those ids by minifaces.py.
    pictures = {str(p['playerid']): str(fc) for fc, p in matched.items() if p.get('playerid')}
    report = {'rated': len(matched) - made, 'by_id': by_id, 'dump_players': len(rows), 'new_players': made,
              'pictures': pictures,
              'clubs': report_clubs, 'new_clubs': [m['name'] for m in made_clubs.made], 'left': made_clubs.left}
    json.dump(report, open(os.path.join(outdir, 'fc27.json'), 'w'), indent=1, ensure_ascii=False)
    print(f"FC 27: {report['rated']} of the game's players rated ({by_id} by id) of {len(rows)}; "
          f"{sum(1 for c in report_clubs if c['teamid'])} clubs' squads, {made} new players, "
          f"{len(made_clubs.made)} clubs made")
    for new in made_clubs.made:
        print(f"  new {new['name']:28} " + (f"in the place of {teams[new['replaces']]['teamname']}"
                                             if new['replaces'] else 'added'))
    for c in report_clubs:
        if c['teamid'] is None:
            print(f"  no team for {c['club']}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
