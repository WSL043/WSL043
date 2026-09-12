#!/usr/bin/env python3
"""Fetch fresh contribution levels and produce verified, theme-aware vector SVGs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from scripts.rotate_arcade import NATIVE, valid_day
from scripts.svg_models import Calendar, PLANNERS
from scripts.svg_arcade import render
from scripts.search_race import comparison, render_comparison

LEVELS = {name: i for i, name in enumerate(('NONE', 'FIRST_QUARTILE', 'SECOND_QUARTILE', 'THIRD_QUARTILE', 'FOURTH_QUARTILE'))}
QUERY = '''query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){contributionsCollection(from:$from,to:$to){
    contributionCalendar{weeks{contributionDays{date weekday contributionLevel}}}
  }}
}'''


def normalize(payload, owner, day):
    end = date.fromisoformat(valid_day(day))
    begin = end-timedelta(days=364)
    if payload.get('errors'):
        raise ValueError('GitHub GraphQL returned errors; not using partial data')
    try:
        weeks = payload['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
    except (KeyError, TypeError) as exc:
        raise ValueError('Missing GitHub contribution calendar') from exc
    if not 52 <= len(weeks) <= 54:
        raise ValueError('Unexpected number of calendar weeks')
    columns, seen, starts = {}, set(), []
    for x, week in enumerate(weeks):
        cells, dates = [None]*7, []
        for d in week['contributionDays']:
            dt = date.fromisoformat(valid_day(d['date']))
            y, level = d['weekday'], LEVELS.get(d['contributionLevel'])
            if (type(y) is not int or not 0 <= y < 7 or y != (dt.weekday()+1) % 7
                    or dt in seen or not begin <= dt <= end or level is None or cells[y] is not None):
                raise ValueError('Invalid or duplicate contribution day')
            seen.add(dt)
            dates.append(dt)
            cells[y] = level
        if not dates:
            raise ValueError('Empty calendar week')
        sunday = min(dates)-timedelta(days=(min(dates).weekday()+1) % 7)
        if any(d-timedelta(days=(d.weekday()+1) % 7) != sunday for d in dates):
            raise ValueError('Mixed dates in a calendar week')
        if starts and sunday != date.fromisoformat(starts[-1])+timedelta(days=7):
            raise ValueError('Calendar weeks are not consecutive')
        starts.append(sunday.isoformat())
        columns[str(x)] = cells
    if seen != {begin+timedelta(days=i) for i in range(365)}:
        raise ValueError('Calendar does not contain the requested 365 days')
    return {'owner': owner, 'source': 'github-graphql', 'as_of': day, 'range_start': begin.isoformat(),
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'columns': len(weeks), 'rows': 7,
            'week_starts': starts, 'active_columns': columns,
            'note': 'Calendar positions and levels only. Game units are not contribution counts.'}


def fetch_calendar(owner, day, token):
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})', owner):
        raise ValueError('Invalid GitHub owner')
    if not token:
        raise ValueError('GH_TOKEN is required; refusing stale or fabricated fallback')
    end = date.fromisoformat(valid_day(day))
    begin = end-timedelta(days=364)
    body = json.dumps({'query': QUERY, 'variables': {'login': owner,
                      'from': begin.isoformat()+'T00:00:00Z', 'to': day+'T23:59:59Z'}}).encode()
    request = urllib.request.Request('https://api.github.com/graphql', data=body, headers={
        'Authorization': 'Bearer '+token, 'Content-Type': 'application/json',
        'Accept': 'application/vnd.github+json', 'User-Agent': 'WSL043-svg-arcade'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError('Oversized calendar response')
            return normalize(json.loads(raw), owner, day)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f'Calendar request failed with HTTP {exc.code}') from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError('Calendar request failed after three attempts') from None
        time.sleep(2**attempt)
    raise RuntimeError('Calendar unavailable')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(snapshot, selection, output):
    cal = Calendar.from_snapshot(snapshot)
    output.mkdir(parents=True, exist_ok=True)
    snapshot_path = output/'heatmap-snapshot.json'
    snapshot_path.write_text(json.dumps(snapshot, indent=2)+'\n', encoding='utf-8', newline='\n')
    scenes = NATIVE if selection.get('refresh_native') or selection.get('mode') == 'all' else (selection['selected'],)
    if any(s not in NATIVE for s in scenes):
        raise ValueError('Not a native SVG scene')
    hashes = {}
    for scene in scenes:
        seed = int.from_bytes(hashlib.sha256(f'{cal.owner}:{selection["date"]}:{scene}'.encode()).digest()[:8], 'big')
        model = PLANNERS[scene](cal, seed)
        for theme in ('dark', 'light'):
            asset = output/f'heatmap-{scene}-{theme}.svg'
            asset.write_text(render(cal, scene, seed, theme, model), encoding='utf-8')
            hashes[asset.name] = digest(asset)
    report = comparison(cal)
    report_path = output/'search-comparison.json'
    report_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    analysis = {report_path.name: digest(report_path)}
    for theme in ('dark', 'light'):
        asset = output/f'search-comparison-{theme}.svg'
        asset.write_text(render_comparison(cal, theme, report), encoding='utf-8')
        analysis[asset.name] = digest(asset)
    manifest = {'date': selection['date'], 'source': snapshot['source'], 'scenes': list(scenes), 'analysis': analysis,
                'engine': 'svg-v3', 'snapshot_sha256': digest(snapshot_path), 'assets': hashes}
    (output/'heatmap-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--owner', default=os.environ.get('GITHUB_REPOSITORY_OWNER', 'WSL043'))
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path('generated'))
    p.add_argument('--input', type=Path, help='Explicit offline snapshot; never publish as fresh data')
    args = p.parse_args()
    selection = json.loads(args.selection.read_text(encoding='utf-8'))
    if args.input:
        snapshot = json.loads(args.input.read_text(encoding='utf-8'))
        snapshot['source'] = 'offline-preview'
    else:
        snapshot = fetch_calendar(args.owner, selection['date'], os.environ.get('GH_TOKEN', ''))
    build(snapshot, selection, args.output)

if __name__ == '__main__':
    main()
