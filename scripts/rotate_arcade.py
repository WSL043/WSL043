#!/usr/bin/env python3
"""Prepare a deterministic daily shuffle-bag rotation, without touching live files."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import random
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

NATIVE = ('bomber', 'miners', 'defense', 'pinball', 'laser', 'gravity')
LEGACY = ('space-shooter', 'breakout', 'snake', 'maze-chase', '3d-city')
ARCADE_EXPERIENCES = LEGACY + NATIVE
CATALOG_VERSION = 2
EXPERIENCE_DETAILS = {
    'space-shooter': {'title': 'Space Shooter', 'icon': '🚀', 'description': "Today's contribution grid has entered bullet-hell mode.", 'light': './assets/arcade/space-shooter.gif'},
    'breakout': {'title': 'Breakout', 'icon': '🧱', 'description': "A tiny paddle is clearing the year's contribution bricks.", 'light': './assets/arcade/breakout-light.svg', 'dark': './assets/arcade/breakout-dark.svg'},
    'snake': {'title': 'Snake', 'icon': '🐍', 'description': 'The classic contribution snake is having lunch.', 'light': './assets/arcade/snake-light.svg', 'dark': './assets/arcade/snake-dark.svg'},
    'maze-chase': {'title': 'Maze Chase', 'icon': '👻', 'description': 'Dots, ghosts, and a full year of commits to chase.', 'light': './assets/arcade/maze-chase-light.svg', 'dark': './assets/arcade/maze-chase-dark.svg'},
    '3d-city': {'title': '3D Contribution City', 'icon': '🏙️', 'description': "Today's commits have been rebuilt as a tiny skyline.", 'light': './assets/arcade/3d-city.svg'},
}
for key, title, description in [
    ('bomber', 'Heatmap Bomber', 'Find a route, plant a bomb, escape. Your green days are the walls.'),
    ('miners', 'Commit Miners', 'Two tiny robots mine your contribution tiles. Higher levels take longer to dig.'),
    ('defense', 'Contribution Defense', 'Active days become towers. Bugs find routes through the empty days.'),
    ('pinball', 'Heatmap Pinball', 'Three ricocheting balls chip away at your real contribution tiles.'),
    ('laser', 'Laser Reflection', 'Your green days reflect laser beams. Every impact drains one level.'),
    ('gravity', 'Contribution Sand', 'Your calendar crumbles into coloured grains that fall, collide and pile up.'),
]:
    EXPERIENCE_DETAILS[key] = {'title': title, 'icon': '', 'description': description,
        'light': f'./assets/arcade/heatmap-{key}-light.gif', 'dark': f'./assets/arcade/heatmap-{key}-dark.gif'}

START_MARKER, END_MARKER = '<!-- ARCADE:START -->', '<!-- ARCADE:END -->'


def valid_day(value: str) -> str:
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Expected YYYY-MM-DD')
    return date.fromisoformat(value).isoformat()


def clean_state(state: dict[str, Any]) -> dict[str, Any]:
    current = state.get('current')
    remaining = list(dict.fromkeys(n for n in state.get('remaining', [])
                                  if n in ARCADE_EXPERIENCES and n != current))
    # An old nonempty bag gains the new cartridges immediately, once only.
    if state.get('catalog_version') != CATALOG_VERSION and remaining:
        remaining = [n for n in NATIVE if n != current] + [n for n in remaining if n not in NATIVE]
    return {**state, 'current': current, 'remaining': remaining,
            'cycle': max(0, int(state.get('cycle', 0))), 'catalog_version': CATALOG_VERSION}


def choose_next(state: dict[str, Any], rng: random.Random) -> tuple[str, dict[str, Any]]:
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


def force_selection(state: dict[str, Any], selected: str) -> dict[str, Any]:
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


def render_arcade_block(selected: str, day: str | None = None) -> str:
    d = EXPERIENCE_DETAILS[selected]
    lines = [f"## Today's Arcade: {d['title']} {d['icon']}".rstrip(), '', d['description'], '',
             '<p align="center">', '  <picture>']
    if d.get('dark'):
        lines += ['    <source media="(prefers-color-scheme: dark)"', f'            srcset="{d["dark"]}">']
    lines += [f'    <img src="{d["light"]}" alt="{d["title"]}" width="100%">',
              '  </picture>', '</p>', '']
    stamp = f' · Published {valid_day(day)} UTC' if day else ''
    lines += [f'<p align="center"><sub>11 cartridges · one daily draw · no back-to-back repeats{stamp}</sub></p>', '',
              '[Watch all six heatmap demos](./ARCADE.md) · Auto-play simulations, driven by contribution tiles.']
    return '\n'.join(lines)


def replace_arcade_block(readme: str, block: str) -> str:
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError('README must contain exactly one arcade marker block')
    pattern = re.compile(re.escape(START_MARKER)+'.*?'+re.escape(END_MARKER), re.DOTALL)
    result, n = pattern.subn(lambda _: f'{START_MARKER}\n{block}\n{END_MARKER}', readme)
    if n != 1:
        raise ValueError('README arcade markers are reversed')
    return result


def read_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def write_github_output(path: str | None, values: dict[str, str]) -> None:
    if path:
        with Path(path).open('a', encoding='utf-8') as out:
            for key, value in values.items():
                out.write(f'{key}={value}\n')


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--state', type=Path, default=Path('.github/arcade-state.json'))
    p.add_argument('--readme', type=Path, default=Path('README.md'))
    p.add_argument('--output-dir', type=Path, default=Path('rotation-output'))
    p.add_argument('--seed', default=os.environ.get('GITHUB_REPOSITORY_OWNER', 'WSL043'))
    p.add_argument('--experience', choices=('random',)+ARCADE_EXPERIENCES, default='random')
    p.add_argument('--generation-mode', choices=('selected', 'all'), default='selected')
    p.add_argument('--refresh-native', choices=('true', 'false'), default='false')
    p.add_argument('--github-output', default=os.environ.get('GITHUB_OUTPUT'))
    p.add_argument('--date', default=os.environ.get('ARCADE_DATE', datetime.now(timezone.utc).date().isoformat()))
    args = p.parse_args()
    selected, state = select_daily(read_state(args.state), args.date, args.experience, args.seed)
    readme = args.readme.read_text(encoding='utf-8')
    native = args.generation_mode == 'all' or args.refresh_native == 'true' or selected in NATIVE
    selection = {'selected': selected, 'mode': args.generation_mode, 'date': args.date,
                 'refresh_native': args.refresh_native == 'true',
                 'readme_sha256': hashlib.sha256(readme.encode()).hexdigest()}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in [('arcade-state.next.json', state), ('selection.json', selection)]:
        (args.output_dir/name).write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    (args.output_dir/'README.next.md').write_text(replace_arcade_block(readme, render_arcade_block(selected, args.date)), encoding='utf-8')
    write_github_output(args.github_output, {'selected': selected, 'mode': args.generation_mode, 'native': str(native).lower()})
    print(f'Selected {selected} for {args.date}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
