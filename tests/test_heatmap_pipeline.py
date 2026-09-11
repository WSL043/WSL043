import copy
import hashlib
import json
import random
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from scripts import heatmap_arcade as a, heatmap_extra as e
from scripts import heatmap_data as data, rotate_arcade as r, publish_arcade as pub

FIXTURE = Path(__file__).parent/'fixtures'/'heatmap.json'


def calendar_payload(day='2026-09-11'):
    end = date.fromisoformat(day); begin = end-timedelta(days=364)
    weeks = []
    for i in range(365):
        dt = begin+timedelta(days=i); y = (dt.weekday()+1) % 7
        if not weeks or y == 0:
            weeks.append({'contributionDays': []})
        weeks[-1]['contributionDays'].append({'date': dt.isoformat(), 'weekday': y,
                                            'contributionLevel': list(data.LEVELS)[i % 5]})
    return {'data': {'user': {'contributionsCollection': {'contributionCalendar': {'weeks': weeks}}}}}


class DataTests(unittest.TestCase):
    def test_fresh_calendar_keeps_dates_levels_and_missing_edges(self):
        obj = data.normalize(calendar_payload(), 'WSL043', '2026-09-11')
        cells = [x for column in obj['active_columns'].values() for x in column]
        self.assertEqual(sum(v is not None for v in cells), 365)
        self.assertEqual(obj['range_start'], '2025-09-12')
        self.assertEqual(obj['source'], 'github-graphql')
        self.assertEqual(cells.count(4), 73)

    def test_leap_year_range_has_exactly_365_days(self):
        obj = data.normalize(calendar_payload('2024-03-01'), 'WSL043', '2024-03-01')
        self.assertEqual(obj['range_start'], '2023-03-03')

    def test_graphql_errors_never_become_fake_empty_calendar(self):
        obj = calendar_payload(); obj['errors'] = [{'message': 'blocked'}]
        with self.assertRaises(ValueError): data.normalize(obj, 'WSL043', '2026-09-11')

    def test_unknown_level_wrong_weekday_and_duplicate_are_rejected(self):
        for mutation in ('level', 'weekday', 'duplicate', 'gap'):
            obj = calendar_payload()
            days = obj['data']['user']['contributionsCollection']['contributionCalendar']['weeks'][1]['contributionDays']
            if mutation == 'level': days[0]['contributionLevel'] = 'UNKNOWN'
            elif mutation == 'weekday': days[0]['weekday'] = 6
            elif mutation == 'duplicate': days.append(days[0].copy())
            else: days.pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                data.normalize(obj, 'WSL043', '2026-09-11')

    def test_absent_token_is_an_explicit_failure(self):
        with self.assertRaises(ValueError): data.fetch_calendar('WSL043', '2026-09-11', '')

    def test_retry_is_bounded_and_does_not_return_stale_data(self):
        with patch.object(data.urllib.request, 'urlopen', side_effect=TimeoutError), patch.object(data.time, 'sleep') as sleep:
            with self.assertRaises(RuntimeError): data.fetch_calendar('WSL043', '2026-09-11', 'test-only')
            self.assertEqual(sleep.call_count, 2)

    def test_both_partial_weeks_remain_null(self):
        obj = data.normalize(calendar_payload(), 'WSL043', '2026-09-11')
        self.assertEqual(obj['active_columns']['0'][:5], [None]*5)
        self.assertIsNone(obj['active_columns'][str(obj['columns']-1)][6])


class ExtraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e.register(); _, cls.grid, cls.missing = a.load_snapshot(FIXTURE)
        cls.models = {s: a.PLANNERS[s](cls.grid, 43) for s in ('pinball', 'laser', 'gravity')}

    def test_all_extra_models_are_deterministic_and_do_not_mutate(self):
        before = self.grid.copy()
        for s, model in self.models.items():
            self.assertEqual(model, a.PLANNERS[s](self.grid, 43))
        self.assertEqual(self.grid, before)

    def test_pinball_damage_is_conserved_and_real(self):
        model = self.models['pinball']; expected = self.grid.copy()
        for hit in model['events']:
            self.assertGreater(expected[hit['p']], 0); expected[hit['p']] -= 1
        self.assertEqual(expected, model['final'])
        self.assertTrue(model['events'])

    def test_pinball_balls_stay_inside_the_arena(self):
        model = self.models['pinball']; lo, hi = model['bounds']
        for frame in model['states']:
            for x, y in frame['balls']:
                self.assertTrue(lo-.301 <= x <= hi+.301)
                self.assertTrue(-.851 <= y <= 6.851)

    def test_laser_reflections_are_axis_aligned_and_reversible(self):
        for direction in a.DIRS:
            for slash in (True, False):
                reflected = e.reflect(direction, slash)
                self.assertIn(reflected, a.DIRS)
                self.assertEqual(e.reflect(reflected, slash), direction)
                self.assertNotEqual(reflected, direction)

    def test_laser_uses_real_cells_and_conserves_damage(self):
        model = self.models['laser']; expected = self.grid.copy()
        for hit in model['events']:
            self.assertGreater(expected[hit['p']], 0); expected[hit['p']] -= 1
        self.assertEqual(expected, model['final'])
        for pulse in model['pulses']:
            self.assertTrue(all(self.grid[p] > 0 for p in pulse['hits']))
            for p, q in zip(pulse['vertices'], pulse['vertices'][1:]):
                self.assertTrue(p[0] == q[0] or p[1] == q[1])

    def test_sand_conserves_every_emitted_particle_on_every_frame(self):
        model = self.models['gravity']
        for frame in model['states']:
            expected = sum(x['grains'] for x in model['events'][:frame['released']])
            self.assertEqual(len(frame['sand']), expected)
            for (x, y) in frame['sand']:
                self.assertTrue(-4 <= x < a.COLS*4+4 and 0 <= y < 30)
                self.assertEqual(frame['grid'].get((x//4, y//4), 0), 0)
        self.assertFalse(any(model['final'].values()))

    def test_empty_input_does_not_invent_game_tiles(self):
        empty = {p: 0 for p in self.grid}
        for s in self.models:
            model = a.PLANNERS[s](empty, 43)
            self.assertEqual(model['events'], [])
            self.assertFalse(any(model['final'].values()))

    def test_all_six_draw_in_both_themes_with_changes(self):
        models = {**self.models, **{s: a.PLANNERS[s](self.grid, 43) for s in ('bomber', 'miners', 'defense')}}
        for theme in ('dark', 'light'):
            a.configure_theme(theme)
            for s, model in models.items():
                first = a.DRAWERS[s](model, self.grid, self.missing, 3.1, 48)
                later = a.DRAWERS[s](model, self.grid, self.missing, 9.2, 48)
                self.assertEqual(first.size, (1040, 420))
                self.assertNotEqual(first.tobytes(), later.tobytes())
                self.assertEqual(first.getpixel((0, 400)), Image.new('RGB', (1,1), a.BG).getpixel((0,0)))
        a.configure_theme('dark')

    def test_full_heatmap_does_not_break_or_fabricate_new_tiles(self):
        full = {p: 4 for p in self.grid}
        for s in ('pinball', 'laser', 'gravity'):
            model = a.PLANNERS[s](full, 3)
            self.assertTrue(all(0 <= v <= 4 for v in model['final'].values()))

    def test_snapshot_accepts_54_columns_without_filling_nulls(self):
        obj = json.loads(FIXTURE.read_text()); obj['columns'] = 54; obj['active_columns']['53'] = [None]*7
        try:
            with tempfile.TemporaryDirectory() as td:
                path = Path(td)/'calendar.json'; path.write_text(json.dumps(obj))
                _, grid, missing = a.load_snapshot(path)
                self.assertEqual(len(grid), 378); self.assertIn((53,0), missing)
        finally:
            a.load_snapshot(FIXTURE)


class RotationTests(unittest.TestCase):
    def test_three_hundred_complete_bags_have_no_adjacent_repeat(self):
        state = {}; previous = None
        for cycle in range(300):
            seen = []
            for _ in r.ARCADE_EXPERIENCES:
                selected, state = r.choose_next(state, random.Random(cycle+len(seen)))
                self.assertNotEqual(previous, selected); previous = selected; seen.append(selected)
            self.assertEqual(set(seen), set(r.ARCADE_EXPERIENCES))

    def test_legacy_bag_gets_all_six_new_cartridges_first(self):
        state = {'current': 'space-shooter', 'remaining': ['3d-city', 'breakout'], 'cycle': 3}
        seen = []
        for _ in r.NATIVE:
            s, state = r.choose_next(state, random.Random(1)); seen.append(s)
        self.assertEqual(set(seen), set(r.NATIVE))
        self.assertEqual(state['remaining'], ['3d-city', 'breakout'])

    def test_same_day_random_retry_keeps_selection_and_bag(self):
        s, state = r.select_daily({}, '2026-09-11', seed='one')
        s2, state2 = r.select_daily(state, '2026-09-11', seed='two')
        self.assertEqual((s, state), (s2, state2))

    def test_manual_change_removes_duplicate_and_rewind_is_rejected(self):
        _, state = r.select_daily({}, '2026-09-11')
        _, state = r.select_daily(state, '2026-09-11', 'miners')
        self.assertNotIn('miners', state['remaining'])
        with self.assertRaises(ValueError): r.select_daily(state, '2026-09-10')

    def test_readme_preserves_outside_content_and_backslashes(self):
        original = 'before\n'+r.START_MARKER+'\nold\n'+r.END_MARKER+'\nafter\n'
        updated = r.replace_arcade_block(original, r'new\path')
        self.assertEqual(updated, 'before\n'+r.START_MARKER+'\nnew\\path\n'+r.END_MARKER+'\nafter\n')
        for bad in ('', r.START_MARKER+r.START_MARKER+r.END_MARKER, r.END_MARKER+r.START_MARKER):
            with self.assertRaises(ValueError): r.replace_arcade_block(bad, 'x')

    def test_catalog_assets_and_workflow_agree(self):
        self.assertEqual(len(r.ARCADE_EXPERIENCES), 11)
        self.assertEqual(set(pub.ASSET_MAP), set(r.ARCADE_EXPERIENCES))
        workflow = (Path(__file__).parents[1]/'.github/workflows/daily-arcade.yml').read_text()
        for name in r.ARCADE_EXPERIENCES:
            self.assertIn(f'          - {name}\n', workflow)
            self.assertIn('Today', r.render_arcade_block(name, '2026-09-11'))


class PublicationTests(unittest.TestCase):
    def setup_stage(self, root, all_native=False):
        (root/'README.md').write_text('live\n')
        staging = root/'staging'; md = staging/'rotation-metadata'; gen = staging/'generators'
        md.mkdir(parents=True); gen.mkdir(parents=True)
        selection = {'selected': 'bomber', 'mode': 'selected', 'date': '2026-09-11',
                     'refresh_native': all_native, 'readme_sha256': pub.digest(root/'README.md')}
        (md/'selection.json').write_text(json.dumps(selection))
        (md/'README.next.md').write_text('next\n')
        (md/'arcade-state.next.json').write_text(json.dumps({'current':'bomber','updated_on':'2026-09-11'}))
        (gen/'heatmap-snapshot.json').write_text(json.dumps({'source':'github-graphql','as_of':'2026-09-11'}))
        scenes = list(r.NATIVE) if all_native else ['bomber']
        hashes = {}
        for s in scenes:
            for name, _ in pub.ASSET_MAP[s]:
                path = gen/name
                Image.new('RGB',(1040,420),'black').save(path,save_all=True,append_images=[Image.new('RGB',(1040,420),'white')],duration=50,loop=0)
                hashes[name] = pub.digest(path)
        manifest = {'date':'2026-09-11','source':'github-graphql','scenes':scenes,
                    'snapshot_sha256':pub.digest(gen/'heatmap-snapshot.json'),'assets':hashes}
        (gen/'heatmap-manifest.json').write_text(json.dumps(manifest))
        return staging, gen

    def test_valid_native_publish_copies_both_themes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); st, gen = self.setup_stage(root); pub.publish(root, st)
            self.assertEqual((root/'README.md').read_text(), 'next\n')
            self.assertTrue((root/'assets/arcade/heatmap-bomber-light.gif').is_file())

    def test_refresh_all_native_publishes_all_twelve_without_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); st, gen = self.setup_stage(root, True); pub.publish(root, st)
            self.assertEqual(len(list((root/'assets/arcade').glob('*.gif'))), 12)

    def test_missing_or_tampered_asset_keeps_readme_and_assets_untouched(self):
        for damage in ('delete','tamper'):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td); st, gen = self.setup_stage(root)
                p = gen/'heatmap-bomber-dark.gif'
                if damage == 'delete': p.unlink()
                else: p.write_bytes(b'not a gif')
                with self.assertRaises((ValueError,FileNotFoundError)): pub.publish(root, st)
                self.assertEqual((root/'README.md').read_text(), 'live\n')
                self.assertFalse((root/'assets').exists())

    def test_changed_readme_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); st, gen = self.setup_stage(root); (root/'README.md').write_text('human edit\n')
            with self.assertRaises(ValueError): pub.publish(root, st)
            self.assertEqual((root/'README.md').read_text(), 'human edit\n')

    def test_stale_or_local_snapshot_cannot_be_published_as_live(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); st, gen = self.setup_stage(root)
            p = gen/'heatmap-snapshot.json'; p.write_text(FIXTURE.read_text())
            with self.assertRaises(ValueError): pub.publish(root, st)
            self.assertEqual((root/'README.md').read_text(), 'live\n')

    def test_state_mismatch_and_unknown_mode_are_rejected(self):
        for key, value in [('selected','miners'),('mode','surprise')]:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td); st, gen = self.setup_stage(root)
                p = st/'rotation-metadata/selection.json'; obj = json.loads(p.read_text()); obj[key] = value; p.write_text(json.dumps(obj))
                with self.assertRaises((ValueError,FileNotFoundError)): pub.publish(root, st)
                self.assertEqual((root/'README.md').read_text(), 'live\n')

if __name__ == '__main__': unittest.main()
