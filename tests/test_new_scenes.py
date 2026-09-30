import json
import unittest
from pathlib import Path

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

    def test_domino_chain_runs_in_column_order_in_one_direction(self):
        cal = calendar()
        model = PLANNERS['domino'](cal, 3)
        self.assertIn(model['dir'], (1, -1))
        columns = [p[0] * model['dir'] for p in model['order']]
        self.assertEqual(columns, sorted(columns))
        self.assertCountEqual(model['order'], cal.active)

    def test_domino_pips_match_the_activity_level(self):
        from scripts.svg_arcade import PIPS
        self.assertEqual([len(PIPS[level]) for level in (1, 2, 3, 4)], [1, 2, 3, 4])

    def test_synth_runs_three_distinct_tempos_alternating_direction(self):
        model = PLANNERS['synth'](calendar(), 3)
        self.assertEqual(len({p['tempo'] for p in model['passes']}), 3)
        self.assertEqual([p['dir'] for p in model['passes']][::2], [model['passes'][0]['dir']]*2)

    def test_fireworks_pads_are_distinct_columns(self):
        pads = PLANNERS['fireworks'](calendar(), 3)['pads']
        self.assertEqual(len(pads), len(set(pads)))


if __name__ == '__main__':
    unittest.main()
