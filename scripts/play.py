#!/usr/bin/env python3
"""Visitor-powered arcade: Connect Four vs a bot, a hall of fame and tomorrow's ballot.

Visitors press a link in the README, which opens a pre-filled issue titled
``arcade: drop 3`` or ``arcade: vote snake``. A workflow feeds the open issues to
``process``; this module updates ``data/*.json`` and redraws ``assets/play/*.svg``.
Standard library only. Issue titles are untrusted input and are never executed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
from xml.sax.saxutils import escape

try:
    from scripts.rotate_arcade import ARCADE_EXPERIENCES, EXPERIENCE_DETAILS
except ModuleNotFoundError:
    from rotate_arcade import ARCADE_EXPERIENCES, EXPERIENCE_DETAILS

ROWS, COLS = 6, 7
BOT_DEPTH = 4
REPO = 'WSL043/WSL043'
LOGIN = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$')
COMMAND = re.compile(r'^arcade: (?:drop ([1-7])|vote ([a-z0-9-]{1,24}))$')
ORDER = (3, 2, 4, 1, 5, 0, 6)
THEMES = ('light', 'dark')
PALETTE = {
    'dark': dict(bg='#0b1020', panel='#141b34', line='#2a3566', text='#e8ecff', dim='#8b95c9',
                 cyan='#59f3ff', orange='#ff7a59', hole='#0b1020', extra=('#b98cff', '#7dff9b', '#ffd166')),
    'light': dict(bg='#f6f8ff', panel='#dfe6fb', line='#b7c1e8', text='#141b34', dim='#56608f',
                  cyan='#0094b0', orange='#e8501f', hole='#f6f8ff', extra=('#7c4dff', '#1a9e4a', '#c98a00')),
}
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
DATA = Path('data')
OUT = Path('assets/play')


class Rejected(Exception):
    """A move or vote that cannot be applied; the message is shown to the visitor."""


# ---------------------------------------------------------------- Connect Four
def new_state(previous=None):
    old = previous or {}
    return {'game': int(old.get('game', 0)) + 1, 'grid': ['.' * COLS] * ROWS, 'status': 'playing',
            'last': None, 'win': [], 'winner': None,
            'record': old.get('record') or {'visitors': 0, 'bot': 0, 'draws': 0},
            'players': old.get('players') or {}}


def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def drop_row(grid, col):
    for row in range(ROWS - 1, -1, -1):
        if grid[row][col] == '.':
            return row
    return None


def place(grid, col, who):
    row = drop_row(grid, col)
    if row is None:
        raise Rejected(f'Column {col + 1} is full.')
    grid = list(grid)
    grid[row] = grid[row][:col] + who + grid[row][col + 1:]
    return grid, row


def winning_line(grid, row, col):
    who = grid[row][col]
    if who == '.':
        return []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        cells = [(row, col)]
        for sign in (1, -1):
            r, c = row + dr * sign, col + dc * sign
            while 0 <= r < ROWS and 0 <= c < COLS and grid[r][c] == who:
                cells.append((r, c))
                r, c = r + dr * sign, c + dc * sign
        if len(cells) >= 4:
            return sorted(cells)
    return []


def board_full(grid):
    return '.' not in grid[0]


def evaluate(grid, who):
    """Heuristic from ``who``'s point of view: open windows of four plus centre control."""
    other = 'B' if who == 'V' else 'V'
    score = sum(3 for r in range(ROWS) if grid[r][3] == who) - sum(3 for r in range(ROWS) if grid[r][3] == other)
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                er, ec = r + dr * 3, c + dc * 3
                if not (0 <= er < ROWS and 0 <= ec < COLS):
                    continue
                window = [grid[r + dr * i][c + dc * i] for i in range(4)]
                mine, theirs = window.count(who), window.count(other)
                if mine and theirs:
                    continue
                weight = (0, 1, 5, 25)[max(mine, theirs)] if mine or theirs else 0
                score += weight if mine else -weight
    return score


