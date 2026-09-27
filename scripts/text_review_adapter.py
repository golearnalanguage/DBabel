"""Located UTF-8 line edits; copy BOM, blank lines and original line endings."""
import hashlib
import re


def read_lines(path):
    raw = path.read_bytes()
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    text = raw[len(bom):].decode('utf-8')
    # splitlines also treats Unicode separators as breaks; only file EOLs count.
    lines = re.findall(r'[^\r\n]*(?:\r\n|\r|\n|$)', text)
    if lines and lines[-1] == '':
        lines.pop()
    return bom, lines


def build_text_anchors(path, units):
    _, lines = read_lines(path)
    texts = [line.rstrip('\r\n') for line in lines]
    anchors = {}
    for unit in units:
        current = unit['current_target']
        hint = re.fullmatch(r'(?:text:)?line:(\d+)', unit.get('location', ''))
        candidates = [i for i, text in enumerate(texts) if text == current]
        if hint and 0 < int(hint[1]) <= len(texts) and texts[int(hint[1])-1] == current:
            candidates = [int(hint[1])-1]
        row = {'id': 'A_'+unit['id'], 'unit_id': unit['id'], 'original_text': current,
               'status': 'RESOLVED' if len(candidates) == 1 else 'UNRESOLVED'}
        if row['status'] == 'RESOLVED':
            row.update(part='text', paragraph_ordinal=candidates[0],
                       original_text_sha256=hashlib.sha256(current.encode()).hexdigest())
        else:
            row['reason'] = 'Text line does not resolve uniquely'
        anchors[unit['id']] = row
    return anchors


def apply_reviewed_text(original, output, units, decisions, anchors):
    bom, lines = read_lines(original)
    changed, seen = [], set()
    for u in units:
        d = decisions[u['id']]
        if d['status'] not in {'ACCEPT_SUGGESTION', 'KEEP_CURRENT', 'USER_EDITED', 'WAIVED'}:
            raise ValueError('Text unit is not export-approved: ' + u['id'])
        new, old = d['approved_target'], u['current_target']
        if new == old:
            continue
        a = anchors.get(u['id'], {})
        if a.get('status') != 'RESOLVED':
            raise ValueError('Unresolved text line: ' + u['id'])
        i = a['paragraph_ordinal']
        if i in seen or not 0 <= i < len(lines) or lines[i].rstrip('\r\n') != old:
            raise ValueError('Overlapping or stale text line: ' + u['id'])
        if '\r' in new or '\n' in new:
            raise ValueError('Text-only export preserves line boundaries; do not insert newlines')
        seen.add(i)
        lines[i] = new + lines[i][len(old):]
        changed.append(u['id'])
    expected = bom + ''.join(lines).encode('utf-8')
    with output.open('xb') as stream:
        stream.write(expected)
    if output.read_bytes() != expected:
        raise ValueError('Text export round-trip mismatch')
    return changed
