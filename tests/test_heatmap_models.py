import copy
import json
import tempfile
import unittest
from pathlib import Path
from scripts import heatmap_arcade as a

SOURCE=Path(__file__).parent / 'fixtures' / 'heatmap.json'

class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta,cls.g,cls.m=a.load_snapshot(SOURCE)
        cls.b=a.plan_bomber(cls.g,20260911)
        cls.n=a.plan_miners(cls.g,20260911)
        cls.d=a.plan_defense(cls.g,20260911)

    def test_source_shape_and_intensities(self):
        self.assertEqual(len(self.g),53*7)
        self.assertEqual(sum(v>0 for v in self.g.values()),44)
        self.assertEqual(self.m,{(52,5),(52,6)})
        self.assertEqual(self.meta['source_blob_sha'],'fb36981cd047ce0cf6ef868fc21347d8d9268d3a')

    def test_no_invented_days_in_early_columns(self):
        self.assertTrue(all(self.g[x,y]==0 for x in range(44) for y in range(7)))

    def test_planners_do_not_mutate_snapshot(self):
        before=copy.deepcopy(self.g)
        for planner in a.PLANNERS.values():planner(self.g,42)
        self.assertEqual(self.g,before)

    def test_bomber_can_reach_every_bomb_and_escape(self):
        for e in self.b['events']:
            for path in [e['route'],e['retreat']]:
                self.assertTrue(all(e['grid_before'].get(p,0)==0 for p in path))
                for p,q in zip(path,path[1:]):self.assertEqual(abs(p[0]-q[0])+abs(p[1]-q[1]),1)
            self.assertNotIn(e['retreat'][-1],e['cells'])
            self.assertLess(e['escape_start']+.075*(len(e['retreat'])-1),e['explosion'])

    def test_blast_stops_at_first_wall(self):
        cells,hits=a.blast_at((3,3),{(4,3):4,(5,3):1})
        self.assertIn((4,3),hits);self.assertNotIn((5,3),cells)

    def test_bomber_damage_is_one_intensity_unit_per_hit(self):
        expected=self.g.copy()
        for e in self.b['events']:
            for p in e['hits']:expected[p]-=1
        self.assertEqual(expected,self.b['final'])
        self.assertGreaterEqual(min(expected.values()),0)

    def test_mining_paths_do_not_walk_through_ore(self):
        for grid,path,target in self.n['audit']:
            self.assertTrue(all(grid.get(p,0)==0 for p in path))
            for p,q in zip(path,path[1:]):self.assertEqual(abs(p[0]-q[0])+abs(p[1]-q[1]),1)
            self.assertEqual(abs(path[-1][0]-target[0])+abs(path[-1][1]-target[1]),1)

    def test_mining_conserves_cells(self):
        mined=[e['p'] for e in self.n['events']]
        self.assertEqual(len(set(mined)),len(mined))
        self.assertTrue(all(self.g[p]>0 for p in mined))
        self.assertEqual(len(mined)+sum(v>0 for v in self.n['final'].values()),44)

    def test_towers_are_real_active_days(self):
        for tower in self.d['towers']:
            self.assertEqual(tower['level'],self.g[tower['p']])
            self.assertGreaterEqual(tower['level'],2)

    def test_enemy_path_uses_only_empty_cells_and_outer_aisle(self):
        self.assertTrue(all(self.g.get(p,0)==0 for p in self.d['route']))
        for p,q in zip(self.d['route'],self.d['route'][1:]):
            self.assertEqual(abs(p[0]-q[0])+abs(p[1]-q[1]),1)

    def test_defense_tallies_and_projectiles(self):
        self.assertTrue(self.d['shots'])
        end=self.d['states'][-1]
        self.assertEqual(end['kills']+end['escaped']+len(end['creeps']),24)
        for b in self.d['shots']:self.assertLess(b['start'],b['end'])

    def test_seed_is_deterministic_and_changes_bomber(self):
        same=a.plan_bomber(self.g,20260911)
        other=a.plan_bomber(self.g,20260912)
        self.assertEqual(self.b,same)
        self.assertNotEqual(self.b,other)

    def test_no_activity_does_not_fabricate_ore(self):
        empty={p:0 for p in self.g}
        self.assertEqual(a.plan_bomber(empty,0)['events'],[])
        self.assertEqual(a.plan_miners(empty,0)['events'],[])
        self.assertEqual(a.plan_defense(empty,0)['towers'],[])

    def test_invalid_intensity_is_rejected(self):
        obj=copy.deepcopy(self.meta);obj['active_columns']['44'][0]=5
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.json';p.write_text(json.dumps(obj))
            with self.assertRaises(ValueError):a.load_snapshot(p)

    def test_rendered_frames_have_real_changes(self):
        for name,model in [('bomber',self.b),('miners',self.n),('defense',self.d)]:
            draw=a.DRAWERS[name]
            first=draw(model,self.g,self.m,4.0,48)
            later=draw(model,self.g,self.m,8.2,48)
            self.assertEqual(first.size,(1040,420))
            self.assertNotEqual(first.tobytes(),later.tobytes())

if __name__=='__main__':unittest.main(verbosity=2)
