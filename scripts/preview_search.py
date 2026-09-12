"""Render the search comparison from a saved snapshot without editing the profile."""
import argparse
import json
from pathlib import Path
from scripts.svg_models import Calendar
from scripts.search_race import comparison, render_comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path('assets/arcade/heatmap-snapshot.json'))
    parser.add_argument('--output', type=Path, default=Path('.rotation-preview/search'))
    args = parser.parse_args()
    cal = Calendar.from_snapshot(json.loads(args.snapshot.read_text(encoding='utf-8')))
    report = comparison(cal)
    args.output.mkdir(parents=True, exist_ok=True)
    for theme in ('dark', 'light'):
        (args.output/f'search-comparison-{theme}.svg').write_text(render_comparison(cal, theme, report), encoding='utf-8')
    (args.output/'search-comparison.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'snapshot': str(args.snapshot), 'date': cal.day,
        'results': {key: {k: value[k] for k in ('steps', 'cost', 'expanded')} for key, value in report['results'].items()}}, indent=2))


if __name__ == '__main__':
    main()