def negamax(grid, depth, alpha, beta, who):
    other = 'B' if who == 'V' else 'V'
    if board_full(grid):
        return 0
    if depth == 0:
        return evaluate(grid, who)
    best = -10 ** 6
    for col in ORDER:
        row = drop_row(grid, col)
        if row is None:
            continue
        nxt, _ = place(grid, col, who)
        score = 10_000 + depth if winning_line(nxt, row, col) else -negamax(nxt, depth - 1, -beta, -alpha, other)
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def bot_move(grid, rng, depth=BOT_DEPTH):
    scores = {}
    for col in ORDER:
        row = drop_row(grid, col)
        if row is None:
            continue
        nxt, _ = place(grid, col, 'B')
        scores[col] = 10_000 + depth if winning_line(nxt, row, col) else -negamax(nxt, depth - 1, -10 ** 6, 10 ** 6, 'V')
    top = max(scores.values())
    return rng.choice([c for c in ORDER if scores.get(c) == top])


def bump_player(state, login, moves=0, wins=0):
    entry = state['players'].setdefault(login, {'moves': 0, 'wins': 0})
    entry['moves'] += moves
    entry['wins'] += wins


def visitor_move(state, col, login, rng=None):
    """Apply a visitor move (0-based column) and the bot's answer. Returns (state, message)."""
    rng = rng or random.Random()
    state = json.loads(json.dumps(state))
    if state['status'] != 'playing':
        state = new_state(state)
    grid, row = place(state['grid'], col, 'V')
    bump_player(state, login, moves=1)
    state['last'] = {'row': row, 'col': col, 'who': 'V', 'by': login}
    line = winning_line(grid, row, col)
    if line:
        state.update(grid=grid, status='visitor-won', win=[list(c) for c in line], winner=login)
        state['record']['visitors'] += 1
        bump_player(state, login, wins=1)
        return state, f'🎉 **Four in a row!** You beat the bot in round {state["game"]}. The next move starts a fresh round.'
    if board_full(grid):
        state.update(grid=grid, status='draw', win=[])
        state['record']['draws'] += 1
        return state, 'Board full — it is a draw. The next move starts a fresh round.'
    bcol = bot_move(grid, rng)
    grid, brow = place(grid, bcol, 'B')
    state['grid'] = grid
    state['last'] = {'row': brow, 'col': bcol, 'who': 'B', 'by': 'bot'}
    line = winning_line(grid, brow, bcol)
    if line:
        state.update(status='bot-won', win=[list(c) for c in line])
        state['record']['bot'] += 1
        return state, f'🤖 The bot got four in a row in column {bcol + 1}. Round {state["game"]} goes to the machine.'
    if board_full(grid):
        state.update(status='draw', win=[])
        state['record']['draws'] += 1
        return state, 'Board full — it is a draw. The next move starts a fresh round.'
    return state, f'You dropped a disc in column {col + 1}; the bot answered in column {bcol + 1}.'


# --------------------------------------------------------------------- Ballot
def cast_vote(votes, login, key):
    if key not in ARCADE_EXPERIENCES:
        raise Rejected(f'Unknown cartridge `{key}`.')
    votes = json.loads(json.dumps(votes or {'votes': {}}))
    votes.setdefault('votes', {})[login] = key
    return votes


def tally(votes):
    counts = {k: 0 for k in ARCADE_EXPERIENCES}
    for key in (votes or {}).get('votes', {}).values():
        if key in counts:
            counts[key] += 1
    return counts


def vote_winner(votes, current, rng):
    """Most-voted cartridge other than today's; ties are drawn at random; None without votes."""
    counts = {k: n for k, n in tally(votes).items() if k != current and n > 0}
    if not counts:
        return None
    top = max(counts.values())
    return rng.choice([k for k in ARCADE_EXPERIENCES if counts.get(k) == top])


def reset_votes(day):
    return {'votes': {}, 'since': day}


# ------------------------------------------------------------------- Processor
def process_issues(issues, state, votes, rng=None):
    """Handle open ``arcade:`` issues oldest first. Returns (state, votes, results)."""
    rng = rng or random.Random()
    results = []
    for issue in sorted(issues, key=lambda i: i['number']):
        title = ' '.join(str(issue.get('title', '')).split()).lower()
        if not title.startswith('arcade:'):
            continue
        login = str((issue.get('author') or {}).get('login', ''))
        number = issue['number']
        match = COMMAND.match(title)
        try:
            if not LOGIN.match(login) or not match:
                raise Rejected('I did not recognise that command. Use the buttons on the profile page.')
            if match.group(1):
                state, message = visitor_move(state, int(match.group(1)) - 1, login, rng)
                message += ' The board refreshes within a couple of minutes (GitHub caches images).'
            else:
                votes = cast_vote(votes, login, match.group(2))
                message = (f'🗳️ Vote counted for **{EXPERIENCE_DETAILS[match.group(2)]["title"]}**. '
                           "The most-voted cartridge headlines the next daily draw.")
        except Rejected as exc:
            message = f'⚠️ {exc}'
        results.append({'number': number, 'comment': f'@{login} {message}' if LOGIN.match(login) else message})
    return state, votes, results


