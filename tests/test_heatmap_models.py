"""Rules and vector-rendering regressions for the replacement SVG engine."""
import copy
import json
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.svg_models import Calendar, PLANNERS
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

    def test_arcade_autoplays_on_screen_and_prints_an_original_static_calendar(self):
        cal = calendar()
        ns = '{http://www.w3.org/2000/svg}'
        for name in PLANNERS:
            raw = render(cal, name, 8)
            doc = ET.fromstring(raw)
            still = next(n for n in doc.findall(ns+'g') if n.get('class') == 'still')
            self.assertEqual(len(list(still)), 53*7-len(cal.missing))
            self.assertIn('.motion{display:inline}', raw)
            self.assertNotIn('prefers-reduced-motion', raw)
            self.assertIn('@media print{.motion{display:none}.still{display:inline}}', raw)

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

    def test_bad_theme_or_scene_rejected(self):
        for scene, theme in [('gravity', 'dark'), ('minecraft', 'bogus')]:
            with self.assertRaises(ValueError):
                render(calendar(), scene, 1, theme)

if __name__ == '__main__':
    unittest.main()
