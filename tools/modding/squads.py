#!/usr/bin/env python3
"""Updates the game's club squads from ESPN's cached rosters.

  squads.py CONFIG.json CSVDIR ESPNDIR OUTCSVDIR [PCSQUADS.json]

CONFIG maps the game's league ids to ESPN league codes (see leagues/world.json). Existing players are matched
by name and birth date and keep their ids and assets. Teams that cannot be matched confidently are reported and
left untouched. CONFIG's max_new_players, when given, caps the players added (the most-used first, spread over
the clubs); the database has no such limit of its own (docs/MODDING.md). PCSQUADS.json (pcsquads.py's report, when
its update came first): the players it rated keep their ratings, and the Legends keep their players.
"""
import csv
import datetime
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import league as fifa  # noqa: E402


def athlete_stats(athlete):
    """The roster response already contains the current season's statistics."""
    out = {}
    splits = (athlete.get('statistics') or {}).get('splits', {})
    for category in splits.get('categories', []):
        for stat in category.get('stats', []):
            out[stat['name']] = stat.get('value') or 0
    return out


_DROP = {'fc', 'afc', 'cf', 'sc', 'ac', 'as', 'cd', 'rc', 'rcd', 'ud', 'fk', 'sk', 'bk', 'if', 'sv', 'vfl',
         'vfb', 'ssc', 'ss', 'us', 'sd', 'ksv', 'club', 'calcio', 'football', 'futbol', 'de', 'la',
         'losc', 'fsv', 'ogc', 'estac', 'scr', 'bb', 'sco', 'kv', 'kvc', 'oh', 'raal', 'olympique', 'stade',
         'deportivo'}
_GENERIC = {'united', 'city', 'sporting', 'racing', 'athletic', 'atletico', 'real', 'dynamo', 'inter'}


def club_key(name):
    words = re.findall(r'[a-z0-9]+', fifa.fold(name).replace('.', ' '))
    aliases = {'saint': 'st', 'munchen': 'munich', 'koeln': 'koln', 'internazionale': 'inter',
               'lyonnais': 'lyon', 'brestois': 'brest'}
    words = [aliases.get(w, w) for w in words if not w.isdigit()]
    words = [w[:-1] if len(w) > 6 and w.endswith('s') else w for w in words]
    useful = [w for w in words if w not in _DROP]
    return ' '.join(useful or words)


def name_score(source, target):
    """A conservative club-name score; country filtering is done by the caller."""
    a, b = club_key(source), club_key(target)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    sa, sb = set(a.split()), set(b.split())
    overlap = len(sa & sb) / max(len(sa), len(sb))
    contained = min(len(a), len(b)) / max(len(a), len(b)) if a in b or b in a else 0
    smaller = sa if len(sa) <= len(sb) else sb
    other = sb if smaller is sa else sa
    subset = (0.92 if smaller and smaller <= other and
              any(len(w) >= 4 and w not in _GENERIC for w in smaller) else 0)
    return max(ratio, overlap, contained, subset)


def source_names(team):
    return [team.get(k, '') for k in ('displayName', 'shortDisplayName', 'name', 'location') if team.get(k)]


