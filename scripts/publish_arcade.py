#!/usr/bin/env python3
"""Validate all artifacts before staging a single non-force Git commit."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
try:
    from scripts.rotate_arcade import ARCADE_EXPERIENCES, NATIVE
    from scripts.svg_models import Calendar
    from scripts.search_race import ANALYSIS_FILES, comparison, render_comparison
except ModuleNotFoundError:
    from rotate_arcade import ARCADE_EXPERIENCES, NATIVE
    from svg_models import Calendar
    from search_race import ANALYSIS_FILES, comparison, render_comparison

ASSET_MAP = {
    'space-shooter': (('space-shooter.gif', 'space-shooter.gif'),),
    **{s: tuple((f'{s}-{t}.svg', f'{s}-{t}.svg') for t in ('light', 'dark')) for s in ('breakout', 'snake', 'maze-chase')},
    '3d-city': (('3d-city.svg', '3d-city.svg'),),
    **{s: tuple((f'heatmap-{s}-{t}.svg', f'heatmap-{s}-{t}.svg') for t in ('light', 'dark')) for s in NATIVE},
}
OLD_GIFS = tuple(f'heatmap-{s}-{t}.gif' for s in ('bomber', 'miners', 'defense', 'pinball', 'laser', 'gravity') for t in ('light', 'dark'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_svg(path, scene, snapshot):
    if not 100 <= path.stat().st_size <= 3_000_000:
        raise ValueError('Invalid SVG size')
    raw = path.read_text(encoding='utf-8')
    if re.search(r'<!DOCTYPE|<!ENTITY|@import|url\s*\(|javascript:|data:', raw, re.I):
        raise ValueError('SVG contains an external or embedded resource')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError('Malformed SVG') from exc
    namespace = '{http://www.w3.org/2000/svg}'
    allowed = {'svg', 'title', 'desc', 'metadata', 'style', 'g', 'rect', 'path', 'circle', 'ellipse', 'text'}
    for element in root.iter():
        if element.tag not in {namespace+n for n in allowed}:
            raise ValueError('SVG contains a non-vector or executable element')
        for name in element.attrib:
            if name.lower().startswith('on') or name.lower().endswith('href'):
                raise ValueError('SVG contains an executable attribute')
    cal = Calendar.from_snapshot(snapshot)
    if root.tag != namespace+'svg' or root.get('viewBox') != f'0 0 {cal.cols*16+48} 216':
        raise ValueError('SVG must display the whole calendar')
    meta_node = root.find(namespace+'metadata')
    if meta_node is None:
        raise ValueError('Missing SVG metadata')
    meta = json.loads(meta_node.text or '{}')
    grid_sha = hashlib.sha256(json.dumps(sorted(cal.grid.items())).encode()).hexdigest()
    if (meta.get('format') != 'vector-css-svg' or meta.get('scene') != scene or root.get('data-scene') != scene
            or meta.get('date') != cal.day or meta.get('owner') != cal.owner
            or meta.get('active_days') != len(cal.active) or meta.get('grid_sha256') != grid_sha):
        raise ValueError('SVG data does not match the contribution snapshot')
    if not 1 <= meta.get('duration_seconds', 0) <= 180:
        raise ValueError('SVG loop duration out of bounds')
    if 'prefers-reduced-motion:reduce' not in raw or (cal.active and '@keyframes' not in raw):
        raise ValueError('Missing animation or reduced-motion fallback')


def publish(root, staging):
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
            if not path.is_file() or not path.stat().st_size:
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
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        if (manifest.get('engine') != 'svg-v3' or manifest['date'] != selection.get('date')
                or manifest['source'] != 'github-graphql' or snapshot.get('source') != 'github-graphql'
                or snapshot.get('as_of') != selection['date'] or digest(snapshot_path) != manifest['snapshot_sha256']
                or set(manifest['scenes']) != set(native)):
            raise ValueError('SVG manifest or source does not match the selected day')
        expected = {src for m in native for src, _ in ASSET_MAP[m]}
        if set(manifest['assets']) != expected:
            raise ValueError('Manifest asset allowlist mismatch')
        for scene in native:
            for name, _ in ASSET_MAP[scene]:
                if digest(artifacts/name) != manifest['assets'][name]:
                    raise ValueError(f'Asset digest mismatch: {name}')
                validate_svg(artifacts/name, scene, snapshot)
        if set(manifest.get('analysis', {})) != set(ANALYSIS_FILES):
            raise ValueError('Search comparison allowlist mismatch')
        cal = Calendar.from_snapshot(snapshot)
        report = comparison(cal)
        for name in ANALYSIS_FILES:
            path = artifacts/name
            if digest(path) != manifest['analysis'][name]:
                raise ValueError('Search comparison digest mismatch')
            if name.endswith('.json'):
                if json.loads(path.read_text(encoding='utf-8')) != report:
                    raise ValueError('Search comparison does not reproduce')
            else:
                validate_svg(path, 'search-comparison', snapshot)
                theme = 'dark' if '-dark.' in name else 'light'
                if path.read_text(encoding='utf-8') != render_comparison(cal, theme, report):
                    raise ValueError('Search visualization does not reproduce')
            copies.append((path, root/'assets'/'arcade'/name))
        copies += [(manifest_path, root/'assets'/'arcade'/manifest_path.name),
                   (snapshot_path, root/'assets'/'arcade'/snapshot_path.name)]
        gallery = root/'scripts'/'arcade_gallery.md'
        if not gallery.is_file():
            raise FileNotFoundError('Missing gallery template')
        # Only switch the gallery when all five replacements are available.
        if set(native) == set(NATIVE):
            copies.append((gallery, root/'ARCADE.md'))
    # No live file is changed until every source passes validation.
    for source, destination in copies+[(next_readme, root/'README.md'), (next_state, root/'.github'/'arcade-state.json')]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    if set(native) == set(NATIVE):
        for name in OLD_GIFS:
            (root/'assets'/'arcade'/name).unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--staging', type=Path, default=Path('staging'))
    args = p.parse_args()
    publish(args.root.resolve(), args.staging.resolve())

if __name__ == '__main__':
    main()
