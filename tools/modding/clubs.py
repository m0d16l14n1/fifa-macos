"""New clubs in the game's leagues, and the clubs they push out (league.Builder's tables).

A league's size is fixed by its competition (compdata), so a club the game hasn't (Wrexham) comes in only as one of
the game's leaves: the club leaving is the template of the new one (its league's level, prestige, budget, tactics),
and goes to Rest of World (league 76: in the game, playable, out of Career's leagues), as the game keeps the
clubs it has no league for. The new club's kits come from a club whose colours are nearest (league.py's
kit_donor), its crest from its logo (teamassets.py), or drawn with its initials when it has none.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import league as fifa  # noqa: E402

REST_OF_WORLD = '76'
GENERIC_STADIUMS = [34, 228, 176, 178, 193, 249, 180, 33, 179, 197, 32, 158]
KIT_DONOR_LEAGUES = [1, 41, 56, 66, 80, 189, 65, 50, 13, 14, 60, 61, 19, 20, 2076, 53, 54, 31, 32, 16, 17]


def rgb_of(hex_colors):
    colors = [c or '000000' for c in hex_colors[:2]] + ['ffffff'] * (2 - len(hex_colors[:2]))
    if colors[0].lower() == '000000' and colors[1].lower() not in ('000000', 'ffffff'):
        colors = colors[::-1]
    rgb = [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in colors]
    rgb.append((255, 255, 255) if sum(rgb[0]) < 384 else (20, 20, 20))
    return colors, rgb


def initials(name):
    words = [w for w in fifa.fold(name).upper().replace('.', ' ').split() if w.isalpha()]
    skip = {'FC', 'SC', 'SV', 'TSV', 'KS', 'GKS', 'CF', 'AFC', 'CITY', 'UNITED', 'TOWN', 'CLUB'}
    core = [w for w in words if w not in skip] or words
    if len(core) == 1:
        return core[0][:3]
    return ''.join(w[0] for w in core[:3])


class Clubs:
    def __init__(self, builder):
        self.b = builder
        t = builder.t
        # From 125000: Russia's clubs are 120000 on, the Legends 121000 on; the game has crests of its own at 130000.
        self.next_team = max([125000] + [int(x['teamid']) + 1 for x in t['teams'] if 125000 <= int(x['teamid']) < 130000])
        self.next_kit = max(int(x['teamkitid']) for x in t['teamkits']) + 1
        self.next_formation = max(int(x['formationid']) for x in t['formations']) + 1
        self.next_lkey = max(int(x['artificialkey']) for x in t['leagueteamlinks']) + 1
        if not hasattr(builder, 'used_donors'):
            builder.used_donors = set()
        builder.cfg.setdefault('kit_donor_leagues', KIT_DONOR_LEAGUES)
        builder.changed |= {'teams', 'leagueteamlinks', 'teamkits', 'formations', 'manager', 'teamstadiumlinks',
                            'rowteamnationlinks'}
        self.made = []  # for teamassets.py (league.json's teams)
        self.left = []

    def leave(self, tid):
        """The club leaves its league for Rest of World (the game's clubs without a league)."""
        tid = str(tid)
        t = self.b.t
        link = next(x for x in t['leagueteamlinks'] if x['teamid'] == tid)
        leagues = {x['leagueid']: x for x in t['leagues']}
        country = leagues[link['leagueid']]['countryid']
        name = next(x['teamname'] for x in t['teams'] if x['teamid'] == tid)
        self.left.append({'teamid': tid, 'name': name, 'from': leagues[link['leagueid']]['leaguename']})
        link['prevleagueid'], link['leagueid'] = link['leagueid'], REST_OF_WORLD
        t['rowteamnationlinks'] = [x for x in t['rowteamnationlinks'] if x['teamid'] != tid]
        t['rowteamnationlinks'].append({'teamid': tid, 'nationid': country})
        return link

    def add(self, name, short, abbr3, hex_colors, league_id, template_tid, logo=None, source_id=None):
        """A new club in league_id, in template_tid's place (that club leaves for Rest of World). Returns its row."""
        b, t = self.b, self.b.t
        template_tid = str(template_tid)
        template = next(x for x in t['teams'] if x['teamid'] == template_tid)
        link = self.leave(template_tid)
        tid = self.next_team
        self.next_team += 1
        team = dict(template)
        team.update(teamid=str(tid), assetid=str(tid), teamname=name, rivalteam=template_tid, genericbanner='1')
        colors, rgb = rgb_of(hex_colors)
        for n, (r, g, bl) in enumerate(rgb[:3], 1):
            team[f'teamcolor{n}r'], team[f'teamcolor{n}g'], team[f'teamcolor{n}b'] = str(r), str(g), str(bl)
        t['teams'].append(team)
        abbr = (abbr3 or initials(name))[:3].upper()
        b.strings[f'TeamName_{tid}'] = name
        b.strings[f'TeamName_Abbr15_{tid}'] = name if len(name) <= 15 else short[:15]
        b.strings[f'TeamName_Abbr10_{tid}'] = short[:10]
        b.strings[f'TeamName_Abbr7_{tid}'] = short[:7]
        b.strings[f'TeamName_Abbr3_{tid}'] = abbr
        b.strings[f'CT_TeamName_{tid}'] = short
        new_link = dict(link, teamid=str(tid), leagueid=link['prevleagueid'], prevleagueid=link['prevleagueid'],
                        artificialkey=str(self.next_lkey))
        self.next_lkey += 1
        t['leagueteamlinks'].append(new_link)
        donor = b.kit_donor(rgb[0])
        for n, k in enumerate([x for x in t['teamkits'] if x['teamtechid'] == str(donor)]):
            row = dict(k, teamtechid=str(tid), teamkitid=str(self.next_kit + n))
            if row['teamkittypetechid'] == '0':
                for i, part in enumerate(('prim', 'sec', 'tert')):
                    r, g, bl = rgb[i]
                    row[f'teamcolor{part}r'], row[f'teamcolor{part}g'], row[f'teamcolor{part}b'] = str(r), str(g), str(bl)
            t['teamkits'].append(row)
        self.next_kit += 8
        stadium = GENERIC_STADIUMS[tid % len(GENERIC_STADIUMS)]
        st = next((x for x in t['teamstadiumlinks'] if x['stadiumid'] == str(stadium)), None)
        t['teamstadiumlinks'].append({'stadiumid': str(stadium), 'stadiumname': f'{short} Stadium' if not st
                                      else st['stadiumname'], 'teamid': str(tid)})
        t['manager'].append({'firstname': '', 'gender': '0', 'surname': 'Head Coach', 'teamid': str(tid)})
        formation = next((x for x in t['formations'] if x['teamid'] == template_tid), None) or \
            next(x for x in t['formations'] if x['teamid'] == '1')
        t['formations'].append(dict(formation, teamid=str(tid), formationid=str(self.next_formation)))
        self.next_formation += 1
        self.made.append({'source_id': source_id or f'club-{tid}', 'teamid': tid, 'name': name, 'existing': False,
                          'colors': colors, 'logo': logo, 'crest_text': None if logo else abbr,
                          'kit_donor': donor, 'replaces': template_tid})
        return team

    def report(self, league_id=None):
        return {'league_id': league_id, 'league_logos': {}, 'teams': self.made, 'left': self.left}