def match_teams(builder, cfg):
    """Returns source entries with a confident, one-to-one game team id."""
    leagues = {x['leagueid']: x for x in builder.t['leagues']}
    links = builder.t['leagueteamlinks']
    teams = {x['teamid']: x for x in builder.t['teams']}
    overrides = cfg.get('team_ids', {})
    matched, unmatched, used = [], [], set()
    for league_id, code in cfg['leagues'].items():
        league_id = str(league_id)
        country = leagues[league_id]['countryid']
        country_leagues = {lid for lid, row in leagues.items() if row['countryid'] == country}
        candidates = {x['teamid'] for x in links if x['leagueid'] in country_leagues and x['teamid'] in teams}
        # The target league first breaks otherwise-equal names in favour of the expected club.
        target = {x['teamid'] for x in links if x['leagueid'] == league_id}
        data = json.load(open(os.path.join(builder.espn, code + '-teams.json'))
                         )['sports'][0]['leagues'][0]['teams']
        proposals = []
        for wrapped in data:
            team = wrapped['team']
            forced = overrides.get(code, {}).get(str(team['id']))
            if forced is not None:
                proposals.append((2.0, 1.0, str(forced), team))
                continue
            scores = []
            for tid in candidates:
                score = max(name_score(a, teams[tid]['teamname']) for a in source_names(team))
                scores.append((score + (0.002 if tid in target else 0), tid))
            scores.sort(reverse=True)
            best = scores[0] if scores else (0, '')
            second = scores[1][0] if len(scores) > 1 else 0
            proposals.append((best[0], second, best[1], team))
        # Resolve collisions by taking the strongest proposal first.
        for score, second, tid, team in sorted(proposals, reverse=True, key=lambda x: x[0]):
            forced = score > 1
            confident = forced or score >= 0.78 and score - second >= 0.055
            if confident and tid not in used and tid in teams:
                used.add(tid)
                roster_path = os.path.join(builder.espn, f"{code}-roster-{team['id']}.json")
                roster = json.load(open(roster_path)).get('athletes', [])
                matched.append({'code': code, 'league_id': league_id, 'source': team, 'teamid': int(tid),
                                'team': teams[tid], 'roster': roster, 'score': min(score, 1.0)})
            else:
                unmatched.append({'league': code, 'source_id': team['id'], 'name': team['displayName'],
                                  'candidate': teams[tid]['teamname'] if tid in teams else '',
                                  'score': round(min(score, 1.0), 3)})
    return matched, unmatched


def full_name_index(builder):
    out = {}
    protected = {x['playerid'] for x in builder.t['teamplayerlinks'] if x['teamid'] in builder.protected}
    for player in builder.t['players']:
        if player['playerid'] in protected:
            continue
        first = fifa.fold(builder.names.get(int(player['firstnameid']), ''))
        last = fifa.fold(builder.names.get(int(player['lastnameid']), ''))
        common = fifa.fold(builder.names.get(int(player['commonnameid']), ''))
        for name in {f'{first} {last}'.strip(), common} - {''}:
            out.setdefault(name, []).append(player)
    return out


def fallback_player(builder, by_name, athlete, born):
    player = builder.match(athlete, born)  # on the real birth date or the shifted one
    if player is not None:
        return player
    hits = {}
    for name in (athlete.get('displayName', ''),
                 f"{athlete.get('firstName', '')} {athlete.get('lastName', '')}"):
        for p in by_name.get(fifa.fold(name), []):
            hits[p['playerid']] = p
    return next(iter(hits.values())) if len(hits) == 1 else None


MAX_SQUAD = 33  # the game's own biggest squads; ESPN's lists with their youth teams reach 58 (Brazil)


