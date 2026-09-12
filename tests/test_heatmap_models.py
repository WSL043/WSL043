"""Rules and vector-rendering regressions for the replacement SVG engine."""
import copy
import json
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.svg_models import Calendar, PLANNERS, DIRS, blast, link_path
from scripts.svg_arcade import RENDERERS, render
from scripts.publish_arcade import validate_svg

FIXTURE = Path(__file__).parent/'fixtures'/'heatmap.json'


def calendar():
    return Calendar.from_snapshot(json.loads(FIXTURE.read_text(encoding='utf-8')))


class ModelTests(unittest.TestCase):
    def test_levels_null_edges_and_no_invented_days(self):
        cal = calendar()
        self.assertTrue(all(cal.grid[x, y] == 0 for x in range(44) for y in range(7)))
        self.assertEqual(cal.missing, {(52, 5), (52, 6)})
        self.assertEqual(cal.grid[47, 5], 4)

    def test_bad_level_rejected(self):
        for value in (True, -1, 5, '3'):
            data = json.loads(FIXTURE.read_text(encoding='utf-8'))
            data['active_columns']['44'][0] = value
            with self.assertRaises(ValueError):
                Calendar.from_snapshot(data)

    def test_52_to_54_columns(self):
        for cols in (52, 53, 54):
            cal = Calendar.from_snapshot({'columns': cols, 'rows': 7, 'active_columns': {'0': [None, 0, 1, 2, 3, 4, 0]}})
            self.assertEqual(len(cal.grid), cols*7)
            self.assertIn((0, 0), cal.missing)

    def test_all_planners_deterministic_and_nonmutating(self):
        cal = calendar()
        before = copy.deepcopy(cal)
        for name, fn in PLANNERS.items():
            with self.subTest(scene=name):
                self.assertEqual(fn(cal, 3), fn(cal, 3))
                self.assertEqual(cal, before)

    def test_new_seed_changes_plans(self):
        cal = calendar()
        for name, fn in PLANNERS.items():
            with self.subTest(scene=name):
                self.assertNotEqual(fn(cal, 3), fn(cal, 9))

    def test_bomber_full_clear_paths_escape_and_damage(self):
        for seed in range(5):
            cal = calendar()
            grid = cal.grid.copy()
            model = PLANNERS['bomber'](cal, seed)
            pos = model['start']
            for event in model['events']:
                self.assertEqual(event['route'][0], pos)
                for route in (event['route'], event['retreat']):
                    self.assertTrue(all(not grid.get(p, 0) for p in route))
                    self.assertTrue(all(abs(a[0]-b[0])+abs(a[1]-b[1]) == 1 for a, b in zip(route, route[1:])))
                self.assertEqual(event['route'][-1], event['retreat'][0])
                area, hits = blast(event['route'][-1], grid, cal.cols)
                self.assertEqual(area, event['area'])
                self.assertEqual(hits, event['hits'])
                self.assertNotIn(event['retreat'][-1], area)
                self.assertEqual([grid[p] for p in hits], event['hp'])
                for p in hits:
                    self.assertGreater(grid[p], 0)
                    grid[p] -= 1
                pos = event['retreat'][-1]
            self.assertFalse(any(grid.values()))
            self.assertEqual(grid, model['final'])
            self.assertGreater(len(model['events']), 9)

    def test_blast_stops_at_the_first_wall(self):
        area, hits = blast((2, 2), {(3, 2): 1, (4, 2): 4}, 53)
        self.assertIn((3, 2), hits)
        self.assertNotIn((4, 2), area)

    def test_miners_accessible_parallel_waves_and_complete_clear(self):
        cal = calendar()
        model = PLANNERS['miners'](cal, 7)
        grid, positions, removed = cal.grid.copy(), model['starts'][:], []
        for wave in model['waves']:
            self.assertEqual(len(wave), len({j['target'] for j in wave}))
            for job in wave:
                self.assertEqual(job['route'][0], positions[job['bot']])
                self.assertTrue(all(not grid.get(p, 0) for p in job['route']))
                self.assertTrue(all(abs(a[0]-b[0])+abs(a[1]-b[1]) == 1 for a, b in zip(job['route'], job['route'][1:])))
                p, q = job['route'][-1], job['target']
                self.assertEqual(abs(p[0]-q[0])+abs(p[1]-q[1]), 1)
                self.assertEqual(grid[q], job['level'])
                positions[job['bot']] = p
            for job in wave:
                grid[job['target']] = 0
                removed.append(job['target'])
        self.assertCountEqual(removed, cal.active)
        self.assertFalse(any(grid.values()))

    def test_link_pair_routes_have_equal_levels_no_walls_and_two_turns(self):
        for seed in range(8):
            cal = calendar()
            grid = cal.grid.copy()
            model = PLANNERS['link-match'](cal, seed)
            for pair in model['pairs']:
                a, b, route = pair['a'], pair['b'], pair['route']
                self.assertEqual(grid[a], grid[b])
                self.assertEqual((route[0], route[-1]), (a, b))
                self.assertTrue(all(not grid.get(p, 0) for p in route[1:-1]))
                dirs = [(b[0]-a[0], b[1]-a[1]) for a, b in zip(route, route[1:])]
                self.assertTrue(all(d in DIRS for d in dirs))
                self.assertLessEqual(sum(a != b for a, b in zip(dirs, dirs[1:])), 2)
                grid[a] = grid[b] = 0
            self.assertEqual(grid, model['final'])
            left = [p for p, level in grid.items() if level]
            self.assertTrue(all(link_path(a, b, grid, cal.cols) is None for i, a in enumerate(left) for b in left[i+1:]))

    def test_link_odd_counts_not_faked(self):
        cal = Calendar(53, {(3, 3): 1, (4, 3): 1, (5, 3): 1}, set(), [], 'test', '2026-09-12')
        model = PLANNERS['link-match'](cal, 1)
        self.assertEqual(len(model['pairs']), 1)
        self.assertEqual(sum(v > 0 for v in model['final'].values()), 1)

    def test_assembly_exact_cover_small_connected_pieces(self):
        cal = calendar()
        for seed in range(20):
            pieces = PLANNERS['assembly'](cal, seed)['pieces']
            self.assertCountEqual([p for piece in pieces for p in piece], cal.active)
            for piece in pieces:
                self.assertTrue(1 <= len(piece) <= 4)
                reached = {piece[0]}
                for _ in range(4):
                    reached |= {q for p in reached for q in piece if abs(p[0]-q[0])+abs(p[1]-q[1]) == 1}
                self.assertEqual(reached, set(piece))

    def test_portal_is_a_permutation_with_original_colours(self):
        cal = calendar()
        for seed in range(20):
            model = PLANNERS['portal'](cal, seed)
            self.assertCountEqual(model['order'], cal.active)
            self.assertEqual(model['levels'], [cal.grid[p] for p in model['order']])

    def test_empty_calendar_has_no_invented_game_objects(self):
        cal = Calendar(53, {(x, y): 0 for x in range(53) for y in range(7)}, set(), [], 'test', '2026-09-12')
        for name in PLANNERS:
            raw = render(cal, name, 4)
            self.assertNotIn('data-day=', raw)
            self.assertNotIn('@keyframes', raw)

    def test_full_54_week_calendar_finishes_all_models_with_bounded_files(self):
        cal = Calendar(54, {(x, y): 4 for x in range(54) for y in range(7)}, set(), [], 'test', '2026-09-12')
        for name, fn in PLANNERS.items():
            with self.subTest(scene=name):
                model = fn(cal, 4)
                if name in ('bomber', 'miners'):
                    self.assertFalse(any(model['final'].values()))
                raw = render(cal, name, 4, model=model)
                self.assertLess(len(raw.encode()), 3_000_000)
                self.assertIn('viewBox="0 0 912 216"', raw)


