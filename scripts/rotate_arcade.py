#!/usr/bin/env python3
"""Daily shuffle bag. Prepare metadata; never edit the live profile here."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import random
import re
from datetime import date, datetime, timezone
from pathlib import Path

NATIVE = ('minecraft', 'lego', 'bomber', 'miners', 'link-match', 'portal', 'assembly')
LEGACY = ('space-shooter', 'breakout', 'snake', 'maze-chase', '3d-city')
RETIRED = ('defense', 'pinball', 'laser', 'gravity')
ARCADE_EXPERIENCES = LEGACY + NATIVE
CATALOG_VERSION = 4
EXPERIENCE_DETAILS = {
    'space-shooter': {'title': 'Space Shooter', 'icon': '🚀', 'description': "Today's contribution grid has entered bullet-hell mode.", 'light': './assets/arcade/space-shooter.gif'},
    'breakout': {'title': 'Breakout', 'icon': '🧱', 'description': "A tiny paddle is clearing the year's contribution bricks.", 'light': './assets/arcade/breakout-light.svg', 'dark': './assets/arcade/breakout-dark.svg'},
    'snake': {'title': 'Snake', 'icon': '🐍', 'description': 'The classic contribution snake is having lunch.', 'light': './assets/arcade/snake-light.svg', 'dark': './assets/arcade/snake-dark.svg'},
    'maze-chase': {'title': 'Maze Chase', 'icon': '👻', 'description': 'Dots, ghosts, and a full year of commits to chase.', 'light': './assets/arcade/maze-chase-light.svg', 'dark': './assets/arcade/maze-chase-dark.svg'},
    '3d-city': {'title': '3D Contribution City', 'icon': '🏙️', 'description': "Today's commits have been rebuilt as a tiny skyline.", 'light': './assets/arcade/3d-city.svg'},
}
for key, title, description in [
    ('bomber', 'Heatmap Bomber', 'A tiny bomber finds safe routes through your green days, one wall at a time.'),
    ('miners', 'Commit Miners', 'Two miners work through the whole calendar. Every ore tile is a real active day.'),
    ('link-match', 'Contribution Link', 'Match equal green levels through empty days, with no more than two turns.'),
    ('portal', 'Portal Courier', 'Your contribution tiles take the long way home, through a pair of portals.'),
    ('assembly', 'Magnetic Assembly', 'Your calendar breaks into connected pieces, then clicks back into its exact original shape.'),
    ('minecraft', 'Minecraft Block Miner', 'Mine your green days into grass blocks, collect them, then rebuild the whole calendar.'),
    ('lego', 'LEGO Brick Workshop', 'Studded bricks ride the conveyor, lift into place, and click your contribution calendar back together.'),
]:
    EXPERIENCE_DETAILS[key] = {'title': title, 'icon': '', 'description': description,
        'light': f'./assets/arcade/heatmap-{key}-light.svg', 'dark': f'./assets/arcade/heatmap-{key}-dark.svg'}
START_MARKER, END_MARKER = '<!-- ARCADE:START -->', '<!-- ARCADE:END -->'


def valid_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Expected YYYY-MM-DD')
    return date.fromisoformat(value).isoformat()


def clean_state(state):
    current = state.get('current')
    if current not in ARCADE_EXPERIENCES:
        current = None
    remaining = list(dict.fromkeys(n for n in state.get('remaining', []) if n in ARCADE_EXPERIENCES and n != current))
    if (state.get('current') is not None or state.get('remaining')) and state.get('catalog_version') != CATALOG_VERSION:
        remaining = [n for n in NATIVE if n != current]+[n for n in remaining if n not in NATIVE]
    return {**state, 'current': current, 'remaining': remaining,
            'cycle': max(0, int(state.get('cycle', 0))), 'catalog_version': CATALOG_VERSION}


def choose_next(state, rng):
    state = clean_state(state)
    remaining = state['remaining'][:]
    if not remaining:
        remaining = list(ARCADE_EXPERIENCES)
        rng.shuffle(remaining)
        if remaining[0] == state['current']:
            remaining[0], remaining[1] = remaining[1], remaining[0]
        state['cycle'] += 1
    selected = remaining.pop(0)
    return selected, {**state, 'current': selected, 'remaining': remaining}


def force_selection(state, selected):
    if selected not in ARCADE_EXPERIENCES:
        raise ValueError(f'Unknown arcade experience: {selected}')
    state = clean_state(state)
    return {**state, 'current': selected, 'remaining': [n for n in state['remaining'] if n != selected]}


def select_daily(state, day, requested='random', seed=''):
    day = valid_day(day)
    previous = state.get('updated_on', '')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', previous) and previous > day:
        raise ValueError('Refusing to rewind a published date')
    if (requested == 'random' and previous == day and state.get('catalog_version') == CATALOG_VERSION
            and state.get('current') in ARCADE_EXPERIENCES):
        return state['current'], clean_state(state)
    if requested == 'random':
        selected, result = choose_next(state, random.Random(f'{day}:{seed}'))
    else:
        selected, result = requested, force_selection(state, requested)
    return selected, {**result, 'updated_on': day}


def render_arcade_block(selected, day=None):
    d = EXPERIENCE_DETAILS[selected]
    lines = [f"## Today's Arcade: {d['title']} {d['icon']}".rstrip(), '', d['description'], '',
             '<p align="center">', '  <picture>']
    if d.get('dark'):
        lines += ['    <source media="(prefers-color-scheme: dark)"', f'            srcset="{d["dark"]}">']
    lines += [f'    <img src="{d["light"]}" alt="{d["title"]}" width="100%">', '  </picture>', '</p>', '']
    stamp = f' · Updated {valid_day(day)} UTC' if day else ''
    lines += [f'<p align="center"><sub>{len(ARCADE_EXPERIENCES)} cartridges · a fresh daily draw · no back-to-back repeats{stamp}</sub></p>', '',
              '[Explore the SVG arcade](./ARCADE.md)']
    return '\n'.join(lines)


def replace_arcade_block(readme, block):
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError('README must contain exactly one arcade marker block')
    pattern = re.compile(re.escape(START_MARKER)+'.*?'+re.escape(END_MARKER), re.DOTALL)
    result, count = pattern.subn(lambda _: f'{START_MARKER}\n{block}\n{END_MARKER}', readme)
    if count != 1:
        raise ValueError('README arcade markers are reversed')
    return result


def read_state(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state', type=Path, default=Path('.github/arcade-state.json'))
    p.add_argument('--readme', type=Path, default=Path('README.md'))
    p.add_argument('--output-dir', type=Path, default=Path('rotation-output'))
    p.add_argument('--seed', default=os.environ.get('GITHUB_REPOSITORY_OWNER', 'WSL043'))
    p.add_argument('--experience', choices=('random',)+ARCADE_EXPERIENCES, default='random')
    p.add_argument('--generation-mode', choices=('selected', 'all'), default='selected')
    p.add_argument('--refresh-native', choices=('true', 'false'), default='true')
    p.add_argument('--github-output', default=os.environ.get('GITHUB_OUTPUT'))
    p.add_argument('--date', default=os.environ.get('ARCADE_DATE', datetime.now(timezone.utc).date().isoformat()))
    args = p.parse_args()
    selected, state = select_daily(read_state(args.state), args.date, args.experience, args.seed)
    readme = args.readme.read_text(encoding='utf-8')
    native = args.generation_mode == 'all' or args.refresh_native == 'true' or selected in NATIVE
    selection = {'selected': selected, 'mode': args.generation_mode, 'date': args.date,
                 'refresh_native': args.refresh_native == 'true', 'engine': 'svg-v3',
                 'readme_sha256': hashlib.sha256(readme.encode()).hexdigest()}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in [('arcade-state.next.json', state), ('selection.json', selection)]:
        (args.output_dir/name).write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    (args.output_dir/'README.next.md').write_text(replace_arcade_block(readme, render_arcade_block(selected, args.date)), encoding='utf-8')
    if args.github_output:
        with Path(args.github_output).open('a', encoding='utf-8') as out:
            for key, value in {'selected': selected, 'mode': args.generation_mode, 'native': str(native).lower()}.items():
                out.write(f'{key}={value}\n')
    print(f'Selected {selected} for {args.date}')

if __name__ == '__main__':
    main()