def club_player(builder, squad, athlete, born):
    """The club's own player for an athlete no name matched: born on his birthday, the year within three (updates
    make young players older), the one such, or the one of those whose name is nearest; else a near name alone."""
    import difflib
    shown = fifa.fold(athlete.get('displayName', ''))
    full = fifa.fold(f"{athlete.get('firstName', '')} {athlete.get('lastName', '')}")

    def name_score(p):
        names = [fifa.fold(builder.names.get(int(p[f]), '')) for f in ('firstnameid', 'lastnameid', 'commonnameid')]
        mine = {f'{names[0]} {names[1]}'.strip(), names[2], names[1]} - {''}
        return max(difflib.SequenceMatcher(None, x, y).ratio() for x in (shown, full) for y in mine) if mine else 0
    for when in (born, fifa.shifted(born, builder.cfg.get('age_shift_years', 8))):
        day = [p for p in squad if (lambda b: (b.month, b.day) == (when.month, when.day) and
                                    abs(b.year - when.year) <= 3)(fifa.from_days(p['birthdate']))]
        if len(day) == 1 and name_score(day[0]) >= 0.3:
            return day[0]
        if len(day) > 1:
            best = max(day, key=name_score)
            if name_score(best) >= 0.5:
                return best
    scored = sorted(((name_score(p), p['playerid'], p) for p in squad), key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.85:
        return scored[0][2]
    return None


def select_new(builder, entries, limit):
    """The new players to add: a few per club first, then by playing time, up to limit."""
    queues = {}
    for entry in entries:
        q = [p for p in entry['players'] if p['player'] is None and not p.get('duplicate')]
        q.sort(key=lambda p: (p['stats'].get('minutes', 0), p['stats'].get('appearances', 0),
                              p['stats'].get('totalGoals', 0), -p['age']), reverse=True)
        queues[entry['teamid']] = q
    chosen = []

    def take(candidate):
        chosen.append(candidate)
        return True

    # No club over MAX_SQUAD: its known players first, then the new ones who played most.
    for entry in entries:
        known = sum(1 for p in entry['players'] if p['player'] is not None)
        del queues[entry['teamid']][max(0, MAX_SQUAD - known):]
    # A few current additions per club are more useful than exhausting the cap in the largest rosters.
    for round_no in range(12):
        for entry in entries:
            q = queues[entry['teamid']]
            if q and len(chosen) < limit:
                take(q.pop(0))
    rest = sorted((p for q in queues.values() for p in q),
                  key=lambda p: (p['stats'].get('minutes', 0), p['stats'].get('appearances', 0),
                                 p['stats'].get('totalGoals', 0)), reverse=True)
    for candidate in rest:
        if len(chosen) >= limit:
            break
        take(candidate)
    return {id(p) for p in chosen}


def update_divisions(builder, cfg, entries):
    """Promotion and relegation: each of a country's divisions gets the clubs ESPN has in it today, as many as
    it has places (the competitions are made for its size); the country's other clubs fill the places left, those
    already in that division first, then the rest in division order. Returns the moves."""
    leagues = {x['leagueid']: x for x in builder.t['leagues']}
    links = builder.t['leagueteamlinks']
    listed = {}
    for e in entries:
        listed.setdefault(e['league_id'], []).append(str(e['teamid']))
    moves = []
    for country in sorted({leagues[str(lid)]['countryid'] for lid in cfg['leagues']}):
        divisions = sorted((lid for lid, row in leagues.items() if row['countryid'] == country),
                           key=lambda lid: (int(leagues[lid]['level']), int(lid)))
        members = {lid: [x['teamid'] for x in links if x['leagueid'] == lid] for lid in divisions}
        assigned = {}
        for lid in divisions:
            today = sorted(listed.get(lid, []), key=lambda t: t not in members[lid])  # the division's own first
            for tid in [t for t in today if t not in assigned][:len(members[lid])]:
                assigned[tid] = lid
        pool = [t for lid in divisions for t in members[lid] if t not in assigned]
        for lid in divisions:
            need = len(members[lid]) - sum(1 for v in assigned.values() if v == lid)
            take = ([t for t in pool if t in members[lid]] + [t for t in pool if t not in members[lid]])[:need]
            for tid in take:
                assigned[tid] = lid
                pool.remove(tid)
        for x in links:
            new = assigned.get(x['teamid']) if x['leagueid'] in divisions else None
            if new and new != x['leagueid']:
                moves.append({'teamid': x['teamid'], 'name': builder.t_teams.get(x['teamid'], ''),
                              'from': leagues[x['leagueid']]['leaguename'], 'to': leagues[new]['leaguename']})
                x['prevleagueid'], x['leagueid'] = x['leagueid'], new
    return moves


def build(cfg, csvdir, espndir, outdir, pcsquads=None):
    common = dict(cfg)
    common.setdefault('today', datetime.date.today().isoformat())
    common.setdefault('age_shift_years', 8)
    common.setdefault('first_player_id', 260000)
    common.setdefault('free_agents_team_id', 111592)
    common.setdefault('template_team_id', 1)
    common.setdefault('seasons', ['current'])
    common.setdefault('nation_id', 14)
    builder = fifa.Builder(common, csvdir, espndir)
    builder.use_pcsquads(pcsquads)
    builder.changed = {'teams', 'teamplayerlinks', 'players', 'dcplayernames', 'editedplayernames', 'playerloans'}
    builder.index_players()
    builder.templates()
    builder._feet = {}
    builder.next_player = max(common['first_player_id'], max(builder.players) + 1)
    entries, unmatched = match_teams(builder, cfg)
    builder.t_teams = {x['teamid']: x['teamname'] for x in builder.t['teams']}
    moves = update_divisions(builder, cfg, entries)
    builder.changed.add('leagueteamlinks')
    by_name = full_name_index(builder)
    today = datetime.date.fromisoformat(common['today'])
    shift = common['age_shift_years']

    # First resolve every source player globally; a transferred player must occur in only one club squad.
    protected = {x['playerid'] for x in builder.t['teamplayerlinks'] if x['teamid'] in builder.protected}
    own = {}
    for x in builder.t['teamplayerlinks']:
        if int(x['playerid']) in builder.players and x['playerid'] not in protected:
            own.setdefault(x['teamid'], []).append(builder.players[int(x['playerid'])])
    ownership = {}
    for entry in entries:
        players = []
        for athlete in entry['roster']:
            try:
                born_real = datetime.date.fromisoformat(athlete['dateOfBirth'][:10])
            except (KeyError, ValueError):
                born_real = today.replace(year=today.year - 25)
            stats = athlete_stats(athlete)
            player = fallback_player(builder, by_name, athlete, born_real)
            if player is None:
                player = club_player(builder, own.get(str(entry['teamid']), []), athlete, born_real)
            item = {'athlete': athlete, 'born_real': born_real, 'born': fifa.shifted(born_real, shift),
                    'age': (today - born_real).days // 365, 'stats': stats, 'st': stats,
                    'letter': (athlete.get('position') or {}).get('abbreviation', 'M')[:1],
                    'player': player, 'entry': entry}
            players.append(item)
            if player is not None:
                priority = stats.get('minutes', 0) + stats.get('appearances', 0)
                old = ownership.get(player['playerid'])
                if old is None or priority > old[0]:
                    ownership[player['playerid']] = (priority, item)
        entry['players'] = players
    for entry in entries:
        for item in entry['players']:
            if item['player'] is not None and ownership[item['player']['playerid']][1] is not item:
                item['player'] = None
                item['duplicate'] = True

    selected = select_new(builder, entries, int(common.get('max_new_players') or 10 ** 9))
    old_links = list(builder.t['teamplayerlinks'])
    national = {x['teamid'] for x in builder.t['leagueteamlinks'] if x['leagueid'] in ('78', '2136')}
    updated_teams = {str(e['teamid']) for e in entries}
    existing_keys = [int(x['artificialkey']) for x in old_links]
    next_key = max(existing_keys) + 1
    assigned = set()
    report_teams = []

    # Create/update the current players before rebuilding links.
    for entry in entries:
        squad = []
        team_strength = int(entry['team'].get('overallrating') or 65)
        for item in entry['players']:
            if item['player'] is None and id(item) not in selected:
                continue
            squad.append(item)
        builder.assign_positions(squad)
        for item in squad:
            athlete, player = item['athlete'], item['player']
            if player is not None and int(player['playerid']) in builder.keep:
                item['rating'] = int(player['overallrating'])  # rated already (pcsquads.py)
                builder.report['matched_players'] += 1
                player['birthdate'] = str(fifa.days(item['born']))  # ESPN's: updates make young players older
                assigned.add(player['playerid'])
                continue
            rating = builder.rating_for(team_strength, item['stats'], item['pos'], item['age'])
            if player is not None:
                rating = round((int(player['overallrating']) * 2 + rating) / 3)
                builder.update_existing(player, rating)
            else:
                nation_name = fifa.fold(athlete.get('citizenship', ''))
                nation = builder.nation_by_name.get(nation_name, common['nation_id'])
                player = builder.new_player(athlete, item['born'], item['pos'], rating, nation,
                                            fifa.stable(entry['code'], athlete['id']))
                item['player'] = player
            item['rating'] = rating
            player['overallrating'] = str(rating)
            player['potential'] = str(builder.potential_for(rating, item['age']))
            player['birthdate'] = str(fifa.days(item['born']))
            if athlete.get('height'):
                player['height'] = str(max(155, min(205, round(athlete['height'] * 2.54))))
            if athlete.get('weight'):
                player['weight'] = str(max(50, min(110, round(athlete['weight'] * 0.4536))))
            assigned.add(player['playerid'])

    # Remove club links for updated clubs and for players who have a new club; national-team links stay.
    builder.t['teamplayerlinks'] = [x for x in old_links if x['teamid'] not in updated_teams and
                                    not (x['playerid'] in assigned and x['teamid'] not in national)]
    builder.t['playerloans'] = [x for x in builder.t['playerloans'] if x['playerid'] not in assigned]
    free_agents = str(common['free_agents_team_id'])
    dropped = set()

    for entry in entries:
        current = [p for p in entry['players'] if p.get('player') is not None and p['player']['playerid'] in assigned]
        current_ids = {p['player']['playerid'] for p in current}
        legacy_links = [x for x in old_links if x['teamid'] == str(entry['teamid']) and
                        x['playerid'] not in assigned and int(x['playerid']) in builder.players]
        legacy_links.sort(key=lambda x: int(builder.players[int(x['playerid'])]['overallrating']), reverse=True)
        # Keep a playable squad without allowing ESPN's reserve/youth lists to make it unbounded.
        room = max(0, 30 - len(current))
        keep_legacy, cut_legacy = legacy_links[:room], legacy_links[room:]
        dropped.update(x['playerid'] for x in cut_legacy)
        formation = builder.formation_for(entry['teamid'], True, 0)
        slots = [int(formation[f'position{i}']) for i in range(11)]
        if len(current) >= 11:
            chosen = builder.line_up(current, slots)
        else:
            chosen = {}
        used_numbers = set()
        for item in current:
            jersey = str(item['athlete'].get('jersey') or '')
            number = int(jersey) if jersey.isdigit() and 0 < int(jersey) < 100 and int(jersey) not in used_numbers else 0
            if not number:
                number = next(n for n in range(1, 100) if n not in used_numbers)
            used_numbers.add(number)
            position = chosen.get(id(item), 28 if item.get('bench') else 29)
            builder.t['teamplayerlinks'].append(builder.link(next_key, entry['teamid'],
                                                             item['player']['playerid'], position, number))
            next_key += 1
        for link in keep_legacy:
            row = dict(link)
            row['artificialkey'] = str(next_key)
            if len(current) >= 11:
                row['position'] = '29'
            builder.t['teamplayerlinks'].append(row)
            next_key += 1
        all_players = current + [{'player': builder.players[int(x['playerid'])], 'pos':
                                  int(builder.players[int(x['playerid'])]['preferredposition1']),
                                  'rating': int(builder.players[int(x['playerid'])]['overallrating']), 'age': 25}
                                 for x in keep_legacy]
        if len(all_players) >= 11:
            best = sorted(all_players, key=lambda p: p.get('rating', int(p['player']['overallrating'])), reverse=True)[:11]
            avg = round(sum(int(p['player']['overallrating']) for p in best) / 11)
            entry['team']['overallrating'] = entry['team']['matchdayoverallrating'] = str(avg)
            captain = max(best, key=lambda p: (p.get('age', 25) > 25, int(p['player']['overallrating'])))
            entry['team']['captainid'] = captain['player']['playerid']
        report_teams.append({'league': entry['code'], 'source_id': entry['source']['id'],
                             'teamid': entry['teamid'], 'source_name': entry['source']['displayName'],
                             'game_name': entry['team']['teamname'], 'current': len(current),
                             'legacy': len(keep_legacy), 'score': round(entry['score'], 3)})

    linked = {x['playerid'] for x in builder.t['teamplayerlinks'] if x['teamid'] not in national}
    for pid in sorted(dropped - linked, key=int):
        builder.t['teamplayerlinks'].append(builder.link(next_key, free_agents, pid, 29, 0))
        next_key += 1

    os.makedirs(outdir, exist_ok=True)
    for name in sorted(builder.changed):
        fifa.write(os.path.join(outdir, name + '.csv'), builder.t[name])
    report = {'matched_teams': len(entries), 'unmatched_teams': unmatched, 'division_moves': moves,
              'matched_players': builder.report['matched_players'],
              'new_players': builder.report['new_players'], 'teams': report_teams,
              'records': {name: len(builder.t[name]) for name in builder.changed}}
    with open(os.path.join(outdir, 'squads.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    return report


def main(argv):
    if len(argv) not in (5, 6):
        print(__doc__, file=sys.stderr)
        return 2
    cfg = json.load(open(argv[1]))
    report = build(cfg, argv[2], argv[3], argv[4], argv[5] if len(argv) > 5 else None)
    print(f"ESPN squads: {report['matched_teams']} clubs, {report['matched_players']} existing players, "
          f"{report['new_players']} new; {len(report['unmatched_teams'])} clubs left unchanged; "
          f"{len(report['division_moves'])} clubs promoted or relegated")
    for item in report['unmatched_teams']:
        print(f"  unmatched {item['league']:7} {item['name']:28} "
              f"({item['candidate'] or 'no candidate'}, {item['score']:.3f})")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
