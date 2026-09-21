"""Repository/public-build documentation boundaries and active Markdown links."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ('operations', 'reference/environment', 'reference/architecture', 'reference/api',
           'reference/extending', 'social/worker', 'EXECUTION_PLAN', 'PROGRESS0910', 'TESTING', 'inventory', 'en/operations')
READER_HISTORY = re.compile(
    r'旧ルート|(?:現在|現行)の実装に合わせ|廃止しています|移管しました|'
    r'出力しません|出しません|ログへ残しません|同じServiceへ委譲|'
    r'compatibility commands|retired (?:settings|warning counters)|'
    r'checked against the registered command tree', re.IGNORECASE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--built', action='store_true')
    args = parser.parse_args()
    errors = []
    pages = [ROOT / 'AGENTS.md', ROOT / 'README.md', ROOT / 'ROADMAP.md', ROOT / 'deploy/README.md', *(ROOT / 'docs').rglob('*.md'), *(ROOT / 'handbook').rglob('*.md')]
    for page in pages:
        if any(part in ('node_modules', '.vitepress', 'history', 'inventory') for part in page.parts) or page.name in ('PROGRESS0910.md', 'DOCUMENT_MAP.md'):
            continue
        text = page.read_text(encoding='utf-8')
        public = page.is_relative_to(ROOT / 'docs')
        reader_guide = public or page.is_relative_to(ROOT / 'handbook/operator') or page in (ROOT / 'README.md', ROOT / 'deploy/README.md')
        if reader_guide:
            for number, line in enumerate(text.splitlines(), 1):
                if READER_HISTORY.search(line):
                    errors.append(f'Reader-facing language {page.relative_to(ROOT)}:{number}; describe usage/results (see handbook/developer/DOCUMENTATION.md)')
        if page.name != 'DOCUMENTATION.md' and re.search(r'Dockerfile\.(?:web-test|test)\b|runDashboard\.bat|scripts/web-baseline\.mjs', text):
            errors.append(f'Removed task entry point in {page.relative_to(ROOT)}')
        if public and ('handbook/' in text or re.search(r'\]\([^)]*/operations/', text)):
            errors.append(f'Private reference in {page.relative_to(ROOT)}')
        for target in re.findall(r'\]\(([^\s)]+)\)', text):
            if target.startswith(('#', '/', 'http:', 'https:', 'mailto:')) or '${' in target:
                continue
            target = target.split('#')[0]
            resolved = (page.parent / target).resolve()
            if not any(p.exists() for p in (resolved, resolved.with_suffix('.md'), resolved / 'index.md')):
                errors.append(f'Broken link {page.relative_to(ROOT)}: {target}')
    if args.built:
        dist = ROOT / 'docs/.vitepress/dist'
        if not (dist / 'index.html').is_file():
            errors.append('Docs build missing')
        for target in PRIVATE:
            if (dist / target).exists() or (dist / (target + '.html')).exists():
                errors.append('Private build page: ' + target)
        for path in dist.rglob('*'):
            if path.suffix in ('.html', '.js', '.json'):
                content = path.read_text(encoding='utf-8')
                for marker in ('PROGRESS0910', 'EXECUTION_PLAN', 'handbook/operator', 'handbook/developer'):
                    if marker in content:
                        errors.append(f'Private content/index marker {marker}: {path.name}')
    if errors:
        raise SystemExit('\n'.join(sorted(set(errors))))
    print('Documentation links and public boundaries: OK')


if __name__ == '__main__':
    main()