class RenderingTests(unittest.TestCase):
    def test_native_output_is_vector_only_valid_and_full_width(self):
        cal = calendar()
        snapshot = json.loads(FIXTURE.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            for name in PLANNERS:
                for theme in ('dark', 'light'):
                    raw = render(cal, name, 12, theme)
                    path = Path(directory)/'test.svg'
                    path.write_text(raw, encoding='utf-8')
                    validate_svg(path, name, snapshot)
                    self.assertIn('viewBox="0 0 896 216"', raw)
                    for forbidden in ('<image', '<script', '<foreignObject', 'base64', '.gif', '@import'):
                        self.assertNotIn(forbidden, raw)

    def test_visible_tiles_keep_exact_calendar_identity(self):
        cal = calendar()
        ns = '{http://www.w3.org/2000/svg}'
        for name in PLANNERS:
            doc = ET.fromstring(render(cal, name, 2))
            days = [tuple(map(int, node.attrib['data-day'].split(','))) for node in doc.iter(ns+'rect') if 'data-day' in node.attrib]
            self.assertCountEqual(days, cal.active)

    def test_reduced_motion_is_an_original_static_calendar(self):
        cal = calendar()
        ns = '{http://www.w3.org/2000/svg}'
        for name in PLANNERS:
            raw = render(cal, name, 8)
            doc = ET.fromstring(raw)
            still = next(n for n in doc.findall(ns+'g') if n.get('class') == 'still')
            self.assertEqual(len(list(still)), 53*7-len(cal.missing))
            self.assertIn('@media(prefers-reduced-motion:reduce){.motion{display:none}.still{display:inline}}', raw)

    def test_tracks_return_to_initial_state_and_effects_wait_for_their_cue(self):
        cal = calendar()
        for name, renderer in RENDERERS.items():
            draw = renderer(cal, PLANNERS[name](cal, 8), 'dark')
            self.assertLessEqual(draw.duration, 180)
            for values in draw.tracks:
                self.assertEqual(values[0.0], values[draw.duration])
                self.assertTrue(all(0 <= t <= draw.duration for t in values))
                first = sorted(values)[1]
                self.assertEqual(values[first], values[0.0])

    def test_file_reproducibility_and_theme_difference(self):
        cal = calendar()
        for name in PLANNERS:
            self.assertEqual(render(cal, name, 4), render(cal, name, 4))
            self.assertNotEqual(render(cal, name, 4, 'dark'), render(cal, name, 4, 'light'))

    def test_tiles_do_not_drift_or_shrink_before_they_are_removed(self):
        cal = calendar()
        for name in ('bomber', 'miners', 'link-match'):
            draw = RENDERERS[name](cal, PLANNERS[name](cal, 8), 'dark')
            for track in draw.tracks[:len(cal.active)]:
                normal = track[0.0]['transform']
                gone = min((t for t, props in track.items() if props.get('opacity') == '0'), default=draw.duration)
                for t, props in track.items():
                    if t <= gone and 'fill' in props:
                        self.assertEqual(props.get('transform'), normal)

    def test_bad_theme_or_scene_rejected(self):
        for scene, theme in [('gravity', 'dark'), ('portal', 'bogus')]:
            with self.assertRaises(ValueError):
                render(calendar(), scene, 1, theme)

if __name__ == '__main__':
    unittest.main()
