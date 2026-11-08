#!/usr/bin/env python3
"""A squads file of the PC game (FIFA 19 for PC, such as a community update) into this game's database: today's
ratings and squads, and a league of the 2010s' great teams (Legends) from the update's own Superliga.

  pcsquads.py CONFIG.json CSVDIR SQUADFILE OUTCSVDIR STRINGS.csv [ESPNDIR]

CONFIG: tools/modding/leagues/pc2026.json. CSVDIR: the game's tables (db.sh export). SQUADFILE: the PC game's
squads save (Squads<date>, "FBCHUNKS" with a t3db inside). Writes the changed tables to OUTCSVDIR, the new names to
STRINGS.csv, and OUTCSVDIR/pcsquads.json: what was done (the players rated from the file, the Legends teams for
teamassets.py and compdata.py).

The squads file is the PC game's database (little-endian; its tables keep their spare records: players 26,000 of
which 18,439 are used) without the names table: a player's names are ids into the PC game's own names (not ours),
plus the file's new names (dcplayernames, ids from 34,000) and full names of edited players (editedplayernames).
The PC ids are put to text through the players both games have. The few left (young players on reused ids) are
named from ESPN's cached rosters (ESPNDIR: the one player born that day of that nation), else from the game's own
names for the nation, as it names its youth players.

Who is who: the update reuses ids. A player whose id and birth date are the game's is the game's player (his face
and boots kept); the same id with another birth date is someone else (4,154 in the April 2026 file): he takes the
id over, as in the update, with a generic head (the old player's face is his id's). Ids the game hasn't are new.

What is taken:
- Players: ratings, attributes, positions, foot, skills, work rates, traits, height and weight; looks for the
  new ones. Birth dates move back CONFIG's age_shift_years (8: the calendar starts in 2018) so ages are today's.
- Squads (who plays where, shirt numbers) for the clubs and national teams the update has as themselves. Line-ups
  are picked again for the game's formations (the update's formations are encoded differently).
- Clubs the update used for other clubs' players (CONFIG's replaced: Russia's clubs in Ireland's, ...) keep their
  own players; the guests go to free agents, where the later steps (a league's build, the ESPN squads) find them.
- Legends: the update's MLS holds the 2010s squads of 23 great clubs. They become a league of their own (CONFIG's
  legends) with new teams named after the clubs, the clubs' kits, crests, flags, banners and grounds. The game
  has these players as they were in 2018, which is the decade they stand for: they keep the game's ratings and
  birth dates (and faces); the few it hasn't come from the file. The real MLS clubs keep the game's squads.
"""
import collections
import csv
import datetime
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fifadb  # noqa: E402
import league as fifa  # noqa: E402

# PC fields stored from another range than ours (the value is raw + rangelow): PC minus ours.
PC_OFFSET = {'players': {'height': -20, 'weight': -20}}
# Player fields the file gives for everyone it rates.
SKILL = fifa.ATTRIBUTES + ['overallrating', 'potential', 'preferredposition1', 'preferredposition2',
                           'preferredposition3', 'preferredposition4', 'preferredfoot', 'weakfootabilitytypecode',
                           'skillmoves', 'attackingworkrate', 'defensiveworkrate', 'trait1', 'trait2',
                           'internationalrep', 'height', 'weight', 'contractvaliduntil', 'playerjointeamdate',
                           'isretiring', 'gksavetype', 'gkkickstyle', 'runningcode1', 'runningcode2',
                           'finishingcode1', 'finishingcode2', 'emotion', 'personality']
NAME_FIELDS = ('firstnameid', 'lastnameid', 'commonnameid', 'playerjerseynameid')
MAX_SQUAD = 33


