import unittest
from scripts.svg_models import Calendar, minecraft

class BlockScenes(unittest.TestCase):
    def test_complete_cover_and_legal_bricks(self):
        for dense in (False, True):
            grid = {(x, y): (1+(x//3+y)%4 if dense or (x+y)%3 else 0) for x in range(54) for y in range(7)}
            cal = Calendar(54, grid, set(), [], 'test', '2026-09-16')
            for seed in range(10):
                self.assertCountEqual(minecraft(cal, seed)['order'], cal.active)

if __name__ == '__main__':
    unittest.main()
