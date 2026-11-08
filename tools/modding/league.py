#!/usr/bin/env python3
"""Adds a league to the game's database from a source's squads (ESPN's, see sources/espn.py).

  league.py CONFIG.json CSVDIR ESPNDIR OUTCSVDIR STRINGS.csv [PCSQUADS.json]

CONFIG (tools/modding/leagues/*.json): the league's ids and names, the clubs the game already has (their assets
kept), the rating range. CSVDIR: the game's tables (tools/modding/db.sh export). Writes the changed tables to
OUTCSVDIR (for db.sh mod / fifadb.py import) and the new names to STRINGS.csv (a mod's strings/eng_us.csv), and
OUTCSVDIR/league.json: what was made (teams, kit donors, logos), for the assets and competition steps.
PCSQUADS.json (pcsquads.py's report, when its update came first): the players it rated keep their ratings, and
the Legends' players aren't taken for the league.

How players are made:
- A player the game has (same surname and birth date, or same full name and birth year) keeps his id, so his
  face, hair and boots; his ratings move from the game's (2018) to today's by his age and his playing time.
- A new player: ratings from his club's strength (the league table) and his share of its minutes, goals and
  assists for attackers; attributes from the game's players of his position and rating; looks from a player of
  his nationality with a generic head; boots from the game's own mix.
- Ages: the game's calendar starts in 2018, so birth dates are moved back by CONFIG's age_shift_years (8 for
  2026) to keep each player's real age (build_update.sh's last step, calendar_shift.py, moves the calendar and
  every date forward again).
"""
import csv
import datetime
import hashlib
import html
import json
import os
import sys

EPOCH = datetime.date(1582, 10, 14)  # the game's day 0 (birthdate, playerjointeamdate)
# New names: dcplayernames' ids (13 bits from 34000; the meta says to 40000) and its name field (38 bytes with the
# terminating zero).
DC_NAMES = (34000, 42191)
DC_NAME_BYTES = 37
EDITED_NAME_BYTES = 44  # editedplayernames' names: 45 bytes with the zero


class NamesFull(Exception):
    """No ids left for new names."""

# FIFA position codes.
GK, RB, CB, LB, CDM, RM, CM, LM, CAM, ST, RW, LW = 0, 3, 5, 7, 10, 12, 14, 16, 18, 25, 23, 27
ATTRIBUTES = ['crossing', 'finishing', 'headingaccuracy', 'shortpassing', 'volleys', 'dribbling', 'curve',
              'freekickaccuracy', 'longpassing', 'ballcontrol', 'acceleration', 'sprintspeed', 'agility',
              'reactions', 'balance', 'shotpower', 'jumping', 'stamina', 'strength', 'longshots', 'aggression',
              'interceptions', 'positioning', 'vision', 'penalties', 'marking', 'standingtackle',
              'slidingtackle', 'gkdiving', 'gkhandling', 'gkkicking', 'gkpositioning', 'gkreflexes']
STYLE = ['preferredfoot', 'weakfootabilitytypecode', 'skillmoves', 'attackingworkrate', 'defensiveworkrate',
         'trait1', 'trait2', 'gksavetype', 'gkkickstyle', 'runningcode1', 'runningcode2', 'finishingcode1',
         'finishingcode2', 'animfreekickstartposcode', 'animpenaltiesstartposcode', 'animpenaltieskickstylecode',
         'animpenaltiesmotionstylecode']
LOOKS = ['headtypecode', 'headclasscode', 'hairtypecode', 'haircolorcode', 'facialhairtypecode',
         'facialhaircolorcode', 'eyebrowcode', 'eyecolorcode', 'skintypecode', 'skintonecode', 'sideburnscode',
         'hashighqualityhead']
KIT = ['shoetypecode', 'shoedesigncode', 'shoecolorcode1', 'shoecolorcode2', 'gkglovetypecode', 'socklengthcode',
       'jerseysleevelengthcode', 'jerseystylecode', 'shortstyle', 'jerseyfit']