# ------------------------------------------------------------------- Rendering
def _svg(width, height, title, css, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{escape(title)}">\n<title>{escape(title)}</title>\n<style>{css}</style>\n{body}\n</svg>\n')


def _text(x, y, s, size, fill, weight='400', anchor='start', spacing=0, extra=''):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" letter-spacing="{spacing}" {extra}>{escape(str(s))}</text>')


W, X0, HEAD, CELL = 714, 7, 56, 100
BOARD_H = ROWS * CELL


def frame_path(r=18):
    x, y, w, h = X0, HEAD, COLS * CELL, BOARD_H
    d = (f'M{x + r},{y}H{x + w - r}A{r},{r} 0 0 1 {x + w},{y + r}V{y + h - r}A{r},{r} 0 0 1 {x + w - r},{y + h}'
         f'H{x + r}A{r},{r} 0 0 1 {x},{y + h - r}V{y + r}A{r},{r} 0 0 1 {x + r},{y}Z')
    for row in range(ROWS):
        for col in range(COLS):
            cx, cy = x + col * CELL + CELL // 2, y + row * CELL + CELL // 2
            d += f'M{cx - 40},{cy}a40,40 0 1 0 80,0a40,40 0 1 0 -80,0Z'
    return d


def status_line(state):
    status = state['status']
    if status == 'visitor-won':
        return f'VISITORS WIN · @{state.get("winner")}', 'cyan'
    if status == 'bot-won':
        return 'BOT WINS · TRY AGAIN', 'orange'
    if status == 'draw':
        return 'DRAW · TRY AGAIN', 'dim'
    return 'YOUR MOVE ▸ PICK A COLUMN', 'text'


def render_board(state, theme):
    p = PALETTE[theme]
    last, win = state.get('last'), {tuple(c) for c in state.get('win', [])}
    fall = (last['row'] + 1) * CELL if last else 0
    css = (f'.drop{{animation:drop .75s cubic-bezier(.3,1.25,.6,1) both}}'
           f'@keyframes drop{{from{{transform:translateY(-{fall}px)}}to{{transform:translateY(0)}}}}'
           '.glow{animation:glow 1s ease-in-out infinite alternate}'
           '@keyframes glow{from{stroke-opacity:.25}to{stroke-opacity:1}}'
           '.blink{animation:blink 1.1s steps(2,start) infinite}@keyframes blink{to{visibility:hidden}}')
    discs = []
    for row in range(ROWS):
        for col in range(COLS):
            who = state['grid'][row][col]
            if who == '.':
                continue
            cx, cy = X0 + col * CELL + CELL // 2, HEAD + row * CELL + CELL // 2
            color = p['cyan'] if who == 'V' else p['orange']
            is_last = bool(last) and (row, col) == (last['row'], last['col'])
            disc = (f'<circle cx="{cx}" cy="{cy}" r="42" fill="{color}"/>'
                    f'<circle cx="{cx}" cy="{cy}" r="28" fill="none" stroke="{p["bg"]}" stroke-opacity=".28" stroke-width="5"/>')
            discs.append(f'<g class="drop">{disc}</g>' if is_last else f'<g>{disc}</g>')
    rings = ''.join(f'<circle class="glow" cx="{X0 + c * CELL + 50}" cy="{HEAD + r * CELL + 50}" r="46" fill="none" '
                    f'stroke="{p["text"]}" stroke-width="5"/>' for r, c in sorted(win))
    label, tone = status_line(state)
    cursor = '<tspan class="blink"> █</tspan>' if state['status'] == 'playing' else ''
    header = (f'<circle cx="{X0 + 12}" cy="26" r="8" fill="{p["cyan"]}"/>' + _text(X0 + 28, 31, 'VISITORS', 15, p['dim'], '700', spacing=2)
              + f'<circle cx="{X0 + 148}" cy="26" r="8" fill="{p["orange"]}"/>' + _text(X0 + 164, 31, 'BOT', 15, p['dim'], '700', spacing=2)
              + f'<text x="{W - X0}" y="31" font-family="{FONT}" font-size="16" font-weight="700" fill="{p[tone]}" '
                f'text-anchor="end" letter-spacing="2">{escape(label)}{cursor}</text>')
    labels = ''.join(_text(X0 + c * CELL + 50, HEAD + BOARD_H + 26, c + 1, 16, p['dim'], '700', 'middle') for c in range(COLS))
    body = (f'<clipPath id="b"><rect x="{X0}" y="{HEAD}" width="{COLS * CELL}" height="{BOARD_H}"/></clipPath>'
            f'<rect width="{W}" height="{HEAD + BOARD_H + 40}" fill="{p["bg"]}"/>{header}'
            f'<g clip-path="url(#b)">{"".join(discs)}</g>'
            f'<path d="{frame_path()}" fill="{p["panel"]}" stroke="{p["line"]}" stroke-width="2" fill-rule="evenodd"/>'
            f'{rings}{labels}')
    return _svg(W, HEAD + BOARD_H + 40, f'Connect Four, round {state["game"]}: {label}', css, body)


def identicon(login, theme, x, y, size=6):
    digest = hashlib.sha256(login.lower().encode()).digest()
    p = PALETTE[theme]
    colors = (p['cyan'], p['orange']) + tuple(p['extra'])
    color = colors[digest[0] % len(colors)]
    cells = []
    for row in range(5):
        for col in range(3):
            if digest[1 + row * 3 + col] & 1:
                for c in {col, 4 - col}:
                    cells.append(f'<rect x="{x + c * size}" y="{y + row * size}" width="{size}" height="{size}" fill="{color}"/>')
    return ''.join(cells)


def ranking(state, limit=5):
    rows = [(login, e['moves'] + 10 * e['wins'], e['wins']) for login, e in state.get('players', {}).items() if LOGIN.match(login)]
    return sorted(rows, key=lambda r: (-r[1], r[0]))[:limit]


def render_scoreboard(state, theme):
    p = PALETTE[theme]
    rec = state['record']
    body = [f'<rect width="{W}" height="236" fill="{p["bg"]}"/>',
            f'<rect x="{X0}" y="8" width="250" height="220" rx="14" fill="{p["panel"]}" stroke="{p["line"]}" stroke-width="2"/>',
            _text(X0 + 20, 40, 'ROUND RECORD', 14, p['dim'], '700', spacing=3)]
    for i, (name, n, tone) in enumerate((('VISITORS', rec['visitors'], 'cyan'), ('BOT', rec['bot'], 'orange'), ('DRAWS', rec['draws'], 'dim'))):
        y = 92 + i * 52
        body += [_text(X0 + 20, y, n, 38, p[tone], '700'), _text(X0 + 230, y - 6, name, 14, p['dim'], '700', 'end', 3)]
    body += [f'<rect x="{X0 + 266}" y="8" width="{W - 2 * X0 - 266}" height="220" rx="14" fill="{p["panel"]}" stroke="{p["line"]}" stroke-width="2"/>',
             _text(X0 + 286, 40, 'HALL OF FAME', 14, p['dim'], '700', spacing=3)]
    rows = ranking(state)
    if not rows:
        body.append(_text(X0 + 286, 110, 'No names yet — be the first to play.', 15, p['text']))
    for i, (login, score, wins) in enumerate(rows):
        y = 58 + i * 33
        body += [_text(X0 + 286, y + 26, f'{i + 1}.', 15, p['dim'], '700'), identicon(login, theme, X0 + 316, y + 1),
                 _text(X0 + 368, y + 25, f'@{login}', 16, p['text'], '700'),
                 _text(W - X0 - 20, y + 25, f'{score} pt{"" if score == 1 else "s"}' + (f' · {wins}★' if wins else ''), 15, p['dim'], '400', 'end')]
    return _svg(W, 236, f'Scoreboard: visitors {rec["visitors"]}, bot {rec["bot"]}, draws {rec["draws"]}', '', ''.join(body))


def render_ballot(votes, theme, current=None):
    p = PALETTE[theme]
    counts = tally(votes)
    top = max(counts.values())
    keys = list(ARCADE_EXPERIENCES)
    since = (votes or {}).get('since')
    heading = "TOMORROW'S BALLOT" + (f' · SINCE {since}' if since else '')
    body = [f'<rect width="{W}" height="248" fill="{p["bg"]}"/>',
            f'<rect x="{X0}" y="8" width="{W - 2 * X0}" height="232" rx="14" fill="{p["panel"]}" stroke="{p["line"]}" stroke-width="2"/>',
            _text(X0 + 20, 38, heading, 14, p['dim'], '700', spacing=3)]
    for i, key in enumerate(keys):
        col, row = divmod(i, 6)
        x, y = X0 + 20 + col * 340, 58 + row * 29
        n = counts[key]
        lead = n > 0 and n == top
        tint = p['cyan'] if lead else p['dim']
        name = EXPERIENCE_DETAILS[key]['title']
        body += [_text(x, y + 15, name, 12, p['text'] if key != current else p['dim'], '700' if lead else '400'),
                 f'<rect x="{x + 190}" y="{y + 4}" width="90" height="12" rx="6" fill="{p["bg"]}"/>']
        if n:
            body.append(f'<rect x="{x + 190}" y="{y + 4}" width="{max(12, round(90 * n / top))}" height="12" rx="6" fill="{tint}"/>')
        body.append(_text(x + 300, y + 15, n, 13, tint, '700', 'end'))
    summary = ', '.join(f'{EXPERIENCE_DETAILS[k]["title"]} {v}' for k, v in counts.items() if v) or 'no votes yet'
    return _svg(W, 248, f"Tomorrow's ballot: {summary}", '', ''.join(body))


def render_button(col, theme):
    p = PALETTE[theme]
    body = (f'<rect x="3" y="3" width="94" height="58" rx="12" fill="{p["panel"]}" stroke="{p["cyan"]}" stroke-width="3"/>'
            f'<path d="M37 16h26v10h9L50 42 28 26h9z" fill="{p["cyan"]}"/>'
            + _text(50, 56, col, 13, p['text'], '700', 'middle'))
    return _svg(100, 64, f'Drop a disc in column {col}', '', body)


def render_all(state, votes, out=OUT, current=None):
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        (out / f'connect4-{theme}.svg').write_text(render_board(state, theme), encoding='utf-8')
        (out / f'scoreboard-{theme}.svg').write_text(render_scoreboard(state, theme), encoding='utf-8')
        (out / f'ballot-{theme}.svg').write_text(render_ballot(votes, theme, current), encoding='utf-8')
        for col in range(1, COLS + 1):
            (out / f'drop-{col}-{theme}.svg').write_text(render_button(col, theme), encoding='utf-8')


# ------------------------------------------------------------------ README bits
def issue_link(command, label):
    body = quote_plus('Just press "Submit new issue". A bot reads the title, plays it, and closes this issue.')
    return f'<a href="https://github.com/{REPO}/issues/new?title={quote_plus("arcade: " + command)}&body={body}">{label}</a>'


def vote_links():
    return ' · '.join(issue_link(f'vote {k}', EXPERIENCE_DETAILS[k]['title']) for k in ARCADE_EXPERIENCES)


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    run = sub.add_parser('process')
    run.add_argument('--issues', type=Path, required=True)
    run.add_argument('--results', type=Path, required=True)
    sub.add_parser('build')
    sub.add_parser('vote-links')
    args = p.parse_args(argv)
    state = load_json(DATA / 'connect4.json', None) or new_state()
    votes = load_json(DATA / 'votes.json', None) or reset_votes(datetime.now(timezone.utc).date().isoformat())
    arcade = load_json(Path('.github/arcade-state.json'), {})
    if args.cmd == 'vote-links':
        print(vote_links())
        return 0
    results = []
    if args.cmd == 'process':
        issues = json.loads(args.issues.read_text(encoding='utf-8'))
        state, votes, results = process_issues(issues, state, votes)
        args.results.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    save_json(DATA / 'connect4.json', state)
    save_json(DATA / 'votes.json', votes)
    render_all(state, votes, current=arcade.get('current'))
    print(f'Handled {len(results)} issue(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