# --- the file -------------------------------------------------------------------------------------------------------
def read_save(path, meta):
    """{table name: [row]} from the PC squads file: fields by our meta's names (others by their short names),
    integers as values (our rangelow added, then PC_OFFSET)."""
    raw = open(path, 'rb').read()
    at = raw.find(b'DB\0\x08')
    if raw[:8] != b'FBCHUNKS' or at < 0:
        raise SystemExit(f'{path}: not a FIFA squads file (FBCHUNKS with a database)')
    d = raw[at:]
    count = struct.unpack('<I', d[16:20])[0]
    base = 24 + 8 * count + 4
    index = [(d[24 + 8 * i:28 + 8 * i][::-1].decode('latin1'), struct.unpack('<I', d[28 + 8 * i:32 + 8 * i])[0])
             for i in range(count)]
    names = fifadb.read_meta(meta)
    order = sorted(index, key=lambda x: x[1])
    out = {}
    for k, (short, offset) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(d) - base
        t = d[base + offset:base + end]
        record_bytes, valid, nfields = struct.unpack('<I', t[4:8])[0], struct.unpack('<H', t[22:24])[0], t[24]
        fields, p = [], 36
        for _ in range(nfields):
            ftype, bit, fshort, bits = struct.unpack('<II4sI', t[p:p + 16])
            fields.append((fshort[::-1].decode('latin1'), ftype, bit, bits))
            p += 16
        tname, fmeta = names.get(short, (short, {}))
        fix = PC_OFFSET.get(tname, {})
        rows = []
        for i in range(valid):  # records past the used ones are the table's spare room
            rec = t[p + i * record_bytes:p + (i + 1) * record_bytes]
            value = int.from_bytes(rec, 'little')
            row = {}
            for fshort, ftype, bit, bits in fields:
                name, _, low = fmeta.get(fshort, (fshort, '', 0))
                if ftype == 0:
                    row[name] = rec[bit // 8:bit // 8 + bits // 8].split(b'\0')[0].decode('utf-8', 'replace')
                elif ftype == 4 and bits == 32:
                    row[name] = struct.unpack('<f', ((value >> bit) & 0xFFFFFFFF).to_bytes(4, 'little'))[0]
                else:
                    row[name] = ((value >> bit) & ((1 << bits) - 1)) + low + fix.get(name, 0)
            rows.append(row)
        out[tname] = rows
    return out


def field_ranges(meta, table):
    """{field: (lowest, highest)} the game takes (its meta's range, within the field's bits)."""
    text = open(meta, encoding='utf-8').read()
    body = re.search(r'<table name="%s".*?</table>' % table, text, re.S).group(0)
    out = {}
    for f in re.findall(r'<field ([^>]*)/>', body):
        a = dict(re.findall(r'(\w+)="([^"]*)"', f))
        if a.get('type') == 'DBOFIELDTYPE_INTEGER':
            low, high, bits = int(a.get('rangelow') or 0), int(a.get('rangehigh') or 0), int(a['depth'])
            out[a['name']] = (low, min(high, low + (1 << bits) - 1))
    return out


class Names:
    """The file's players' names as text."""

    def __init__(self, save, ours, our_names):
        self.edited = {r['playerid']: r for r in save['editedplayernames']}
        self.new = {r['nameid']: r['name'] for r in save['dcplayernames']}
        votes = collections.defaultdict(collections.Counter)
        for p in save['players']:
            x = ours.get(p['playerid'])
            if x is None or p['playerid'] in self.edited or p['birthdate'] != int(x['birthdate']):
                continue
            for f in NAME_FIELDS:
                if p[f] and int(x[f]):
                    votes[p[f]][our_names.get(int(x[f]), '')] += 1
        self.pc = {k: v.most_common(1)[0][0] for k, v in votes.items()}

    def text(self, nameid):
        if not nameid:
            return ''
        return self.new.get(nameid) or self.pc.get(nameid) or ''

    def of(self, p):
        """(first, last, common, jersey) of a file's player."""
        e = self.edited.get(p['playerid'])
        if e:
            return e['firstname'], e['surname'], e['commonname'], e['playerjerseyname']
        return tuple(self.text(p[f]) for f in NAME_FIELDS)


# --- the update -----------------------------------------------------------------------------------------------------
def espn_names(espn, b):
    """{(real birth date, nation id): (first, last, shown)} from ESPN's cached rosters (sources/espn.py), where only
    one player has the pair."""
    found = collections.defaultdict(set)
    if espn and os.path.isdir(espn):
        for name in os.listdir(espn):
            if '-roster-' not in name:
                continue
            for a in json.load(open(os.path.join(espn, name))).get('athletes', []):
                nation = b.nation_by_name.get(fifa.fold(a.get('citizenship', '')), 0)
                if a.get('dateOfBirth'):
                    import html
                    found[(a['dateOfBirth'][:10], nation)].add(tuple(html.unescape(a.get(k, '')).strip() for k in
                                                                     ('firstName', 'lastName', 'displayName')))
    return found


def build(cfg, csvdir, squadfile, out, strings_path, espn=None):
    meta = cfg.get('meta') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'out', 'mod', 'raw',
                                           'fifa_ng_db-meta.xml')  # db.sh unpacks it there
    save = read_save(squadfile, meta)
    common = {'today': cfg['today'], 'age_shift_years': cfg['age_shift_years'], 'seasons': ['current'],
              'nation_id': cfg['legends']['nation_id'], 'template_league_id': cfg['legends']['template_league_id'],
              'referees': cfg['legends']['referees'], 'free_agents_team_id': cfg['free_agents_team_id']}
    b = fifa.Builder(common, csvdir, None)
    b.index_players()
    b.templates()
    t = b.t
    ranges = field_ranges(meta, 'players')
    shift = cfg['age_shift_years']
    ours = {int(p['playerid']): p for p in t['players']}
    names = Names(save, ours, b.names)
    teams = {x['teamid']: x for x in t['teams']}
    by_name = {}
    for x in t['teams']:
        by_name.setdefault(x['teamname'], x['teamid'])
    national = {x['teamid'] for x in t['leagueteamlinks'] if x['leagueid'] in ('78', '2136')}
    free_agents = str(cfg['free_agents_team_id'])
    report = {'rated': [], 'legends': {}, 'new_players': 0, 'taken_over': 0, 'same': 0, 'names_from_espn': 0,
              'names_made_up': 0}

    def resolve(name):
        tid = by_name.get(name)
        if tid is None:
            raise SystemExit(f'{name}: no such team in the game (pc2026.json)')
        return tid

    replaced = {resolve(n) for n in cfg['replaced']}
    legends_cfg = cfg['legends']
    pc_league = {r['teamid']: r['leagueid'] for r in save['leagueteamlinks']}
    legend_teams = {str(k): v for k, v in legends_cfg['teams'].items()}
    for k in legend_teams:
        if pc_league.get(int(k)) != legends_cfg['source_league']:
            raise SystemExit(f'team {k} is not in the file\'s league {legends_cfg["source_league"]}')
    pc_links = collections.defaultdict(list)
    for r in save['teamplayerlinks']:
        pc_links[str(r['teamid'])].append(r)
    pc_players = {r['playerid']: r for r in save['players']}
    legend_players = {r['playerid'] for k in legend_teams for r in pc_links[k]}

    # --- players ---
    def valid(field, value):
        low, high = ranges.get(field, (None, None))
        return low is None or low <= value <= high

    def take(row, p, fields):
        for f in fields:
            if f in p and f in row and isinstance(p[f], int) and valid(f, p[f]):
                row[f] = str(p[f])

    espn_people = espn_names(espn, b)
    by_birthday = collections.defaultdict(list)  # (month, day, nation): [(year, names)]
    for (day, nation), people in espn_people.items():
        when = datetime.date.fromisoformat(day)
        by_birthday[(when.month, when.day, nation)] += [(when.year, x) for x in people]

    def espn_person(p, first=''):
        """ESPN's player of the file's player's nation born on his birthday, the year within three of the file's
        (updates make young players older), with his first name when the file has it; the nearest, when only one
        is."""
        born = fifa.from_days(p['birthdate'])
        near = sorted((abs(year - born.year), year, names) for year, names in
                      by_birthday.get((born.month, born.day, p['nationality']), []) if abs(year - born.year) <= 3)
        if first:
            near = [x for x in near if fifa.fold(x[2][0]) == fifa.fold(first)] or near
        if near and (len(near) == 1 or near[0][0] < near[1][0]):
            return near[0][1], near[0][2]
        return None

    by_day = collections.defaultdict(set)
    for (day, _), people in espn_people.items():
        by_day[day] |= people

    def still_playing(row):
        """A player of the game's whom ESPN's rosters have today (born that day, of that name; his nationality may
        be another now)."""
        hits = by_day.get(fifa.from_days(row['birthdate']).isoformat(), ())
        mine = {fifa.fold(b.names.get(int(row[f]), '')) for f in ('lastnameid', 'commonnameid')} - {''}
        return any(mine & {fifa.fold(n) for n in hit} or
                   any(m in fifa.fold(hit[2]).split() for m in mine) for hit in hits)
    groups = {r['nationality']: r['groupid'] for r in fifa.read(os.path.join(csvdir, 'career_namesgroups.csv'))}
    pools = {}
    for kind, table, field in (('first', 'career_firstnames', 'firstname'), ('last', 'career_lastnames', 'lastname')):
        for r in fifa.read(os.path.join(csvdir, table + '.csv')):
            pools.setdefault((kind, r['groupid']), []).append(b.names.get(int(r[field]), ''))

    def names_for(row, p):
        first, last, common_name, jersey = names.of(p)
        if not last and not common_name:
            # A name of the PC game's own (not in the file): ESPN's player born that day of that nation, else one
            # of the game's names for his nation (as it names its youth players).
            hit = espn_person(p, first)
            if hit:
                year, (first, last, shown) = hit
                if not last:
                    first, last = '', shown
                if shown and shown != f'{first} {last}'.strip() and len(shown.split()) <= 2:
                    common_name = shown
                born = fifa.from_days(p['birthdate'])
                p['birthdate'] = fifa.days(fifa.shifted(born, born.year - year))  # ESPN's year: his true age
                report['names_from_espn'] += 1
            else:
                group = groups.get(str(p['nationality']), '0')
                firsts = [n for n in pools.get(('first', group)) or pools[('first', '0')] if n]
                lasts = [n for n in pools.get(('last', group)) or pools[('last', '0')] if n]
                first = first or firsts[fifa.stable('first', p['playerid']) % len(firsts)]
                last = lasts[fifa.stable('last', p['playerid']) % len(lasts)]
                report['names_made_up'] += 1
        b.set_names(row, first, last, common_name, jersey)

    def club(tid):
        return tid not in national

    # The update's MLS is its Superliga (the real MLS clubs keep the game's squads), the Legends taken from it.
    superliga = {str(t) for t, lg in pc_league.items() if lg == legends_cfg['source_league']}
    applied = {tid for tid in pc_links if tid in teams and tid not in replaced and tid not in superliga}
    # The file's players this takes: those in the squads it uses, the Legends and the guests of the lent clubs
    # (the rest, in its youth teams, stay out: the game's own players keep those ids).
    wanted = {r['playerid'] for tid in applied | set(legend_teams) | replaced for r in pc_links[tid]}

    rated, taken = set(), set()
    clones = {}  # a still-playing legend's id: his Legends copy's
    next_copy = [max(max(ours) + 1, legends_cfg['first_player_id'])]
    for pid, p in pc_players.items():
        if pid not in wanted:
            continue
        row = ours.get(pid)
        same = row is not None and int(row['birthdate']) == p['birthdate']
        if row is not None and not same:
            taken.add(pid)
        legend = pid in legend_players
        if same and legend:
            report['same'] += 1
            if not still_playing(row):
                continue  # as the game has him: the 2010s
            # Still playing today: he stays himself (today's ratings from the file, his club from the later
            # steps), and the Legends get his 2010s self as a copy on a new id (his head, face and hair copied).
            copy = dict(row, playerid=str(next_copy[0]))
            clones[pid] = next_copy[0]
            ours[next_copy[0]] = copy
            b.players[next_copy[0]] = copy
            t['players'].append(copy)
            next_copy[0] += 1
            # Today's self: the game's 2018 ratings aged to now, half each with the file's (its Superliga's ratings
            # are squeezed), on his 2018 attributes; positions from the file.
            age = (datetime.date.fromisoformat(cfg['today']) - fifa.from_days(row['birthdate'])).days // 365
            old_rating = int(row['overallrating'])
            rating = round((old_rating - max(0, age - 31) * 2 + p['overallrating']) / 2)
            b.update_existing(row, rating)
            row['overallrating'] = row['potential'] = str(rating)
            take(row, p, ['preferredposition1', 'preferredposition2', 'preferredposition3', 'preferredposition4'])
            row['birthdate'] = str(fifa.days(fifa.shifted(fifa.from_days(row['birthdate']), shift)))
            rated.add(pid)
            continue
        if row is None:
            pos = p['preferredposition1'] if valid('preferredposition1', p['preferredposition1']) else fifa.CM
            row = dict(b.template(pos, p['overallrating'], pid))
            row['playerid'] = str(pid)
            t['players'].append(row)
            ours[pid] = row
            b.players[pid] = row
            report['new_players'] += 1
        elif not same:
            report['taken_over'] += 1
        else:
            report['same'] += 1
        take(row, p, SKILL)
        if not same:
            # Someone new: his looks and boots from the file (a generic head: the id's face is the old player's).
            take(row, p, fifa.LOOKS + fifa.KIT + ['nationality', 'gender', 'bodytypecode', 'accessorycode1',
                                                  'accessorycode2', 'accessorycode3', 'accessorycode4',
                                                  'accessorycolourcode1', 'accessorycolourcode2',
                                                  'accessorycolourcode3', 'accessorycolourcode4'])
            row['hashighqualityhead'] = '0'
            names_for(row, p)
        born = fifa.from_days(p['birthdate'])
        row['birthdate'] = str(fifa.days(born if legend else fifa.shifted(born, shift)))
        if not legend:
            rated.add(pid)
    report['rated'] = sorted(rated)

    # --- squads ---
    placed = {str(r['playerid']) for tid in applied for r in pc_links[tid] if club(tid)}
    links = []
    for x in t['teamplayerlinks']:
        tid, pid = x['teamid'], int(x['playerid'])
        # The game's own squads where the file's aren't taken (the real MLS clubs, the clubs whose places the
        # update lent to others): their players the file has moved, or whose id is someone else's now, leave.
        if tid in applied or pid in legend_players or pid in taken or str(pid) in placed and club(tid):
            continue
        links.append(x)
    for tid in sorted(applied, key=int):
        for r in pc_links[tid]:
            links.append({'teamid': tid, 'playerid': str(r['playerid']), 'jerseynumber': str(r['jerseynumber']),
                          'position': '29'})

    # --- Legends ---
    league_id = str(legends_cfg['league_id'])
    template_team = {x['teamid']: x for x in t['teams']}
    next_team = legends_cfg['first_team_id']
    next_kit = max(int(x['teamkitid']) for x in t['teamkits']) + 1
    next_formation = max(int(x['formationid']) for x in t['formations']) + 1
    lrow = dict(next(x for x in t['leagues'] if x['leagueid'] == str(legends_cfg['template_league_id'])))
    lrow.update(leagueid=league_id, leaguename=legends_cfg['database_name'], countryid=str(legends_cfg['nation_id']),
                level='1')
    t['leagues'] = [x for x in t['leagues'] if x['leagueid'] != league_id] + [lrow]
    for key, text in legends_cfg['league_strings'].items():
        b.strings[key.format(id=league_id)] = text
    b.league_extras(int(league_id))
    template_link = dict(next(x for x in t['leagueteamlinks'] if x['teamid'] == '1'))
    next_lkey = max(int(x['artificialkey']) for x in t['leagueteamlinks']) + 1
    made = []
    for pc_tid, spec in legend_teams.items():
        club_id = resolve(spec['club'])
        donor = template_team[club_id]
        tid = str(next_team)
        next_team += 1
        team = dict(donor)
        team['teamid'] = team['assetid'] = tid
        t['teams'].append(team)
        teams[tid] = team
        long_name = spec['name']
        b.strings[f'TeamName_{tid}'] = long_name
        # The 15-letter name (Kick Off's, the tables'): the whole name when it fits (Arsenal Legends), else the
        # club's short one with "Leg." (Real Madrid Leg.).
        b.strings[f'TeamName_Abbr15_{tid}'] = spec.get('abbr15') or (
            long_name if len(long_name) <= 15 else f"{spec.get('short', long_name)[:10]} Leg.")
        b.strings[f'TeamName_Abbr10_{tid}'] = spec.get('short', long_name)[:10]
        b.strings[f'TeamName_Abbr7_{tid}'] = spec.get('abbr7', spec.get('short', long_name))[:7]
        b.strings[f'TeamName_Abbr3_{tid}'] = spec['abbr3']
        b.strings[f'CT_TeamName_{tid}'] = spec.get('short', long_name)
        team['teamname'] = long_name
        for n, k in enumerate([x for x in t['teamkits'] if x['teamtechid'] == club_id]):
            t['teamkits'].append(dict(k, teamtechid=tid, teamkitid=str(next_kit)))
            next_kit += 1
        st = next((x for x in t['teamstadiumlinks'] if x['teamid'] == club_id), None)
        if st:
            t['teamstadiumlinks'].append(dict(st, teamid=tid))
        mgr = next((x for x in t['manager'] if x['teamid'] == club_id), None)
        t['manager'].append(dict(mgr or {'firstname': '', 'gender': '0', 'surname': 'Head Coach'}, teamid=tid))
        formation = dict(next(x for x in t['formations'] if x['teamid'] == club_id))
        formation.update(teamid=tid, formationid=str(next_formation))
        next_formation += 1
        t['formations'].append(formation)
        ltl = dict(template_link)
        for k in ltl:
            if k not in ('teamid', 'leagueid', 'prevleagueid', 'artificialkey'):
                ltl[k] = '0'
        ltl.update(teamid=tid, leagueid=league_id, prevleagueid=league_id, artificialkey=str(next_lkey))
        next_lkey += 1
        t['leagueteamlinks'].append(ltl)
        # The squad: its best MAX_SQUAD (the update's reach 51; the game's own clubs have at most 33).
        squad = sorted(pc_links[pc_tid], key=lambda r: -int(ours[clones.get(r['playerid'], r['playerid'])]
                                                          ['overallrating']))[:MAX_SQUAD]
        for r in squad:
            links.append({'teamid': tid, 'playerid': str(clones.get(r['playerid'], r['playerid'])),
                          'jerseynumber': str(r['jerseynumber']), 'position': '29'})
        report['legends'][tid] = {'name': long_name, 'club': int(club_id), 'source': int(pc_tid)}
        made.append({'teamid': int(tid), 'name': long_name, 'existing': False, 'kit_donor': int(club_id),
                     'crest_from': int(club_id), 'players': len(pc_links[pc_tid])})

    # --- every club's line-up, numbers and team ratings ---
    by_team = collections.defaultdict(list)
    for x in links:
        by_team[x['teamid']].append(x)
    redo = applied | set(report['legends'])
    final = []
    key = 0
    for tid, rows in by_team.items():
        if tid not in redo:
            for x in rows:
                final.append(dict(x, artificialkey=str(key)))
                key += 1
            continue
        squad = []
        seen = set()
        for x in rows:
            if x['playerid'] in seen or int(x['playerid']) not in ours:
                continue
            seen.add(x['playerid'])
            p = ours[int(x['playerid'])]
            squad.append({'x': x, 'player': p, 'pos': int(p['preferredposition1']), 'rating': int(p['overallrating']),
                          'age': 30})
        formation = next((f for f in t['formations'] if f['teamid'] == tid), None)
        chosen = b.line_up(squad, [int(formation[f'position{i}']) for i in range(11)]) if formation and \
            len(squad) >= 11 else {}
        numbers = set()
        for e in squad:
            n = int(e['x']['jerseynumber'] or 0)
            if not 0 < n < 100 or n in numbers:
                n = next(k for k in range(1, 100) if k not in numbers)
            numbers.add(n)
            role = chosen.get(id(e), 28 if e.get('bench') else 29)
            final.append(b.link(key, tid, e['player']['playerid'], role, n))
            key += 1
        if chosen and tid in teams:
            team = teams[tid]
            starters = [e for e in squad if id(e) in chosen]
            team['overallrating'] = team['matchdayoverallrating'] = str(round(sum(e['rating'] for e in starters) / 11))
            for field, group in (('attackrating', {fifa.ST, fifa.RW, fifa.LW, fifa.CAM, 20, 21, 22, 24, 26}),
                                 ('midfieldrating', {fifa.CM, fifa.CDM, fifa.RM, fifa.LM, fifa.CAM, 9, 11, 13, 15, 17, 19}),
                                 ('defenserating', {fifa.CB, fifa.RB, fifa.LB, fifa.GK, 2, 4, 6, 8})):
                xs = [e['rating'] for e in starters if e['pos'] in group] or [e['rating'] for e in starters]
                team[field] = team['matchday' + field] = str(round(sum(xs) / len(xs)))
            outfield = sorted((e for e in starters if e['pos'] != fifa.GK), key=lambda e: -e['rating'])
            captain = max(starters, key=lambda e: (int(e['player']['internationalrep']), e['rating']))
            team['captainid'] = captain['player']['playerid']
            for k in ('penaltytakerid', 'freekicktakerid', 'longkicktakerid', 'leftcornerkicktakerid',
                      'rightcornerkicktakerid'):
                team[k] = outfield[0]['player']['playerid']
    # Anyone left without a club joins the free agents (the game has no player without one).
    clubbed = {x['playerid'] for x in final if x['teamid'] not in national}
    for p in t['players']:
        if p['playerid'] not in clubbed:
            final.append(b.link(key, free_agents, p['playerid'], 29, 0))
            key += 1
    t['teamplayerlinks'] = final
    moved = {x['playerid'] for x in final}
    t['playerloans'] = [x for x in t['playerloans'] if x['playerid'] in moved and int(x['playerid']) not in rated]
    for team in t['teams']:  # kickers and captains still in the team
        squad = {x['playerid'] for x in final if x['teamid'] == team['teamid']}
        for k in ('captainid', 'penaltytakerid', 'freekicktakerid', 'longkicktakerid', 'leftcornerkicktakerid',
                  'rightcornerkicktakerid'):
            if team.get(k) not in squad and squad and team['teamid'] != free_agents:
                team[k] = max(squad, key=lambda pid: int(ours[int(pid)]['overallrating']) if int(pid) in ours else 0)

    b.changed = {'players', 'dcplayernames', 'editedplayernames', 'teamplayerlinks', 'teams', 'leagues', 'leagueteamlinks', 'teamkits',
                 'teamstadiumlinks', 'manager', 'formations', 'playerloans', 'competition', 'career_boardoutcomes',
                 'referee', 'leaguerefereelinks'}
    b.report = {'teams': [], 'league_id': int(league_id), 'league_logos': legends_cfg.get('league_logos', {})}
    b.source = []
    os.makedirs(out, exist_ok=True)
    for name in sorted(b.changed):
        fifa.write(os.path.join(out, name + '.csv'), t[name])
    os.makedirs(os.path.dirname(strings_path) or '.', exist_ok=True)
    with open(strings_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['stringid', 'text'])
        for k, v in sorted(b.strings.items()):
            w.writerow([k, v])
    legends = {'league_id': int(league_id), 'league_logos': legends_cfg.get('league_logos', {}), 'teams': made,
               'player_copies': {str(v): k for k, v in clones.items()}}
    report['legend_copies'] = len(clones)
    json.dump(legends, open(os.path.join(out, 'legends.json'), 'w'), indent=1, ensure_ascii=False)
    report['applied_teams'] = len(applied)
    report['players'] = len(t['players'])
    report['links'] = len(final)
    json.dump(report, open(os.path.join(out, 'pcsquads.json'), 'w'), indent=1, ensure_ascii=False)
    return report


def main(argv):
    if len(argv) not in (6, 7):
        print(__doc__, file=sys.stderr)
        return 2
    cfg = json.load(open(argv[1]))
    r = build(cfg, argv[2], argv[3], argv[4], argv[5], argv[6] if len(argv) > 6 else None)
    print(f"PC squads: {r['applied_teams']} squads, {len(r['rated'])} players rated from the file "
          f"({r['taken_over']} ids someone else's now, {r['new_players']} new), {len(r['legends'])} Legends teams; "
          f"{r['players']} players, {r['links']} links" +
          f"; {r['legend_copies']} legends still playing (copied for the Legends); names not in the file: "
          f"{r['names_from_espn']} from ESPN, {r['names_made_up']} made up")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
