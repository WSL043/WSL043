"""Fresh-data, rotation, safe-publication and integration tests for SVG v3."""
import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from scripts import heatmap_data as data
from scripts import rotate_arcade as rotation
from scripts.publish_arcade import publish, ASSET_MAP, OLD_GIFS, digest
from scripts.svg_models import SCENES

ROOT = Path(__file__).resolve().parents[1]
DAY = '2026-09-12'


def payload(day=DAY):
    end = date.fromisoformat(day)
    begin = end-timedelta(days=364)
    weeks = {}
    levels = list(data.LEVELS)
    for i in range(365):
        dt = begin+timedelta(days=i)
        weekday = (dt.weekday()+1) % 7
        sunday = dt-timedelta(days=weekday)
        level = dt.toordinal() % 5 if dt >= end-timedelta(days=35) else 0
        weeks.setdefault(sunday, []).append({'date': dt.isoformat(), 'weekday': weekday, 'contributionLevel': levels[level]})
    return {'data': {'user': {'contributionsCollection': {'contributionCalendar': {
        'weeks': [{'contributionDays': values} for values in weeks.values()]}}}}}


class DataTests(unittest.TestCase):
    def test_normalize_preserves_all_dates_and_partial_edges(self):
        source = payload()
        snap = data.normalize(source, 'WSL043', DAY)
        self.assertEqual(snap['source'], 'github-graphql')
        self.assertEqual(sum(v is not None for col in snap['active_columns'].values() for v in col), 365)
        self.assertEqual(snap['range_start'], '2025-09-13')
        for x, week in enumerate(source['data']['user']['contributionsCollection']['contributionCalendar']['weeks']):
            for d in week['contributionDays']:
                self.assertEqual(snap['active_columns'][str(x)][d['weekday']], data.LEVELS[d['contributionLevel']])

    def test_leap_year_is_exactly_365_days(self):
        for day in ('2024-03-01', '2024-12-31', '2026-09-12'):
            snap = data.normalize(payload(day), 'WSL043', day)
            self.assertEqual((date.fromisoformat(day)-date.fromisoformat(snap['range_start'])).days, 364)

    def test_partial_graphql_errors_are_not_an_empty_calendar(self):
        source = payload()
        source['errors'] = [{'message': 'denied'}]
        with self.assertRaises(ValueError):
            data.normalize(source, 'WSL043', DAY)

    def test_unknown_level_duplicate_or_bad_weekday_rejected(self):
        for kind in ('level', 'duplicate', 'weekday'):
            source = payload()
            days = source['data']['user']['contributionsCollection']['contributionCalendar']['weeks'][1]['contributionDays']
            if kind == 'level':
                days[0]['contributionLevel'] = 'UNKNOWN'
            elif kind == 'weekday':
                days[0]['weekday'] = 9
            else:
                days.append(days[0].copy())
            with self.assertRaises(ValueError):
                data.normalize(source, 'WSL043', DAY)

    def test_missing_token_and_invalid_owner_fail_explicitly(self):
        for owner, token in [('WSL043', ''), ('bad/user', 'token')]:
            with self.assertRaises(ValueError):
                data.fetch_calendar(owner, DAY, token)

    def test_retries_bounded_and_never_return_old_data(self):
        with patch.object(data.urllib.request, 'urlopen', side_effect=urllib.error.URLError('offline')) as mock, patch.object(data.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                data.fetch_calendar('WSL043', DAY, 'not-a-real-token')
            self.assertEqual(mock.call_count, 3)

    def test_auth_failure_is_not_retried(self):
        error = urllib.error.HTTPError('test', 401, 'denied', {}, None)
        with patch.object(data.urllib.request, 'urlopen', side_effect=error) as mock:
            with self.assertRaises(RuntimeError):
                data.fetch_calendar('WSL043', DAY, 'not-a-real-token')
            self.assertEqual(mock.call_count, 1)

    def test_build_all_outputs_only_ten_svg_files(self):
        snap = data.normalize(payload(), 'WSL043', DAY)
        before = copy.deepcopy(snap)
        with tempfile.TemporaryDirectory() as temp:
            manifest = data.build(snap, {'selected': 'assembly', 'date': DAY, 'refresh_native': True}, Path(temp))
            self.assertEqual(len(manifest['assets']), 10)
            self.assertTrue(all(name.endswith('.svg') for name in manifest['assets']))
            self.assertEqual(snap, before)

    def test_offline_cli_forces_source_label_even_for_a_live_snapshot(self):
        snap = data.normalize(payload(), 'WSL043', DAY)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p/'snapshot.json').write_text(json.dumps(snap))
            (p/'selection.json').write_text(json.dumps({'selected': 'portal', 'date': DAY}))
            subprocess.run([sys.executable, '-m', 'scripts.heatmap_data', '--input', str(p/'snapshot.json'),
                '--selection', str(p/'selection.json'), '--output', str(p/'out')], cwd=ROOT, check=True, capture_output=True)
            self.assertEqual(json.loads((p/'out/heatmap-snapshot.json').read_text())['source'], 'offline-preview')


