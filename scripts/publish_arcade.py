#!/usr/bin/env python3
"""Validate everything before staging a single, all-or-nothing Git commit."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from pathlib import Path
try:
    from scripts.rotate_arcade import ARCADE_EXPERIENCES, NATIVE
except ModuleNotFoundError:
    from rotate_arcade import ARCADE_EXPERIENCES, NATIVE

ASSET_MAP = {
    'space-shooter': (('space-shooter.gif', 'space-shooter.gif'),),
    'breakout': tuple((f'breakout-{t}.svg', f'breakout-{t}.svg') for t in ('light', 'dark')),
    'snake': tuple((f'snake-{t}.svg', f'snake-{t}.svg') for t in ('light', 'dark')),
    'maze-chase': tuple((f'maze-chase-{t}.svg', f'maze-chase-{t}.svg') for t in ('light', 'dark')),
    '3d-city': (('3d-city.svg', '3d-city.svg'),),
    **{s: tuple((f'heatmap-{s}-{t}.gif', f'heatmap-{s}-{t}.gif') for t in ('light', 'dark')) for s in NATIVE},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_gif(path):
    from PIL import Image
    if path.stat().st_size > 8_000_000:
        raise ValueError(f'Oversized GIF: {path.name}')
    with Image.open(path) as im:
        if im.format != 'GIF' or im.size != (1040, 420) or not 2 <= im.n_frames <= 400:
            raise ValueError(f'Invalid animated GIF: {path.name}')
        for i in range(im.n_frames):
            im.seek(i); im.load()


def publish(root: Path, staging: Path) -> None:
    metadata, artifacts = staging/'rotation-metadata', staging/'generators'
    selection = json.loads((metadata/'selection.json').read_text(encoding='utf-8'))
    selected, mode = selection['selected'], selection.get('mode', 'selected')
    if selected not in ARCADE_EXPERIENCES or mode not in ('selected', 'all'):
        raise ValueError('Invalid selected experience or generation mode')
    modules = list(ARCADE_EXPERIENCES if mode == 'all' else (selected,))
    if selection.get('refresh_native'):
        modules = list(dict.fromkeys(modules+list(NATIVE)))
    copies = []
    for module in modules:
        for source, destination in ASSET_MAP[module]:
            path = artifacts/source
            if not path.is_file() or path.stat().st_size == 0:
                raise FileNotFoundError(f'Missing generated asset for {module}: {source}')
            copies.append((path, root/'assets'/'arcade'/destination))
    next_readme, next_state = metadata/'README.next.md', metadata/'arcade-state.next.json'
    if not next_readme.is_file() or not next_state.is_file():
        raise FileNotFoundError('Rotation metadata is incomplete')
    state = json.loads(next_state.read_text(encoding='utf-8'))
    if 'date' in selection:
        if state.get('current') != selected or state.get('updated_on') != selection['date']:
            raise ValueError('Selection and state do not match')
        if digest(root/'README.md') != selection.get('readme_sha256'):
            raise ValueError('Live README changed since selection; refusing to overwrite')
    native = [m for m in modules if m in NATIVE]
    if native:
        manifest_path, snapshot_path = artifacts/'heatmap-manifest.json', artifacts/'heatmap-snapshot.json'
        manifest = json.loads(manifest_path.read_text())
        snapshot = json.loads(snapshot_path.read_text())
        if (manifest['date'] != selection.get('date') or manifest['source'] != 'github-graphql'
                or snapshot.get('source') != 'github-graphql' or snapshot.get('as_of') != selection['date']
                or digest(snapshot_path) != manifest['snapshot_sha256']
                or set(manifest['scenes']) != set(native)):
            raise ValueError('Native manifest or source does not match the selected day')
        expected = {src for m in native for src, _ in ASSET_MAP[m]}
        if set(manifest['assets']) != expected:
            raise ValueError('Manifest asset allowlist mismatch')
        for name in expected:
            if digest(artifacts/name) != manifest['assets'][name]:
                raise ValueError(f'Asset digest mismatch: {name}')
            validate_gif(artifacts/name)
        copies += [(manifest_path, root/'assets'/'arcade'/manifest_path.name),
                   (snapshot_path, root/'assets'/'arcade'/snapshot_path.name)]
    # No live file is touched before every source and all metadata are validated.
    for source, destination in copies+[(next_readme, root/'README.md'), (next_state, root/'.github'/'arcade-state.json')]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--staging', type=Path, default=Path('staging'))
    args = p.parse_args()
    publish(args.root.resolve(), args.staging.resolve())

if __name__ == '__main__':
    main()
