#!/usr/bin/env python3
"""Check paired current manuals, local Markdown links and language entry points."""
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    errors = []
    for path in sorted((root/'docs').glob('*.md')):
        peer = path.with_name(path.name.replace('.zh-CN.md', '.md')) if path.name.endswith('.zh-CN.md') else path.with_name(path.stem+'.zh-CN.md')
        text = path.read_text(encoding='utf-8')
        if not peer.exists():
            errors.append(str(path.relative_to(root))+': missing language counterpart '+peer.name)
        if peer.name not in text:
            errors.append(str(path.relative_to(root))+': missing language link')
    ignored = {'output', 'cache', 'source_cache', 'private', 'customer_data', '__pycache__'}
    for path in sorted(root.rglob('*.md')):
        parts = path.relative_to(root).parts
        if any(part.startswith('.') or part in ignored for part in parts):
            continue
        prose = re.sub(r'^```[^\n]*\n.*?^```[^\n]*$', '', path.read_text(encoding='utf-8'), flags=re.M|re.S)
        for link in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', prose):
            if re.match(r'^[a-zA-Z]+:', link):
                continue
            target, _, anchor = unquote(link.strip('<>')).partition('#')
            dest = (path.parent/target).resolve() if target else path
            if not dest.exists():
                errors.append(str(path.relative_to(root))+': broken link '+link)
            elif anchor and dest.suffix == '.md':
                headings = re.findall(r'^#{1,6} (.+)$', dest.read_text(encoding='utf-8'), re.M)
                slugs = [re.sub(r'[^\w\- ]', '', h.lower()).replace(' ', '-') for h in headings]
                if anchor not in slugs:
                    errors.append(str(path.relative_to(root))+': missing heading '+link)
        if re.search(r'[\u3400-\u9fff]\n[\u3400-\u9fff]', prose):
            errors.append(str(path.relative_to(root))+': CJK paragraph soft break')
    return errors


if __name__ == '__main__':
    errors = check()
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Documentation checks passed: language pairs, entry points, local links, headings and CJK paragraphs.')