class RotationTests(unittest.TestCase):
    def test_migration_removes_retired_and_prioritizes_svg(self):
        selected, state = rotation.choose_next({'current': 'defense', 'remaining': ['pinball', 'laser', 'gravity', 'snake'], 'catalog_version': 2}, random.Random(2))
        self.assertIn(selected, rotation.NATIVE)
        self.assertEqual(set([selected]+state['remaining']), set(rotation.NATIVE+('snake',)))
        self.assertEqual(state['catalog_version'], 3)

    def test_three_hundred_complete_bags_no_repeats(self):
        state = {}
        previous = None
        for cycle in range(300):
            values = []
            for i in rotation.ARCADE_EXPERIENCES:
                selected, state = rotation.choose_next(state, random.Random(f'{cycle}:{i}'))
                self.assertNotEqual(selected, previous)
                values.append(selected)
                previous = selected
            self.assertCountEqual(values, rotation.ARCADE_EXPERIENCES)

    def test_same_day_retry_preserves_draw_and_bag(self):
        selected, state = rotation.select_daily({}, DAY, seed='first')
        self.assertEqual((selected, state), rotation.select_daily(state, DAY, seed='different'))

    def test_manual_selection_and_time_rewind(self):
        _, state = rotation.select_daily({}, DAY, 'portal')
        selected, new = rotation.select_daily(state, DAY, 'assembly')
        self.assertEqual(selected, 'assembly')
        self.assertNotIn('assembly', new['remaining'])
        with self.assertRaises(ValueError):
            rotation.select_daily(state, '2026-09-11')
        for retired in rotation.RETIRED:
            with self.assertRaises(ValueError):
                rotation.force_selection(state, retired)

    def test_readme_preserves_project_section_and_literal_backslashes(self):
        original = 'before\\1\n<!-- ARCADE:START -->old<!-- ARCADE:END -->\nafter\\1'
        updated = rotation.replace_arcade_block(original, 'new\\1')
        self.assertEqual(updated, 'before\\1\n<!-- ARCADE:START -->\nnew\\1\n<!-- ARCADE:END -->\nafter\\1')

    def test_bad_markers_and_dates_rejected(self):
        for text in ('no markers', '<!-- ARCADE:END --><!-- ARCADE:START -->', '<!-- ARCADE:START --><!-- ARCADE:START --><!-- ARCADE:END -->'):
            with self.assertRaises(ValueError):
                rotation.replace_arcade_block(text, 'new')
        for value in ('2026-9-12', '2026-02-30', 'x'):
            with self.assertRaises(ValueError):
                rotation.valid_day(value)

    def test_workflow_catalog_asset_map_and_gallery_agree(self):
        self.assertEqual(rotation.NATIVE, SCENES)
        self.assertEqual(set(ASSET_MAP), set(rotation.ARCADE_EXPERIENCES))
        workflow = (ROOT/'.github/workflows/daily-arcade.yml').read_text()
        gallery = (ROOT/'scripts/arcade_gallery.md').read_text()
        for name in rotation.ARCADE_EXPERIENCES:
            self.assertIn(f'          - {name}\n', workflow)
        for name in rotation.NATIVE:
            self.assertIn(f'heatmap-{name}-dark.svg', gallery)
            self.assertIn('.svg', rotation.render_arcade_block(name))
        self.assertIn("github.event_name != 'workflow_dispatch' || inputs.refresh_native", workflow)
        self.assertEqual(workflow.count('contents: write'), 1)
        self.assertIn('git add README.md ARCADE.md', workflow)

    def test_cli_defaults_to_refreshing_all_native_scenes(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p/'README.md').write_text('<!-- ARCADE:START --><!-- ARCADE:END -->')
            subprocess.run([sys.executable, 'scripts/rotate_arcade.py', '--state', str(p/'absent.json'), '--readme', str(p/'README.md'),
                '--date', DAY, '--output-dir', str(p/'out')], cwd=ROOT, check=True, capture_output=True)
            self.assertTrue(json.loads((p/'out/selection.json').read_text())['refresh_native'])


