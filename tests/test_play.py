import random
import unittest
import xml.etree.ElementTree as ET

from scripts import play
from scripts.rotate_arcade import ARCADE_EXPERIENCES, select_daily


def board(*rows):
    return [r.ljust(play.COLS, '.') for r in rows]


class EngineTests(unittest.TestCase):
    def test_detects_all_four_directions(self):
        horizontal = board('', '', '', '', '', 'VVVV')
        self.assertEqual(len(play.winning_line(horizontal, 5, 0)), 4)
        vertical = board('', '', 'V', 'V', 'V', 'V')
        self.assertEqual(len(play.winning_line(vertical, 5, 0)), 4)
        diagonal = board('', '', '...V', '..V', '.V', 'V')
        self.assertEqual(len(play.winning_line(diagonal, 5, 0)), 4)
        anti = board('', '', 'V', '.V', '..V', '...V')
        self.assertEqual(len(play.winning_line(anti, 5, 3)), 4)
        self.assertEqual(play.winning_line(board('', '', '', '', '', 'VVV'), 5, 0), [])

    def test_bot_takes_an_immediate_win(self):
        grid = board('', '', '', '', 'V.V', 'BBB')
        self.assertEqual(play.bot_move(grid, random.Random(1)), 3)

    def test_bot_blocks_an_immediate_loss(self):
        grid = board('', '', '', '', 'B', 'VVV')
        self.assertEqual(play.bot_move(grid, random.Random(1)), 3)

    def test_full_column_is_rejected(self):
        state = play.new_state()
        state['grid'] = ['V......', 'B......', 'V......', 'B......', 'V......', 'B......']
        with self.assertRaises(play.Rejected):
            play.visitor_move(state, 0, 'octocat')

    def test_move_places_disc_and_bot_answers(self):
        state, message = play.visitor_move(play.new_state(), 3, 'octocat', random.Random(1))
        discs = ''.join(state['grid'])
        self.assertEqual((discs.count('V'), discs.count('B')), (1, 1))
        self.assertEqual(state['players']['octocat']['moves'], 1)
        self.assertIn('column 4', message)

    def test_visitor_win_is_recorded_and_next_move_starts_new_round(self):
        state = play.new_state()
        state['grid'] = board('', '', '', '', 'B', 'VVV')
        state['grid'][4] = 'B.B....'
        done, message = play.visitor_move(state, 3, 'octocat', random.Random(1))
        self.assertEqual((done['status'], done['winner']), ('visitor-won', 'octocat'))
        self.assertEqual(done['record']['visitors'], 1)
        self.assertEqual(done['players']['octocat']['wins'], 1)
        self.assertEqual(len(done['win']), 4)
        again, _ = play.visitor_move(done, 0, 'octocat', random.Random(1))
        self.assertEqual((again['game'], again['status']), (2, 'playing'))
        self.assertEqual(again['record']['visitors'], 1)

    def test_bot_game_always_terminates(self):
        rng = random.Random(7)
        state = play.new_state()
        for _ in range(45):
            open_cols = [c for c in range(play.COLS) if play.drop_row(state['grid'], c) is not None]
            state, _ = play.visitor_move(state, rng.choice(open_cols), 'a', rng)
            if state['status'] != 'playing':
                break
        self.assertNotEqual(state['status'], 'playing')


