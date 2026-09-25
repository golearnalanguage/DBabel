#!/usr/bin/env python3
"""Check local Markdown links, heading anchors and unintended CJK line breaks."""
from pathlib import Path
import re,json
from urllib.parse import unquote
R=Path(__file__).resolve().parents[1];rows=[];bad=[]
for p in sorted(R.rglob('*.md')):
 if any(part.startswith('.') for part in p.relative_to(R).parts):continue
 s=p.read_text();prose=re.sub(r'^```[^\n]*\n.*?^```[^\n]*$','',s,flags=re.M|re.S)
 problems=[]
 for target in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)',prose):
  if re.match(r'^[a-zA-Z]+:',target):continue
  path,_,anchor=unquote(target.strip('<>')).partition('#');dest=(p.parent/path).resolve() if path else p
  if not dest.exists():problems.append('Missing local link: '+target)
  elif anchor and dest.suffix=='.md':
   headings=re.findall(r'^#{1,6} (.+)$',dest.read_text(),re.M)
   slugs=[re.sub(r'[^\w\- ]','',x.lower()).replace(' ','-') for x in headings]
   if anchor not in slugs:problems.append('Missing heading: '+target)
 if re.search(r'[\u3400-\u9fff]\n[\u3400-\u9fff]',prose):problems.append('CJK paragraph soft break')
 rows.append({'file':str(p.relative_to(R)),'problems':problems})
 bad.extend([str(p.relative_to(R))+': '+x for x in problems])

print('\n'.join(bad) or f'{len(rows)} Markdown files: local links, headings and CJK paragraph breaks passed')

raise SystemExit(1 if bad else 0)