def read(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write(path, rows):
    if not rows:
        return
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def stable(*parts):
    """A number from the parts, the same every run (choices that look random but don't change)."""
    return int(hashlib.sha1('|'.join(map(str, parts)).encode()).hexdigest()[:8], 16)


def fold(s):
    import unicodedata
    s = html.unescape(s)
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('-', ' ').replace("'", '').strip()


def days(date):
    return (date - EPOCH).days


def from_days(n):
    return EPOCH + datetime.timedelta(days=int(n))


def shifted(date, years):
    try:
        return date.replace(year=date.year - years)
    except ValueError:  # 29 February
        return date.replace(year=date.year - years, day=28)


def stat_block(path):
    if not os.path.exists(path):
        return {}
    d = json.load(open(path))
    out = {}
    for cat in d.get('splits', {}).get('categories', []):
        for s in cat.get('stats', []):
            out[s['name']] = s.get('value') or 0
    return out


class Builder:
    def __init__(self, config, csvdir, espndir):
        self.cfg = config
        self.csvdir = csvdir
        self.espn = espndir
        self.t = {}
        for name in ('teams', 'leagueteamlinks', 'leagues', 'teamplayerlinks', 'players', 'playernames',
                     'dcplayernames', 'editedplayernames', 'teamkits', 'formations', 'manager', 'teamstadiumlinks', 'rowteamnationlinks', 'nations',
                     'career_boardoutcomes', 'referee', 'leaguerefereelinks', 'playerloans', 'competition'):
            self.t[name] = read(os.path.join(csvdir, name + '.csv'))
        self.changed = {'teams', 'leagueteamlinks', 'leagues', 'teamplayerlinks', 'players', 'dcplayernames',
                        'teamkits', 'formations', 'manager', 'teamstadiumlinks', 'rowteamnationlinks',
                        'career_boardoutcomes', 'referee', 'leaguerefereelinks', 'playerloans', 'competition'}
        self.nation_by_name = {fold(n['nationname']): int(n['nationid']) for n in self.t['nations']}
        self.names = {int(n['nameid']): n['name'] for n in self.t['playernames'] + self.t['dcplayernames']}
        self.name_ids = {}
        for nid, text in self.names.items():
            self.name_ids.setdefault(text, nid)
        # The characters the game's names use: a name with another (ё, ə, ț) crashed it at boot.
        self.charset = {c for n in self.t['playernames'] for c in n['name']}
        self.next_name = max([DC_NAMES[0] - 1] + [int(n['nameid']) for n in self.t['dcplayernames']]) + 1
        self.players = {int(p['playerid']): p for p in self.t['players']}
        self.strings = {}
        self.used_donors = set()
        self.report = {'teams': [], 'new_players': 0, 'matched_players': 0, 'unmatched_nationality': []}
        self.keep = set()  # players whose ratings are kept (rated from a better source: pcsquads.py)
        self.protected = set()  # teams whose players aren't matched (the Legends: their own 2010s selves)

    def use_pcsquads(self, path):
        """Takes pcsquads.py's report: the players it rated keep their ratings, the Legends keep their players."""
        if path and os.path.exists(path):
            r = json.load(open(path))
            self.keep = set(map(int, r.get('rated', [])))
            self.protected = set(r.get('legends', {}))

    # --- names -------------------------------------------------------------------------------------------------
    def name_id(self, text):
        """A name's id: the game's row with this text, else a new name (dcplayernames: the names table itself stays
        as the game has it; rewriting or growing it crashed the game at boot)."""
        text = self.representable(text.strip())
        while len(text.encode('utf-8')) > DC_NAME_BYTES:
            text = text[:-1].rstrip()
        if not text:
            return 0
        if text in self.name_ids:
            return self.name_ids[text]
        nid = self.next_name
        if nid > DC_NAMES[1]:
            raise NamesFull(f'more new names than the game takes ({DC_NAMES[1] - DC_NAMES[0] + 1}: dcplayernames)')
        self.next_name += 1
        self.t['dcplayernames'].append({'nameid': str(nid), 'name': text})
        self.names[nid] = text
        self.name_ids[text] = nid
        return nid

    def set_names(self, p, first, last, common='', jersey=''):
        """A player's names: their ids (name_id), or, once the new names' ids are used up, the names themselves in
        editedplayernames (as the game keeps a name edited in Edit Player), the ids then 0."""
        texts = [first, last, common, jersey or common or last]
        try:
            ids = [self.name_id(x) if x else 0 for x in texts]
        except NamesFull:
            ids = None
        fields = ('firstnameid', 'lastnameid', 'commonnameid', 'playerjerseynameid')
        if ids is not None:
            for f, nid in zip(fields, ids):
                p[f] = str(nid)
            return
        for f in fields:
            p[f] = '0'
        cut = [self.representable(x.strip()) for x in texts]
        cut = [x.encode('utf-8')[:EDITED_NAME_BYTES].decode('utf-8', 'ignore') for x in cut]
        self.t['editedplayernames'] = [x for x in self.t['editedplayernames'] if x['playerid'] != p['playerid']]
        self.t['editedplayernames'].append({'playerid': p['playerid'], 'firstname': cut[0], 'surname': cut[1],
                                            'commonname': cut[2], 'playerjerseyname': cut[3]})
        self.changed.add('editedplayernames')

    def representable(self, text):
        """The text in the game's characters: others without their marks (ț as t), else a near letter."""
        import unicodedata
        out = []
        for c in text:
            if c in self.charset:
                out.append(c)
                continue
            base = ''.join(x for x in unicodedata.normalize('NFKD', c) if not unicodedata.combining(x))
            base = ''.join(x for x in base if x in self.charset)
            out.append(base or {'ə': 'e', 'Ə': 'E', 'ı': 'i', 'ł': 'l', 'Ł': 'L', 'ø': 'o', 'Ø': 'O', 'đ': 'd',
                                'Đ': 'D', 'ß': 'ss', 'æ': 'ae', 'œ': 'oe', '’': "'", 'ʼ': "'"}.get(c, ''))
        return ''.join(out)

    # --- source --------------------------------------------------------------------------------------------------
    def load_source(self):
        league = self.cfg['source_league']
        teams = json.load(open(f'{self.espn}/{league}-teams.json'))['sports'][0]['leagues'][0]['teams']
        table = json.load(open(f'{self.espn}/{league}-standings.json'))
        ppg = {}
        for e in table['children'][0]['standings']['entries']:
            st = {s['name']: s.get('value') or 0 for s in e['stats']}
            ppg[e['team']['id']] = (st.get('points', 0) / max(st.get('gamesPlayed', 1), 1), st.get('rank', 99))
        self.source = []
        for t in teams:
            t = t['team']
            roster = json.load(open(f"{self.espn}/{league}-roster-{t['id']}.json")).get('athletes', [])
            self.source.append({'team': t, 'ppg': ppg.get(t['id'], (1.0, 99)), 'roster': roster})
        lo = min(s['ppg'][0] for s in self.source)
        hi = max(s['ppg'][0] for s in self.source)
        r0, r1 = self.cfg['team_rating_range']
        for s in self.source:
            s['strength'] = r0 + (r1 - r0) * ((s['ppg'][0] - lo) / (hi - lo) if hi > lo else 0.5)

    def stats(self, athlete):
        seasons = self.cfg['seasons']
        blocks = [stat_block(f"{self.espn}/stats/{athlete}-{season}.json") for season in seasons]
        total = {}
        for b in blocks:
            for k, v in b.items():
                total[k] = total.get(k, 0) + v
        return total

    # --- matching the game's players ------------------------------------------------------------------------------
    def index_players(self):
        self.by_key = {}
        protected = {x['playerid'] for x in self.t['teamplayerlinks'] if x['teamid'] in self.protected}
        for p in self.t['players']:
            if p['playerid'] in protected:
                continue
            first = fold(self.names.get(int(p['firstnameid']), ''))
            last = fold(self.names.get(int(p['lastnameid']), ''))
            common = fold(self.names.get(int(p['commonnameid']), ''))
            born = from_days(p['birthdate'])
            for key in ((last, born), (common, born) if common else None, (f'{first} {last}', born.year)):
                if key:
                    self.by_key.setdefault(key, []).append(p)
            self.by_key.setdefault(born, []).append((p, set(f'{first} {last} {common}'.split())))
            for name in {last, common} - {''}:
                self.by_key.setdefault((name, born.month, born.day), []).append(p)
            self.by_key.setdefault((born.month, born.day), []).append((p, f'{first} {last}'.strip(), common))

    def match(self, a, born):
        """The game's player for a source's athlete born on that day (or, when born is the real date, on the
        same day age_shift_years earlier, as this tool's updates store births)."""
        last, first = fold(a.get('lastName', '')), fold(a.get('firstName', ''))
        dates = [born]
        if self.cfg.get('age_shift_years'):
            dates.append(shifted(born, self.cfg['age_shift_years']))
        for when in dates:
            for key in ((last, when), (fold(a.get('displayName', '')), when)):
                hits = self.by_key.get(key, [])
                if hits:  # the same name and birthday twice (an update's duplicate): the real head, the better
                    return max(hits, key=lambda p: (p['hashighqualityhead'] == '1', int(p['overallrating'])))
            hits = self.by_key.get((f'{first} {last}', when.year), [])
            if len(hits) == 1:
                return hits[0]
        # The same name and birthday, the year a little off (updates make young players older: the PC update's
        # Quansah, born 2003, is 2002's): the nearest within three years.
        for name in (last, fold(a.get('displayName', ''))):
            for when in dates:
                hits = [p for p in self.by_key.get((name, when.month, when.day), [])
                        if abs(from_days(p['birthdate']).year - when.year) <= 3]
                if hits:
                    return min(hits, key=lambda p: abs(from_days(p['birthdate']).year - when.year))
        # A misspelt name (an update's Jarrod Branthwate for Jarrad Branthwaite), the same birthday, the year
        # within three: the one whose name is nearest, when near enough.
        import difflib
        full, shown = f'{first} {last}'.strip(), fold(a.get('displayName', ''))
        scored = []
        for when in dates:
            for p, name, common in self.by_key.get((when.month, when.day), []):
                if abs(from_days(p['birthdate']).year - when.year) <= 3:
                    score = max(difflib.SequenceMatcher(None, x, y).ratio() for x in (full, shown) for y in (name, common))
                    scored.append((score, p['playerid'], p))
        scored.sort(key=lambda x: -x[0])
        if scored and scored[0][0] >= 0.8 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.1 or
                                               scored[1][1] == scored[0][1]):
            return scored[0][2]
        # Born the same day and a name in common (Gabriel for Gabriel Magalhaes, Bruno Guimaraes for Bruno
        # Guimaraes Rodriguez Moura): the one such player.
        words = {w for w in f"{first} {last} {fold(a.get('displayName', ''))}".split() if len(w) > 2}
        for when in dates:
            hits = [p for p, names in self.by_key.get(when, []) if words & {w for w in names if len(w) > 2}]
            if len(hits) == 1:
                return hits[0]
        return None

    # --- making a player ---------------------------------------------------------------------------------------
    def templates(self):
        self.by_pos = {}
        for p in self.t['players']:
            self.by_pos.setdefault(int(p['preferredposition1']), []).append(p)
        self.generic = {}
        for p in self.t['players']:
            if p['hashighqualityhead'] == '0':
                self.generic.setdefault(int(p['nationality']), []).append(p)
        self.everyone = [p for p in self.t['players'] if p['hashighqualityhead'] == '0']

    def template(self, pos, rating, seed):
        pool = self.by_pos.get(pos) or self.by_pos[CM]
        for width in (0, 1, 2, 4, 8, 99):
            near = [p for p in pool if abs(int(p['overallrating']) - rating) <= width]
            if len(near) >= 3 or width == 99:
                return sorted(near, key=lambda p: int(p['playerid']))[seed % len(near)]

    def rating_for(self, team_strength, st, pos, age):
        apps = st.get('appearances', 0)
        minutes = st.get('minutes', 0)
        share = min(minutes / (90 * 30 * len(self.cfg['seasons']) * 0.85), 1.0)
        r = team_strength - 6 + 9 * share ** 0.6
        if pos in (ST, RW, LW, CAM) and minutes > 300:
            per90 = (st.get('totalGoals', 0) + 0.6 * st.get('goalAssists', 0)) * 90 / minutes
            r += min(per90 * 6, 4)
        if pos == GK and apps < 3:
            r -= 3
        if age < 20:
            r -= 4
        elif age < 22:
            r -= 2
        elif age > 33:
            r -= age - 33
        return max(48, min(86, round(r)))

    def potential_for(self, rating, age):
        return max(rating, min(92, rating + max(0, 26 - age) * 2 + (2 if age < 21 else 0)))

    def scaled_attributes(self, tmpl, rating):
        diff = rating - int(tmpl['overallrating'])
        out = {}
        for a in ATTRIBUTES:
            v = int(tmpl[a])
            # Keep the template's strengths: a player's good attributes move with his rating, the rest less.
            out[a] = str(max(10, min(95, v + round(diff * (1.0 if v >= 50 else 0.4)))))
        return out

    def new_player(self, a, born, pos, rating, nation, seed):
        tmpl = self.template(pos, rating, seed)
        donors = self.generic.get(nation) or self.everyone
        looks = sorted(donors, key=lambda p: int(p['playerid']))[stable('looks', seed) % len(donors)]
        boots = self.everyone[stable('boots', seed) % len(self.everyone)]
        p = dict(tmpl)
        p.update(self.scaled_attributes(tmpl, rating))
        for k in LOOKS:
            p[k] = looks[k]
        for k in KIT:
            p[k] = boots[k]
        if pos == GK:
            gks = [x for x in self.everyone if x['preferredposition1'] == '0']
            p['gkglovetypecode'] = gks[stable('gloves', seed) % len(gks)]['gkglovetypecode']
        p['playerid'] = str(self.next_player)
        self.next_player += 1
        first, last = html.unescape(a.get('firstName', '')).strip(), html.unescape(a.get('lastName', '')).strip()
        if not last:
            first, last = '', html.unescape(a.get('displayName', '')).strip()
        shown = html.unescape(a.get('displayName', '')).strip()
        if shown and shown != f'{first} {last}'.strip() and len(shown.split()) <= 2:
            # Known by another name (Brazilians' Pedro, Wendel): shown and on the shirt as that.
            self.set_names(p, first, last, shown, shown.split()[-1] if len(shown.split()) == 2 and
                           shown.split()[-1] == last else shown)
        else:
            self.set_names(p, first, last)
        p['nationality'] = str(nation)
        p['preferredposition1'] = str(pos)
        for k in ('preferredposition2', 'preferredposition3', 'preferredposition4'):
            p[k] = '-1'
        left, right = self._feet.get(a['id'], (0, 0))
        if left + right >= 6:
            p['preferredfoot'] = '2' if left > right * 1.5 else '1'
        p['isretiring'] = '0'
        p['usercaneditname'] = '1'
        p['gender'] = '0'
        p['hasseasonaljersey'] = '0'
        self.t['players'].append(p)
        self.players[int(p['playerid'])] = p
        self.report['new_players'] += 1
        return p

    def update_existing(self, p, rating):
        old = int(p['overallrating'])
        diff = rating - old
        for a in ATTRIBUTES:
            v = int(p[a])
            p[a] = str(max(10, min(95, v + round(diff * (1.0 if v >= 50 else 0.4)))))
        self.report['matched_players'] += 1

    # --- the league ----------------------------------------------------------------------------------------------
    def build(self):
        cfg = self.cfg
        self.load_source()
        self.index_players()
        self.templates()
        self.next_player = max(cfg['first_player_id'], max(self.players) + 1)
        self._feet = {}
        next_team = cfg['first_team_id']
        next_key = max(int(x['artificialkey']) for x in self.t['teamplayerlinks']) + 1
        next_lkey = max(int(x['artificialkey']) for x in self.t['leagueteamlinks']) + 1
        next_kit = max(int(x['teamkitid']) for x in self.t['teamkits']) + 1
        next_formation = max(int(x['formationid']) for x in self.t['formations']) + 1
        today = datetime.date.fromisoformat(cfg['today'])
        shift = cfg['age_shift_years']
        league = cfg['league_id']
        national = {x['teamid'] for x in self.t['leagueteamlinks'] if x['leagueid'] in ('78', '2136')}
        free_agents = cfg['free_agents_team_id']
        teams_by_id = {x['teamid']: x for x in self.t['teams']}
        template_team = dict(teams_by_id[str(cfg['template_team_id'])])
        template_link = dict(next(x for x in self.t['leagueteamlinks'] if x['teamid'] == str(cfg['template_team_id'])))

        # The league.
        lrow = dict(next(x for x in self.t['leagues'] if x['leagueid'] == str(cfg['template_league_id'])))
        lrow.update(leagueid=str(league), leaguename=cfg['database_name'], countryid=str(cfg['nation_id']),
                    level='1')
        self.t['leagues'] = [x for x in self.t['leagues'] if x['leagueid'] != str(league)] + [lrow]
        for key, text in cfg['league_strings'].items():
            self.strings[key.format(id=league)] = text
        self.league_extras(league)

        made = []
        for s in sorted(self.source, key=lambda s: s['ppg'][1]):
            t = s['team']
            existing = cfg['existing_teams'].get(t['id'])
            if existing:
                tid = int(existing)
                team = teams_by_id[str(tid)]
            else:
                tid = next_team
                next_team += 1
                team = dict(template_team)
                team['teamid'] = team['assetid'] = str(tid)
                self.t['teams'].append(team)
            names = cfg['team_names'].get(t['id'], {})
            long_name = names.get('name', t['displayName'])
            team['teamname'] = long_name
            colors = [t.get('color') or '000000', t.get('alternateColor') or 'ffffff']
            if colors[0].lower() == '000000' and colors[1].lower() not in ('000000', 'ffffff'):
                colors = colors[::-1]
            rgb = [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in colors]
            rgb.append((255, 255, 255) if sum(rgb[0]) < 384 else (20, 20, 20))
            for n, (r, g, b) in enumerate(rgb[:3], 1):
                team[f'teamcolor{n}r'], team[f'teamcolor{n}g'], team[f'teamcolor{n}b'] = str(r), str(g), str(b)
            if not existing:
                abbr = names.get('abbr3', t.get('abbreviation', long_name[:3]).upper())
                short = names.get('short', t.get('shortDisplayName', long_name))
                self.strings[f'TeamName_{tid}'] = long_name
                self.strings[f'TeamName_Abbr15_{tid}'] = long_name[:15] if len(long_name) <= 15 else short[:15]
                self.strings[f'TeamName_Abbr10_{tid}'] = short[:10]
                self.strings[f'TeamName_Abbr7_{tid}'] = short[:7]
                self.strings[f'TeamName_Abbr3_{tid}'] = abbr[:3]
                self.strings[f'CT_TeamName_{tid}'] = short

            # Its squad: the old one leaves (to free agents), the source's comes in.
            old_links = [x for x in self.t['teamplayerlinks'] if x['teamid'] == str(tid)]
            squad_ids = set()
            squad = []
            for a in s['roster']:
                try:
                    born_real = datetime.date.fromisoformat(a['dateOfBirth'][:10])
                except (KeyError, ValueError):
                    born_real = today.replace(year=today.year - 25)
                age = (today - born_real).days // 365
                born = shifted(born_real, shift)
                st = self.stats(a['id'])
                self._feet[a['id']] = (st.get('leftFootedShots', 0), st.get('rightFootedShots', 0))
                letter = (a.get('position') or {}).get('abbreviation', 'M')[:1]
                nation = self.nation_by_name.get(fold(a.get('citizenship', '')), cfg['nation_id'])
                if fold(a.get('citizenship', '')) not in self.nation_by_name:
                    self.report['unmatched_nationality'].append(a.get('citizenship', ''))
                p = self.match(a, born_real) or self.match(a, born)
                squad.append({'a': a, 'born': born, 'age': age, 'st': st, 'letter': letter, 'nation': nation,
                              'player': p})
            self.assign_positions(squad)
            for e in squad:
                e['rating'] = self.rating_for(s['strength'], e['st'], e['pos'], e['age'])
                seed = stable(e['a']['id'])
                if e['player'] is not None and int(e['player']['playerid']) in self.keep:
                    p = e['player']  # rated already (pcsquads.py): only his club (and his true birthday) change
                    e['pos'], e['rating'] = int(p['preferredposition1']), int(p['overallrating'])
                    p['birthdate'] = str(days(e['born']))
                    self.report['matched_players'] += 1
                    squad_ids.add(p['playerid'])
                    continue
                if e['player'] is not None:
                    p = e['player']
                    game_pos = int(p['preferredposition1'])
                    if (game_pos == GK) == (e['pos'] == GK):
                        e['pos'] = game_pos
                    # Today's rating: the game's for him, aged to now, and his playing time's, half each.
                    old = int(p['overallrating'])
                    old_age = (datetime.date(2018, 9, 1) - from_days(p['birthdate'])).days // 365 + shift
                    aged = old - max(0, old_age - 31) * 2 + (max(0, min(int(p['potential']) - old, (26 - old_age + shift) * 2)) if old_age - shift < 24 else 0)
                    e['rating'] = max(45, min(90, round((aged + e['rating']) / 2)))
                    self.update_existing(p, e['rating'])
                else:
                    p = self.new_player(e['a'], e['born'], e['pos'], e['rating'], e['nation'], seed)
                    e['player'] = p
                p['overallrating'] = str(e['rating'])
                p['potential'] = str(self.potential_for(e['rating'], e['age']))
                p['birthdate'] = str(days(e['born']))
                if e['a'].get('height'):
                    p['height'] = str(max(155, min(205, round(e['a']['height'] * 2.54))))
                if e['a'].get('weight'):
                    p['weight'] = str(max(50, min(110, round(e['a']['weight'] * 0.4536))))
                p['playerjointeamdate'] = str(days(shifted(today, shift)) - 200)
                p['contractvaliduntil'] = str(2020 + stable('contract', e['a']['id']) % 4)  # the game's 2018
                p['internationalrep'] = str(1 + (e['rating'] >= 74) + (e['rating'] >= 79) + (e['rating'] >= 84))
                squad_ids.add(p['playerid'])
            # The game's players who left go to free agents; this squad's players leave their old clubs.
            leaving = {x['playerid'] for x in old_links} - squad_ids
            self.t['teamplayerlinks'] = [x for x in self.t['teamplayerlinks']
                                         if not (x['teamid'] == str(tid) or
                                                 (x['playerid'] in squad_ids and x['teamid'] not in national))]
            for pid in sorted(leaving):
                if not any(x['playerid'] == pid and x['teamid'] not in national for x in self.t['teamplayerlinks']):
                    self.t['teamplayerlinks'].append(self.link(next_key, free_agents, pid, 29, 0))
                    next_key += 1
            self.t['playerloans'] = [x for x in self.t['playerloans'] if x['playerid'] not in squad_ids]
            # Line-up: a formation and who plays where.
            formation = self.formation_for(tid, existing, next_formation)
            if not existing:
                next_formation += 1
            numbers = set()
            for e in squad:
                n = e['a'].get('jersey')
                e['number'] = int(n) if n and n.isdigit() and 0 < int(n) < 100 and int(n) not in numbers else 0
                numbers.add(e['number'])
            free = (n for n in range(1, 100) if n not in numbers)
            for e in squad:
                if not e['number']:
                    e['number'] = next(free)
            slots = [int(formation[f'position{i}']) for i in range(11)]
            chosen = self.line_up(squad, slots)
            for e in squad:
                role = chosen.get(id(e))
                if role is None:
                    role = 28 if e.get('bench') else 29
                self.t['teamplayerlinks'].append(self.link(next_key, tid, e['player']['playerid'], role, e['number']))
                next_key += 1
            # The team's numbers.
            starters = [e for e in squad if id(e) in chosen]
            def avg(group):
                xs = [e['rating'] for e in starters if e['pos'] in group] or [e['rating'] for e in starters]
                return str(round(sum(xs) / len(xs)))
            team['overallrating'] = team['matchdayoverallrating'] = str(round(sum(e['rating'] for e in starters) / 11))
            team['attackrating'] = team['matchdayattackrating'] = avg({ST, RW, LW, CAM})
            team['midfieldrating'] = team['matchdaymidfieldrating'] = avg({CM, CDM, RM, LM, CAM})
            team['defenserating'] = team['matchdaydefenserating'] = avg({CB, RB, LB, GK})
            best = sorted(starters, key=lambda e: -e['rating'])
            outfield = [e for e in best if e['pos'] != GK]
            captain = max(starters, key=lambda e: (e['age'] > 25, e['rating']))
            team['captainid'] = captain['player']['playerid']
            for k in ('penaltytakerid', 'freekicktakerid', 'longkicktakerid', 'leftcornerkicktakerid',
                      'rightcornerkicktakerid'):
                team[k] = outfield[0]['player']['playerid']
            strength = s['strength']
            team['domesticprestige'] = str(max(1, min(10, round((strength - 60) / 2))))
            team['internationalprestige'] = str(max(1, min(10, round((strength - 63) / 2))))
            team['popularity'] = team['domesticprestige']
            team['transferbudget'] = str(int(max(1, strength - 62) ** 2 * 150000))
            # League membership.
            self.t['leagueteamlinks'] = [x for x in self.t['leagueteamlinks'] if x['teamid'] != str(tid)]
            ltl = dict(template_link)
            for k in ltl:
                if k not in ('teamid', 'leagueid', 'prevleagueid', 'artificialkey'):
                    ltl[k] = '0'
            ltl.update(teamid=str(tid), leagueid=str(league), prevleagueid=str(league),
                       artificialkey=str(next_lkey), previousyeartableposition=str(int(s['ppg'][1])),
                       currenttableposition=str(int(s['ppg'][1])))
            next_lkey += 1
            self.t['leagueteamlinks'].append(ltl)
            self.t['rowteamnationlinks'] = [x for x in self.t['rowteamnationlinks'] if x['teamid'] != str(tid)]
            if not existing:
                self.new_team_rows(tid, team, rgb, next_kit, s)
                next_kit += 4
            made.append({'source_id': t['id'], 'teamid': tid, 'name': long_name, 'existing': bool(existing),
                         'colors': colors, 'logo': (t.get('logos') or [{}])[0].get('href'),
                         'strength': round(strength, 1), 'players': len(squad)})
        # Rivals within the league for the new teams.
        ids = [m['teamid'] for m in made]
        for m in made:
            team = teams_by_id.get(str(m['teamid'])) or next(x for x in self.t['teams'] if x['teamid'] == str(m['teamid']))
            if not m['existing']:
                team['rivalteam'] = str(ids[(ids.index(m['teamid']) + 1) % len(ids)])
        self.report['teams'] = made
        self.report['league_id'] = league
        self.report['league_logos'] = cfg.get('league_logos', {})

    def league_extras(self, league):
        """What Career mode needs of a league besides its teams: the board's objectives and referees."""
        cfg, template = self.cfg, str(self.cfg['template_league_id'])
        # The competition's row (its ball, the pole flags), keyed by the league's id as the competition's asset.
        self.t['competition'] = [x for x in self.t['competition'] if x['competitionid'] != str(league)]
        self.t['competition'] += [dict(x, competitionid=str(league)) for x in self.t['competition']
                                  if x['competitionid'] == template]
        self.t['career_boardoutcomes'] = [x for x in self.t['career_boardoutcomes'] if x['leagueid'] != str(league)]
        for x in [x for x in self.t['career_boardoutcomes'] if x['leagueid'] == template]:
            self.t['career_boardoutcomes'].append(dict(x, leagueid=str(league)))
        old = {x['refereeid'] for x in self.t['referee'] if x['leagueid'] == str(league)}
        self.t['referee'] = [x for x in self.t['referee'] if x['refereeid'] not in old]
        self.t['leaguerefereelinks'] = [x for x in self.t['leaguerefereelinks'] if x['leagueid'] != str(league)]
        donors = [x for x in self.t['referee'] if x['leagueid'] == template]
        next_ref = max(int(x['refereeid']) for x in self.t['referee']) + 1
        for n, (first, last) in enumerate(cfg['referees']):
            row = dict(donors[n % len(donors)])
            row.update(refereeid=str(next_ref), leagueid=str(league), firstname=first, surname=last,
                       nationalitycode=str(cfg['nation_id']))
            self.t['referee'].append(row)
            self.t['leaguerefereelinks'].append({'leagueid': str(league), 'refereeid': str(next_ref)})
            next_ref += 1

    def assign_positions(self, squad):
        """G/D/M/F to the game's positions: the game's own for players it has, else by role in the squad."""
        by_letter = {}
        for e in squad:
            by_letter.setdefault(e['letter'], []).append(e)
        order = {'G': [GK], 'D': [CB, RB, CB, LB, CB, RB, LB, CB], 'M': [CM, CDM, CAM, RM, LM, CM, CDM, CAM, CM],
                 'F': [ST, LW, RW, ST, ST]}
        for letter, group in by_letter.items():
            seq = order.get(letter, [CM])
            group.sort(key=lambda e: -e['st'].get('minutes', 0))
            if letter == 'F':
                group.sort(key=lambda e: -(e['st'].get('totalGoals', 0) * 2 + e['st'].get('minutes', 0) / 300))
            for i, e in enumerate(group):
                e['pos'] = seq[i % len(seq)]
                if e['player'] is not None and (int(e['player']['preferredposition1']) == GK) == (letter == 'G'):
                    e['pos'] = int(e['player']['preferredposition1'])

    def line_up(self, squad, slots):
        """{id(entry): slot position} for the best eleven, and 'bench' marks on the next seven."""
        family = {GK: {GK}, 3: {RB, 2, CB}, 2: {RB, 2}, 4: {CB}, 5: {CB}, 6: {CB}, 7: {LB, 8, CB}, 8: {LB, 8},
                  9: {CDM, CM}, 10: {CDM, CM}, 11: {CDM, CM}, 12: {RM, RW, CM}, 13: {CM, CDM, CAM},
                  14: {CM, CDM, CAM}, 15: {CM, CDM, CAM}, 16: {LM, LW, CM}, 17: {CAM, CM}, 18: {CAM, CM},
                  19: {CAM, CM}, 20: {ST, 21, CAM}, 21: {ST, 21, CAM}, 22: {ST, 21, CAM}, 23: {RW, RM, ST},
                  24: {ST, 21}, 25: {ST, 21}, 26: {ST, 21}, 27: {LW, LM, ST}}
        left = sorted(squad, key=lambda e: -e['rating'])
        chosen = {}
        for slot in sorted(slots, key=lambda s: s != GK):  # keeper first
            fits = [e for e in left if e['pos'] in family.get(slot, {slot})]
            if not fits:
                fits = [e for e in left if (e['pos'] == GK) == (slot == GK)] or left
            e = fits[0]
            chosen[id(e)] = slot
            left.remove(e)
        keepers = [e for e in left if e['pos'] == GK][:1]
        for e in keepers + [e for e in left if e['pos'] != GK][:7 - len(keepers)]:
            e['bench'] = True
        return chosen

    def link(self, key, teamid, playerid, position, number):
        return {'isamongtopscorers': '0', 'yellows': '0', 'isamongtopscorersinteam': '0', 'leaguegoals': '0',
                'jerseynumber': str(number), 'position': str(position), 'artificialkey': str(key),
                'teamid': str(teamid), 'injury': '0', 'leagueappearances': '0', 'istopscorer': '0',
                'playerid': str(playerid), 'form': '3', 'reds': '0'}

    def formation_for(self, tid, existing, formation_id):
        rows = [x for x in self.t['formations'] if x['teamid'] == str(tid)]
        if rows:
            return rows[0]
        donor = next(x for x in self.t['formations'] if x['teamid'] == str(self.cfg['template_team_id']))
        if self.cfg.get('formation_from_team'):
            donor = next(x for x in self.t['formations'] if x['teamid'] == str(self.cfg['formation_from_team']))
        row = dict(donor)
        row.update(teamid=str(tid), formationid=str(formation_id))
        self.t['formations'].append(row)
        return row

    def new_team_rows(self, tid, team, rgb, kit_id, s):
        cfg = self.cfg
        donor = cfg['kit_donors'][str(s['team']['id'])] if str(s['team']['id']) in cfg.get('kit_donors', {}) \
            else self.kit_donor(rgb[0])
        s['kit_donor'] = donor
        for n, k in enumerate([x for x in self.t['teamkits'] if x['teamtechid'] == str(donor)]):
            row = dict(k)
            row.update(teamtechid=str(tid), teamkitid=str(kit_id + n))
            if row['teamkittypetechid'] == '0':
                for i, name in enumerate(('prim', 'sec', 'tert')):
                    r, g, b = rgb[i]
                    row[f'teamcolor{name}r'], row[f'teamcolor{name}g'], row[f'teamcolor{name}b'] = str(r), str(g), str(b)
            self.t['teamkits'].append(row)
        stadiums = cfg['generic_stadiums']
        st = next(x for x in self.t['teamstadiumlinks'] if x['stadiumid'] == str(stadiums[tid % len(stadiums)]))
        self.t['teamstadiumlinks'].append({'stadiumid': st['stadiumid'],
                                           'stadiumname': cfg['stadium_names'].get(str(s['team']['id']), st['stadiumname']),
                                           'teamid': str(tid)})
        coach = cfg['coaches'].get(str(s['team']['id']), ['', 'Head Coach'])
        self.t['manager'].append({'firstname': coach[0], 'gender': '0', 'surname': coach[1], 'teamid': str(tid)})

    def kit_donor(self, rgb):
        """A club whose home kit's main colour is nearest this one (its kit files and settings are copied)."""
        leagues = set(map(str, self.cfg['kit_donor_leagues']))
        allowed = {x['teamid'] for x in self.t['leagueteamlinks'] if x['leagueid'] in leagues}
        allowed -= {str(m) for m in self.used_donors}
        allowed = {t for t in allowed if int(t) < 120000}  # the game's own: a club made here has no kit files
        best = None
        for k in self.t['teamkits']:
            if k['teamkittypetechid'] != '0' or k['teamtechid'] not in allowed:
                continue
            c = (int(k['teamcolorprimr']), int(k['teamcolorprimg']), int(k['teamcolorprimb']))
            d = sum((a - b) ** 2 for a, b in zip(c, rgb))
            if best is None or d < best[0]:
                best = (d, int(k['teamtechid']))
        self.used_donors.add(best[1])
        return best[1]

    def write(self, out, strings_path):
        os.makedirs(out, exist_ok=True)
        for name in sorted(self.changed):
            write(os.path.join(out, name + '.csv'), self.t[name])
        os.makedirs(os.path.dirname(strings_path) or '.', exist_ok=True)
        with open(strings_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['stringid', 'text'])
            for k, v in sorted(self.strings.items()):
                w.writerow([k, v])
        for m in self.report['teams']:
            src = next(s for s in self.source if s['team']['id'] == m['source_id'])
            m['kit_donor'] = src.get('kit_donor')
        json.dump(self.report, open(os.path.join(out, 'league.json'), 'w'), indent=1, ensure_ascii=False)


def main(argv):
    if len(argv) not in (6, 7):
        print(__doc__, file=sys.stderr)
        return 2
    cfg = json.load(open(argv[1]))
    b = Builder(cfg, argv[2], argv[3])
    b.use_pcsquads(argv[6] if len(argv) > 6 else None)
    b.build()
    b.write(argv[4], argv[5])
    r = b.report
    print(f"{cfg['database_name']}: {len(r['teams'])} teams, {r['matched_players']} of the game's players, "
          f"{r['new_players']} new")
    for m in r['teams']:
        print(f"  {m['teamid']:7} {m['name']:28} strength {m['strength']:5} players {m['players']}"
              + ('' if m['existing'] else f"  kits from {m.get('kit_donor')}"))
    if r['unmatched_nationality']:
        print('nationalities not found (Russia used):', sorted(set(r['unmatched_nationality'])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
