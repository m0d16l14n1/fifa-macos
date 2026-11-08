#!/usr/bin/env python3
"""Fetches a league's squads, table and player season statistics from ESPN's public JSON API (no key; paced).

  espn.py LEAGUE OUTDIR [SEASON...]     e.g. espn.py rus.1 out/moddata/espn 2026 2025 (none: squads only)

Writes OUTDIR/LEAGUE-teams.json, -standings.json, -roster-<team>.json and stats/<athlete>-<season>.json
(already fetched files are kept: a rerun only fetches what is missing). Standard library only.
"""
import concurrent.futures
import json
import os
import sys
import time
import urllib.request

SITE = 'https://site.api.espn.com/apis/site/v2/sports/soccer'
CORE = 'https://sports.core.api.espn.com/v2/sports/soccer/leagues'


def fetch(url, path, pause=0.35):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return json.load(open(path))
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'fifa-macos-modding/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                data = b'{}'
                break
            time.sleep(2 + 3 * attempt)
        except Exception:
            time.sleep(2 + 3 * attempt)
    else:
        raise SystemExit(f'could not fetch {url}')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(data)
    time.sleep(pause)
    return json.loads(data)


def main(league, out, seasons):
    teams = fetch(f'{SITE}/{league}/teams', f'{out}/{league}-teams.json')
    fetch(f'https://site.api.espn.com/apis/v2/sports/soccer/{league}/standings', f'{out}/{league}-standings.json')
    ids = [t['team']['id'] for t in teams['sports'][0]['leagues'][0]['teams']]
    athletes = []
    for tid in ids:
        roster = fetch(f'{SITE}/{league}/teams/{tid}/roster', f'{out}/{league}-roster-{tid}.json')
        athletes += [a['id'] for a in roster.get('athletes', [])]
    seasons = [s for s in seasons if s != 'none']
    jobs = [(f'{CORE}/{league}/seasons/{season}/types/1/athletes/{aid}/statistics', f'{out}/stats/{aid}-{season}.json')
            for aid in athletes for season in seasons]
    with concurrent.futures.ThreadPoolExecutor(6) as pool:  # six at a time, each pausing after its request
        for n, _ in enumerate(pool.map(lambda job: fetch(*job), jobs)):
            if n % 100 == 0:
                print(f'{league}: {n}/{len(jobs)} statistics', flush=True)
    print(f'{league}: {len(ids)} teams, {len(athletes)} players')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or ['2026'])