class ProcessorTests(unittest.TestCase):
    def run_issues(self, issues, state=None, votes=None):
        return play.process_issues(issues, state or play.new_state(), votes or play.reset_votes('2026-09-29'), random.Random(3))

    def test_commands_are_parsed_strictly(self):
        for bad in ('arcade: drop 8', 'arcade: drop 3; rm -rf', 'arcade: vote ../../x', 'arcade: nonsense'):
            _, _, results = self.run_issues([{'number': 1, 'title': bad, 'author': {'login': 'octocat'}}])
            self.assertIn('did not recognise', results[0]['comment'], bad)

    def test_other_issues_are_ignored(self):
        _, _, results = self.run_issues([{'number': 1, 'title': 'Bug: something', 'author': {'login': 'octocat'}}])
        self.assertEqual(results, [])

    def test_bot_accounts_and_odd_logins_cannot_play(self):
        state, _, results = self.run_issues([{'number': 1, 'title': 'arcade: drop 1', 'author': {'login': 'x[bot]'}}])
        self.assertEqual(''.join(state['grid']).count('V'), 0)
        self.assertIn('did not recognise', results[0]['comment'])

    def test_oldest_issue_is_handled_first_and_vote_is_counted(self):
        issues = [{'number': 5, 'title': 'ARCADE:  vote   Snake', 'author': {'login': 'b'}},
                  {'number': 2, 'title': 'arcade: vote portal', 'author': {'login': 'a'}}]
        _, votes, results = self.run_issues(issues)
        self.assertEqual([r['number'] for r in results], [2, 5])
        self.assertEqual(votes['votes'], {'a': 'portal', 'b': 'snake'})

    def test_one_vote_per_visitor_latest_wins(self):
        votes = play.cast_vote(play.cast_vote(play.reset_votes('2026-09-29'), 'a', 'snake'), 'a', 'lego')
        self.assertEqual(play.tally(votes)['lego'], 1)
        self.assertEqual(play.tally(votes)['snake'], 0)

    def test_unknown_cartridge_is_rejected(self):
        with self.assertRaises(play.Rejected):
            play.cast_vote(play.reset_votes('2026-09-29'), 'a', 'defense')


class VoteRotationTests(unittest.TestCase):
    def test_winner_ignores_todays_cartridge_and_needs_votes(self):
        votes = {'votes': {'a': 'snake', 'b': 'snake', 'c': 'lego'}}
        self.assertEqual(play.vote_winner(votes, 'snake', random.Random(1)), 'lego')
        self.assertEqual(play.vote_winner(votes, 'portal', random.Random(1)), 'snake')
        self.assertIsNone(play.vote_winner({'votes': {}}, 'portal', random.Random(1)))

    def test_voted_cartridge_is_drawn_and_leaves_the_shuffle_bag(self):
        state = {'current': 'snake', 'remaining': ['lego', 'portal'], 'cycle': 1, 'updated_on': '2026-09-28', 'catalog_version': 4}
        selected, new = select_daily(state, '2026-09-29', voted='portal')
        self.assertEqual(selected, 'portal')
        self.assertNotIn('portal', new['remaining'])
        self.assertEqual(new['updated_on'], '2026-09-29')

    def test_same_day_rerun_ignores_votes(self):
        state = {'current': 'snake', 'remaining': ['lego'], 'cycle': 1, 'updated_on': '2026-09-29', 'catalog_version': 4}
        self.assertEqual(select_daily(state, '2026-09-29', voted='lego')[0], 'snake')


class RenderTests(unittest.TestCase):
    def test_every_generated_svg_is_well_formed_and_self_contained(self):
        state, _ = play.visitor_move(play.new_state(), 3, 'octocat', random.Random(1))
        state['players']['<script>'] = {'moves': 3, 'wins': 0}
        votes = play.cast_vote(play.reset_votes('2026-09-29'), 'octocat', 'snake')
        for theme in play.THEMES:
            files = [play.render_board(state, theme), play.render_scoreboard(state, theme),
                     play.render_ballot(votes, theme, 'lego'), play.render_button(4, theme)]
            for raw in files:
                ET.fromstring(raw)
                self.assertNotIn('<script', raw)
                self.assertNotIn('href', raw)
                self.assertNotIn('http://www.w3.org/1999/xlink', raw)

    def test_winning_board_highlights_four_cells(self):
        state = play.new_state()
        state['grid'] = board('', '', '', '', 'B', 'VVV')
        state['grid'][4] = 'B.B....'
        done, _ = play.visitor_move(state, 3, 'octocat', random.Random(1))
        self.assertEqual(play.render_board(done, 'dark').count('class="glow"'), 4)

    def test_vote_links_cover_every_cartridge_with_encoded_titles(self):
        links = play.vote_links()
        for key in ARCADE_EXPERIENCES:
            self.assertIn(f'title=arcade%3A+vote+{key}', links)


if __name__ == '__main__':
    unittest.main()
