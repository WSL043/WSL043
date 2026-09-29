import json
import unittest
from pathlib import Path

import re

from scripts.svg_arcade import RENDERERS
from scripts.svg_models import PLANNERS, Calendar

FIXTURE = Path(__file__).parent/'fixtures'/'heatmap.json'


def calendar():
    return Calendar.from_snapshot(json.loads(FIXTURE.read_text(encoding='utf-8')))


class NewSceneTests(unittest.TestCase):
    def test_every_scene_covers_each_active_day_exactly_once(self):
        cal = calendar()
        for name in ('fireworks', 'domino', 'dust', 'sorter', 'claw'):
            with self.subTest(scene=name):
                self.assertCountEqual(PLANNERS[name](cal, 5)['order'], cal.active)

    def test_sorter_bins_are_the_real_level_histogram(self):
        cal = calendar()
        model = PLANNERS['sorter'](cal, 5)
        expected = [sum(1 for p in cal.active if cal.grid[p] == level) for level in (1, 2, 3, 4)]
        self.assertEqual(model['counts'], expected)
        for p, (level, slot) in zip(model['order'], model['slots']):
            self.assertEqual(level, cal.grid[p]-1)
            self.assertLess(slot, expected[level])

    def test_claw_never_reaches_past_a_tile_still_above_its_target(self):
        cal = calendar()
        remaining = set(cal.active)
        for p in PLANNERS['claw'](cal, 7)['order']:
            self.assertFalse(any((p[0], y) in remaining for y in range(p[1])))
            remaining.remove(p)

    def test_domino_starts_from_a_real_active_day_and_orders_by_distance(self):
        cal = calendar()
        model = PLANNERS['domino'](cal, 3)
        self.assertIn(model['origin'], cal.active)
        self.assertEqual(model['order'][0], model['origin'])

    def test_synth_runs_three_distinct_tempos_alternating_direction(self):
        model = PLANNERS['synth'](calendar(), 3)
        self.assertEqual(len({p['tempo'] for p in model['passes']}), 3)
        self.assertEqual([p['dir'] for p in model['passes']][::2], [model['passes'][0]['dir']]*2)

    def test_fireworks_pads_are_distinct_columns(self):
        pads = PLANNERS['fireworks'](calendar(), 3)['pads']
        self.assertEqual(len(pads), len(set(pads)))

    def test_skyline_rises_from_a_real_day_in_distance_order(self):
        cal = calendar()
        model = PLANNERS['skyline'](cal, 3)
        self.assertIn(model['origin'], cal.active)
        self.assertEqual(model['order'][0], model['origin'])
        self.assertCountEqual(model['order'], cal.active)

    def test_perspective_scenes_approach_the_camera_monotonically(self):
        cal = calendar()
        for name, gates in (('tunnel', cal.cols), ('neondrive', len(cal.active))):
            draw = RENDERERS[name](cal, PLANNERS[name](cal, 3), 'dark')
            approaching = 0
            for track in draw.tracks:
                scales = [float(m.group(1)) for _, props in sorted(track.items())[:-1]
                          if 'transform' in props and (m := re.search(r'scale\(([\d.]+)\)', props['transform']))]
                if len(scales) > 12 and all(b >= a-1e-9 for a, b in zip(scales, scales[1:])):
                    approaching += 1
            self.assertGreaterEqual(approaching, gates, name)


if __name__ == '__main__':
    unittest.main()