class PublicationTests(unittest.TestCase):
    def prepare(self, all_native=False, selected='assembly'):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root/'README.md').write_text('before\n<!-- ARCADE:START -->old<!-- ARCADE:END -->\nafter')
        (root/'ARCADE.md').write_text('old gallery')
        (root/'scripts').mkdir()
        shutil.copyfile(ROOT/'scripts/arcade_gallery.md', root/'scripts/arcade_gallery.md')
        metadata = root/'staging/rotation-metadata'
        metadata.mkdir(parents=True)
        selection = {'selected': selected, 'mode': 'selected', 'date': DAY, 'refresh_native': all_native,
                     'readme_sha256': digest(root/'README.md')}
        (metadata/'selection.json').write_text(json.dumps(selection))
        (metadata/'arcade-state.next.json').write_text(json.dumps({'current': selected, 'updated_on': DAY}))
        (metadata/'README.next.md').write_text('new readme')
        artifacts = root/'staging/generators'
        data.build(data.normalize(payload(), 'WSL043', DAY), selection, artifacts)
        return root, artifacts, metadata

    def test_valid_single_publish_copies_both_themes(self):
        root, _, _ = self.prepare()
        publish(root, root/'staging')
        self.assertEqual((root/'README.md').read_text(), 'new readme')
        for theme in ('dark', 'light'):
            self.assertTrue((root/f'assets/arcade/heatmap-assembly-{theme}.svg').is_file())
        self.assertEqual((root/'ARCADE.md').read_text(), 'old gallery')

    def test_full_refresh_swaps_gallery_and_removes_only_old_native_gifs(self):
        root, _, _ = self.prepare(True)
        assets = root/'assets/arcade'
        assets.mkdir(parents=True)
        for name in OLD_GIFS+('space-shooter.gif',):
            (assets/name).write_text('old')
        publish(root, root/'staging')
        self.assertEqual(len(list(assets.glob('*.svg'))), 10)
        self.assertEqual((assets/'space-shooter.gif').read_text(), 'old')
        self.assertFalse(any((assets/name).exists() for name in OLD_GIFS))
        self.assertNotEqual((root/'ARCADE.md').read_text(), 'old gallery')

    def test_missing_asset_changes_nothing(self):
        root, artifacts, _ = self.prepare(True)
        (artifacts/'heatmap-bomber-light.svg').unlink()
        before = (root/'README.md').read_bytes()
        with self.assertRaises(FileNotFoundError):
            publish(root, root/'staging')
        self.assertEqual((root/'README.md').read_bytes(), before)
        self.assertEqual((root/'ARCADE.md').read_text(), 'old gallery')
        self.assertFalse((root/'assets').exists())

    def test_tampered_asset_fails_before_any_copy(self):
        root, artifacts, _ = self.prepare()
        with (artifacts/'heatmap-assembly-dark.svg').open('a') as f:
            f.write('tampered')
        with self.assertRaises(ValueError):
            publish(root, root/'staging')
        self.assertFalse((root/'assets').exists())

    def test_script_image_and_external_resource_rejected_even_with_updated_digest(self):
        for addition in ('<script>alert(1)</script>', '<image href="x.gif"/>', '<foreignObject/>', '<g onclick="x()"/>', '<style>@import "x";</style>'):
            root, artifacts, _ = self.prepare()
            asset = artifacts/'heatmap-assembly-dark.svg'
            asset.write_text(asset.read_text().replace('</svg>', addition+'</svg>'))
            manifest = json.loads((artifacts/'heatmap-manifest.json').read_text())
            manifest['assets'][asset.name] = digest(asset)
            (artifacts/'heatmap-manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                publish(root, root/'staging')
            self.assertFalse((root/'assets').exists())

    def test_wrong_snapshot_or_scene_is_rejected(self):
        root, artifacts, _ = self.prepare()
        asset = artifacts/'heatmap-assembly-dark.svg'
        asset.write_text(asset.read_text().replace('data-scene="assembly"', 'data-scene="portal"'))
        manifest = json.loads((artifacts/'heatmap-manifest.json').read_text())
        manifest['assets'][asset.name] = digest(asset)
        (artifacts/'heatmap-manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            publish(root, root/'staging')

    def test_stale_or_offline_snapshot_cannot_publish(self):
        for key, value in [('as_of', '2026-09-11'), ('source', 'offline-preview')]:
            root, artifacts, _ = self.prepare()
            source = json.loads((artifacts/'heatmap-snapshot.json').read_text())
            source[key] = value
            (artifacts/'heatmap-snapshot.json').write_text(json.dumps(source))
            with self.assertRaises(ValueError):
                publish(root, root/'staging')

    def test_concurrent_readme_edits_are_not_overwritten(self):
        root, _, _ = self.prepare()
        (root/'README.md').write_text('a newer user edit')
        with self.assertRaises(ValueError):
            publish(root, root/'staging')
        self.assertEqual((root/'README.md').read_text(), 'a newer user edit')

    def test_selection_state_mismatch_and_unknown_mode(self):
        for field, value in [('mode', 'surprise'), ('selected', 'gravity'), ('date', '2026-09-13')]:
            root, _, metadata = self.prepare()
            selection = json.loads((metadata/'selection.json').read_text())
            selection[field] = value
            (metadata/'selection.json').write_text(json.dumps(selection))
            with self.assertRaises(ValueError):
                publish(root, root/'staging')

if __name__ == '__main__':
    unittest.main()
