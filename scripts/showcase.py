#!/usr/bin/env python3
"""Daily showcase: a "Now Playing" strip and live project cards, drawn as vector SVG.

Reads public repository facts from the GitHub API (stars, language, latest release,
last push) and redraws ``assets/showcase/*.svg``. Standard library only; text is escaped.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import textwrap
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

OWNER = 'WSL043'
PROFILE_REPO = 'WSL043'
OUT = Path('assets/showcase')
THEMES = ('light', 'dark')
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
PALETTE = {
    'dark': dict(bg='#0b1020', panel='#141b34', line='#2a3566', text='#e8ecff', dim='#8b95c9',
                 accents=('#59f3ff', '#ff7a59', '#b98cff', '#7dff9b', '#ffd166'), live='#7dff9b'),
    'light': dict(bg='#f6f8ff', panel='#e9eefc', line='#b7c1e8', text='#141b34', dim='#56608f',
                  accents=('#0094b0', '#e8501f', '#7c4dff', '#1a9e4a', '#c98a00'), live='#1a9e4a'),
}
LANGUAGES = {'JavaScript': '#f1e05a', 'TypeScript': '#3178c6', 'Python': '#3572A5', 'Rust': '#dea584', 'Go': '#00ADD8'}
PROJECTS = (
    ('DSH-Portable', 'DSH Portable', 'Portable desktop distribution for Windows, macOS and Linux with independent app and kernel updates.'),
    ('dsh-codex-subscription', 'Codex Subscription for DSH', 'ChatGPT / Codex subscription integration: auth, models, usage, search and images.'),
    ('loudease', 'LoudEase', 'Local audio normalization for Chrome. AudioWorklet DSP with look-ahead limiting.'),
    ('updated-again', 'Updated Again', 'A self-updating software toy: signed daily capsules and local rollback.'),
    ('agent-skills-neutral', 'Agent Skills Neutral', 'Vendor-neutral reasoning and workflow library with held-out evaluation.'),
)


def api_get(path, token=None):
    request = urllib.request.Request(f'https://api.github.com{path}', headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'profile-showcase',
        **({'Authorization': f'Bearer {token}'} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def ago(value, now):
    seconds = max(0, int((now - parse_time(value)).total_seconds()))
    for unit, size in (('mo', 2_592_000), ('d', 86_400), ('h', 3_600), ('m', 60)):
        if seconds >= size:
            return f'{seconds // size}{unit} ago'
    return 'just now'


def collect(fetch=api_get, token=None):
    projects = []
    for slug, title, description in PROJECTS:
        repo = fetch(f'/repos/{OWNER}/{slug}', token)
        if not repo:
            raise RuntimeError(f'Repository not found: {slug}')
        release = fetch(f'/repos/{OWNER}/{slug}/releases/latest', token)
        projects.append({'slug': slug, 'title': title, 'description': description, 'stars': repo['stargazers_count'],
                         'language': repo.get('language'), 'pushed_at': repo['pushed_at'],
                         'release': (release or {}).get('tag_name')})
    recent = [r for r in fetch(f'/users/{OWNER}/repos?sort=pushed&per_page=10&type=owner', token) or []
              if not r.get('fork') and not r.get('private') and r['name'] != PROFILE_REPO]
    latest = recent[0] if recent else None
    user = fetch(f'/users/{OWNER}', token) or {}
    return {'projects': projects, 'public_repos': user.get('public_repos', 0),
            'latest': {'name': latest['name'], 'pushed_at': latest['pushed_at']} if latest else None}


def _text(x, y, s, size, fill, weight='400', anchor='start', spacing=0):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}" letter-spacing="{spacing}">{escape(str(s))}</text>')


def _svg(width, height, title, css, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title, {chr(34): '&quot;'})}">\n'
            f'<title>{escape(title)}</title>\n<style>{css}</style>\n{body}\n</svg>\n')


def pixel_icon(name, color, bg, x, y, size=9):
    """Symmetric 5x5 sprite derived from the repository name."""
    digest = hashlib.sha256(name.lower().encode()).digest()
    cells = []
    for row in range(5):
        for col in range(3):
            if digest[1 + row * 3 + col] & 1:
                for c in sorted({col, 4 - col}):
                    cells.append(f'<rect x="{x + c * size}" y="{y + row * size}" width="{size}" height="{size}" fill="{color}"/>')
    return f'<rect x="{x - 8}" y="{y - 8}" width="{size * 5 + 16}" height="{size * 5 + 16}" rx="10" fill="{bg}"/>' + ''.join(cells)


def render_now_playing(data, theme, now):
    p = PALETTE[theme]
    latest = data['latest']
    css = ('.eq{transform-box:fill-box;transform-origin:50% 100%;animation:eq 1s ease-in-out infinite alternate}'
           '@keyframes eq{from{transform:scaleY(.25)}to{transform:scaleY(1)}}')
    bars = ''.join(f'<rect class="eq" x="{28 + i * 11}" y="20" width="7" height="24" rx="2" fill="{p["accents"][i % 2]}" '
                   f'style="animation-delay:-{i * 0.23:.2f}s;animation-duration:{0.7 + i * 0.13:.2f}s"/>' for i in range(5))
    if latest:
        title = f'Now playing: {latest["name"]}, pushed {ago(latest["pushed_at"], now)}'
        text = (_text(100, 27, 'NOW PLAYING', 12, p['dim'], '700', spacing=3)
                + _text(100, 47, latest['name'], 18, p['text'], '700')
                + _text(686, 38, f'last push {ago(latest["pushed_at"], now)}', 14, p['dim'], anchor='end'))
    else:
        title = 'Now playing: the workshop'
        text = _text(100, 38, 'NOW PLAYING · the workshop', 16, p['text'], '700')
    body = (f'<rect width="714" height="64" fill="{p["bg"]}"/>'
            f'<rect x="7" y="4" width="700" height="56" rx="14" fill="{p["panel"]}" stroke="{p["line"]}" stroke-width="2"/>'
            f'{bars}{text}')
    return _svg(714, 64, title, css, body)


def wrap(text, width=40, lines=3):
    rows = textwrap.wrap(text, width)
    if len(rows) > lines:
        rows = rows[:lines]
        rows[-1] = rows[-1][:width - 1].rstrip() + '…'
    return rows


def render_card(project, index, theme, now):
    p = PALETTE[theme]
    accent = p['accents'][index % len(p['accents'])]
    live = (now - parse_time(project['pushed_at'])).total_seconds() < 86_400
    css = '.pulse{animation:pulse 1.6s ease-in-out infinite alternate}@keyframes pulse{from{opacity:.25}to{opacity:1}}'
    body = [f'<rect width="440" height="188" fill="{p["bg"]}"/>',
            f'<rect x="3" y="3" width="434" height="182" rx="16" fill="{p["panel"]}" stroke="{p["line"]}" stroke-width="2"/>',
            f'<rect x="3" y="3" width="434" height="8" rx="4" fill="{accent}"/>',
            pixel_icon(project['slug'], accent, p['bg'], 34, 38),
            _text(104, 52, project['title'], 18, p['text'], '700')]
    for i, row in enumerate(wrap(project['description'])):
        body.append(_text(104, 76 + i * 19, row, 13, p['dim']))
    y, x = 168, 26
    body.append(_text(x, y, f'★ {project["stars"]}', 14, p['text'], '700'))
    x += 30 + 9 * len(str(project['stars']))
    if project['language']:
        color = LANGUAGES.get(project['language'], p['dim'])
        body += [f'<circle cx="{x + 6}" cy="{y - 5}" r="5" fill="{color}"/>', _text(x + 18, y, project['language'], 13, p['dim'])]
        x += 30 + 8 * len(project['language'])
    if project['release']:
        label = project['release'][:12]
        width = 14 + 8 * len(label)
        body += [f'<rect x="{x}" y="{y - 15}" width="{width}" height="20" rx="10" fill="none" stroke="{accent}" stroke-width="1.5"/>',
                 _text(x + width / 2, y, label, 12, accent, '700', 'middle')]
    status = ago(project['pushed_at'], now)
    if live:
        body.append(f'<circle class="pulse" cx="{414 - 8 * len(status) - 6}" cy="{y - 5}" r="4" fill="{p["live"]}"/>')
    body.append(_text(414, y, status, 12, p['dim'], anchor='end'))
    return _svg(440, 188, f'{project["title"]}: {project["stars"]} stars, pushed {status}', css, ''.join(body))


def render_more_card(data, theme):
    p = PALETTE[theme]
    body = (f'<rect width="440" height="188" fill="{p["bg"]}"/>'
            f'<rect x="3" y="3" width="434" height="182" rx="16" fill="{p["panel"]}" stroke="{p["line"]}" stroke-width="2" stroke-dasharray="8 6"/>'
            + _text(220, 84, 'THE WHOLE WORKSHOP', 16, p['text'], '700', 'middle', 3)
            + _text(220, 112, f'{data["public_repos"]} public repositories, experiments included', 13, p['dim'], anchor='middle')
            + _text(220, 148, '▸ browse them all', 14, p['accents'][0], '700', 'middle'))
    return _svg(440, 188, 'Browse the whole workshop', '', body)


def render_all(data, out=OUT, now=None):
    now = now or datetime.now(timezone.utc)
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        files = {f'now-playing-{theme}.svg': render_now_playing(data, theme, now),
                 f'card-more-{theme}.svg': render_more_card(data, theme)}
        for index, project in enumerate(data['projects']):
            files[f'card-{project["slug"]}-{theme}.svg'] = render_card(project, index, theme, now)
        for name, content in files.items():
            (out / name).write_text(content, encoding='utf-8', newline='\n')


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=OUT)
    args = p.parse_args(argv)
    data = collect(token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'))
    render_all(data, args.out)
    print(f'Rendered {len(data["projects"])} cards; latest push: {(data["latest"] or {}).get("name")}')


if __name__ == '__main__':
    main()
