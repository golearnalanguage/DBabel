"""Document intake, scoped glossary scoring and review-result interchange.

Result exports contain reviewed and pending rows with explicit status; they do not
rewrite source layouts. Native DOCX delivery remains in export_reviewed_document.
"""
from __future__ import annotations
import base64
import csv
import hashlib
import html
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from html.parser import HTMLParser

from detect_document_format import probe_document
from glossary_io import load_glossary, validate_glossary, applicable_entries, targets_for_unit, term_occurrences
from review_model import final_target_for, utc_now, write_json, sha256_json

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 16 * 1024 * 1024
RESULT_FORMATS = {'json': 'application/json', 'csv': 'text/csv', 'tsv': 'text/tab-separated-values',
                  'md': 'text/markdown', 'html': 'text/html', 'txt': 'text/plain'}


def upload_file(payload, directory):
    if not isinstance(payload, dict):
        raise ValueError('Select a document to upload.')
    name = str(payload.get('name', ''))
    if not name or Path(name).name != name or '\\' in name or len(name) > 180:
        raise ValueError('Upload requires a plain filename.')
    try:
        content = base64.b64decode(payload.get('content_base64', ''), validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid base64 upload.') from exc
    if not content or len(content) > MAX_FILE:
        raise ValueError('Document must contain 1 byte to 16 MiB.')
    path = Path(directory) / name
    path.write_bytes(content)
    return path


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'template'}: self.hidden += 1
        if tag in {'p', 'div', 'li', 'br', 'tr', 'h1', 'h2', 'h3'}: self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'template'}: self.hidden = max(0, self.hidden - 1)
        if tag in {'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3'}: self.parts.append('\n')
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def _read_document(path):
    """Extract located text in a declared, bounded scope; return the probe too."""
    path = Path(path)
    if path.stat().st_size > MAX_FILE: raise ValueError('Document exceeds 16 MiB.')
    probe = probe_document(path)
    if probe['status'] in {'EXTENSION_ONLY', 'UNKNOWN'}:
        raise ValueError('File content does not confirm a supported document format.')
    fmt = probe['effective_format']
    # Text formats overlap (Markdown may start with HTML, TSV probes as CSV).
    # Select a declared text grammar only after the probe confirms text content;
    # the parser below then validates UTF-8 and the complete declared structure.
    suffix = path.suffix.lower().lstrip('.')
    if fmt in {'txt', 'md', 'csv', 'xml', 'html', 'json'} and suffix in {'txt', 'md', 'csv', 'tsv', 'json', 'jsonl', 'html'}:
        fmt = suffix
    rows = []; limitations = []
    def add(location, text):
        if str(text).strip(): rows.append({'location': location, 'text': str(text)})
    if fmt in {'docx', 'xlsx', 'pptx'}:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > 10000 or sum(i.file_size for i in infos) > 64 * 1024 * 1024:
                raise ValueError('Office package exceeds extraction limits.')
            def xml(name):
                raw = z.read(name)
                if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                    raise ValueError('XML entity declarations are unsupported.')
                return ET.fromstring(raw)
            if fmt == 'docx':
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                for n, p in enumerate(xml('word/document.xml').findall('.//w:body//w:p', ns), 1):
                    add('body:p:{}'.format(n), ''.join(t.text or '' for t in p.findall('.//w:t', ns)))
                limitations = ['Body paragraphs and table paragraphs only; headers, footnotes, comments, drawings and revision semantics require Agent extraction.']
            elif fmt == 'pptx':
                ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
                names = sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)), key=lambda n: int(re.search(r'(\d+)\.xml', n)[1]))
                for name in names:
                    for n, p in enumerate(xml(name).findall('.//a:p', ns), 1):
                        add('{}:p:{}'.format(name, n), ''.join(t.text or '' for t in p.findall('.//a:t', ns)))
                limitations = ['Slide XML order; notes, charts, SmartArt, masters and image text are not extracted.']
            else:
                ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                strings = []
                if 'xl/sharedStrings.xml' in z.namelist():
                    strings = [''.join(t.text or '' for t in v.findall('.//s:t', ns)) for v in xml('xl/sharedStrings.xml')]
                for name in sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)):
                    for cell in xml(name).findall('.//s:c', ns):
                        if cell.find('s:f', ns) is not None: continue
                        value = cell.findtext('s:v', '', ns)
                        if cell.get('t') == 's': value = strings[int(value)]
                        if cell.get('t') == 'inlineStr': value = ''.join(t.text or '' for t in cell.findall('.//s:t', ns))
                        add('{}:{}'.format(name, cell.get('r')), value)
                limitations = ['Stored non-formula cells, including hidden sheets; formulas, formatting, charts and comments are not extracted.']
    elif fmt == 'pdf':
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError('PDF text intake needs pypdf: python -m pip install pypdf. Scans require OCR before upload.') from exc
        reader = PdfReader(path)
        if reader.is_encrypted: raise ValueError('Decrypt the PDF before upload.')
        for n, page in enumerate(reader.pages, 1): add('page:{}'.format(n), page.extract_text() or '')
        limitations = ['Text layer only; reading order, tables and image text require inspection. No OCR or PDF layout write-back.']
    elif fmt in {'txt', 'md', 'markdown', 'csv', 'tsv', 'json', 'jsonl', 'html', 'xml'}:
        text = path.read_text(encoding='utf-8-sig')
        if fmt in {'csv', 'tsv'}:
            for r, values in enumerate(csv.reader(io.StringIO(text), delimiter='\t' if fmt == 'tsv' else ','), 1):
                for c, value in enumerate(values, 1): add('row:{}:col:{}'.format(r, c), value)
            limitations = ['Every non-empty cell, including headers; column roles require review.']
        elif fmt in {'json', 'jsonl'}:
            def walk(value, loc):
                if isinstance(value, str): add(loc, value)
                elif isinstance(value, dict):
                    for key, item in value.items(): walk(item, loc + '/' + str(key).replace('~', '~0').replace('/', '~1'))
                elif isinstance(value, list):
                    for n, item in enumerate(value): walk(item, loc + '/' + str(n))
            if fmt == 'jsonl':
                for n, line in enumerate(text.splitlines(), 1):
                    if line.strip(): walk(json.loads(line), 'line:{}'.format(n))
            else: walk(json.loads(text), '')
            limitations = ['String values only; keys, numbers and booleans are preserved outside review.']
        elif fmt == 'html':
            parser = VisibleHTML(); parser.feed(text)
            for n, line in enumerate(''.join(parser.parts).splitlines(), 1): add('text-block:{}'.format(n), line.strip())
            limitations = ['Visible text nodes only; attributes, layout, script-generated content and CSS visibility require Agent inspection.']
        elif fmt == 'xml':
            raise ValueError('XML is recognized. Use an Agent to select translatable elements and supply aligned units JSON.')
        else:
            for n, line in enumerate(text.splitlines(), 1): add('line:{}'.format(n), line)
            limitations = ['Non-empty lines; Markdown markup and code remain in the text and need protected-token review.']
    else:
        raise ValueError('Recognized format {} has no upload extractor. Convert a copy or supply aligned units JSON.'.format(fmt))
    if not rows: raise ValueError('No text extracted. For scans, run OCR and inspect its output first.')
    if len(rows) > 20000: raise ValueError('More than 20,000 segments; split the document before intake.')
    return {'filename': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'format': fmt, 'probe': probe, 'segments': rows, 'limitations': limitations,
            'coverage': 'EXTRACTED_SCOPE', 'native_export': fmt == 'docx'}


def read_document(path):
    try:
        return _read_document(path)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError) as exc:
        raise ValueError('Malformed document structure: {}'.format(exc)) from exc


def create_intake(source, output, source_language, target_languages, target=None, alignment_confirmed=False):
    source_info = read_document(source)
    target_info = read_document(target) if target else None
    languages = list(dict.fromkeys(x.strip() for x in target_languages if x.strip()))
    if not source_language.strip() or not languages or any(not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*', x) for x in [source_language] + languages):
        raise ValueError('Use explicit language tags, for example zh-CN, en, ja.')
    if target and (len(languages) != 1 or len(source_info['segments']) != len(target_info['segments'])):
        raise ValueError('A target document requires one target language and equal segment counts; align other documents with an Agent.')
    units = []
    for lang in languages:
        for n, row in enumerate(source_info['segments'], 1):
            units.append({'id': 'U{:05d}_{}'.format(n, lang), 'location': row['location'],
                          'source': row['text'], 'target': target_info['segments'][n-1]['text'] if target else '',
                          'source_language': source_language, 'target_language': lang,
                          'alignment': 'ALIGNED' if target and alignment_confirmed else 'UNALIGNED'})
    if len(units) > 20000: raise ValueError('More than 20,000 language/segment pairs; split this intake.')
    output = Path(output)
    with tempfile.TemporaryDirectory() as td:
        units_path = Path(td) / 'units.json'; write_json(units_path, units)
        command = [sys.executable, str(ROOT/'scripts/create_review_session.py'), str(units_path),
                   '--output', str(output), '--title', source_info['filename'], '--mode', 'BILINGUAL_REVIEW' if target else 'TRANSLATE']
        if target: command += ['--original', str(target)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode: raise ValueError(result.stderr.strip())
    if not target:
        session = json.loads((output/'session.json').read_text(encoding='utf-8'))
        session['original'] = {key: source_info[key] for key in ('filename', 'format', 'sha256')}
        session['source_document'] = source_info['filename']
        write_json(output/'session.json', session)
        (output/'original.sha256').write_text(source_info['sha256']+'  '+source_info['filename']+'\n', encoding='utf-8')
    # Keep source inputs and extraction report inside the new session for later Agent work.
    inputs = output/'inputs'; inputs.mkdir()
    (inputs/('source'+Path(source).suffix)).write_bytes(Path(source).read_bytes())
    if target: (inputs/('target'+Path(target).suffix)).write_bytes(Path(target).read_bytes())
    write_json(output/'intake.json', {'source': source_info, 'target': target_info, 'languages': languages,
                                    'alignment_confirmed': bool(target and alignment_confirmed)})
    return output


def glossary_score(data, path):
    glossary = load_glossary(path)
    errors = validate_glossary(glossary)
    if errors: raise ValueError('\n'.join(errors))
    checks = []
    skipped = 0
    for unit in data['units']:
        if not unit.get('source_language') or not unit.get('target_language'):
            skipped += 1; continue
        target = final_target_for(unit, data['decisions_by_id'][unit['id']])
        for entry in applicable_entries(glossary, unit):
            terms = targets_for_unit(entry, unit)
            accepted = [t['term'] for t in terms if t['status'] in {'PREFERRED', 'ADMITTED'}]
            forbidden = [t['term'] for t in terms if t['status'] == 'FORBIDDEN']
            if entry['behavior'] == 'PROTECT': accepted = [entry['source']['term']]
            if not accepted and not forbidden: continue
            passed = (not accepted or any(term_occurrences(target, t, entry) for t in accepted)) and not any(term_occurrences(target, t, entry) for t in forbidden)
            checks.append({'unit_id': unit['id'], 'entry_id': entry['id'], 'target_language': unit['target_language'],
                           'source_term': entry['source']['term'], 'accepted': accepted, 'forbidden': forbidden,
                           'passed': bool(passed)})
    passed = sum(c['passed'] for c in checks)
    return {'entries': len(glossary['entries']), 'applicable_checks': len(checks), 'passed_checks': passed,
            'score': round(100*passed/len(checks), 1) if checks else None, 'skipped_missing_languages': skipped,
            'definition': 'Passed applicable approved term/unit checks ÷ all applicable approved term/unit checks × 100; lexical compliance, not translation quality.',
            'checks': checks}


def result_snapshot(data):
    rows = []
    for unit in data['units']:
        d = data['decisions_by_id'][unit['id']]
        rows.append({'id': unit['id'], 'location': unit['location'], 'source_language': unit.get('source_language', ''),
                     'target_language': unit.get('target_language', ''), 'source': unit['source'],
                     'target': final_target_for(unit, d), 'suggested_target': unit.get('suggested_target', ''), 'suggestion_reason': unit.get('suggestion_reason', ''),
                     'status': d['status'], 'revision': d['revision'], 'reviewer_note': d.get('reviewer_note', ''),
                     'qa_status': d['recheck']['status']})
    return {'format_version': '1.0', 'report_type': 'REVIEW_SNAPSHOT', 'created_at': utc_now(),
            'session_id': data['session']['session_id'], 'original': data['session']['original'],
            'delivery_state': 'REVIEW_SNAPSHOT', 'agent_review_status': 'NOT_RUN',
            'decision_digest': sha256_json(sorted(data['decisions'], key=lambda d: d['unit_id'])),
            'units_sha256': sha256_json(rows),
            'issue_provenance': 'Session intake findings; consult per-unit recheck for the current QA state.',
            'units': rows, 'issues': data['issues'], 'evidence': data['evidence'], 'decisions': data['decisions']}


def render_result(data, fmt):
    if not isinstance(fmt, str) or fmt not in RESULT_FORMATS: raise ValueError('Unsupported result format.')
    snapshot = result_snapshot(data)
    rows = snapshot['units']
    if fmt == 'json': return json.dumps(snapshot, ensure_ascii=False, indent=2)+'\n'
    if fmt in {'csv', 'tsv'}:
        stream = io.StringIO(newline=''); writer = csv.writer(stream, delimiter='\t' if fmt == 'tsv' else ',')
        keys = list(rows[0]) if rows else ['id', 'source', 'target', 'status']
        writer.writerow(keys)
        for row in rows:
            # Spreadsheet exports treat every cell as text, including hostile formulas.
            writer.writerow([("'"+str(row[k])) if str(row[k]).lstrip().startswith(('=', '+', '-', '@')) or str(row[k]).startswith(('\t','\r','\n')) else row[k] for k in keys])
        return stream.getvalue()
    title = 'DBabel review snapshot / 审核快照'
    if fmt == 'html':
        parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>'+title+'</title><body><h1>'+title+'</h1>', '<p>'+html.escape(snapshot['session_id'])+'</p>']
        for row in rows:
            parts.append('<section><h2>'+html.escape(row['id']+' · '+row['status'])+'</h2><p>'+html.escape(row['location'])+'</p><h3>'+html.escape(row['source_language'])+'</h3><pre>'+html.escape(row['source'])+'</pre><h3>'+html.escape(row['target_language'])+'</h3><pre>'+html.escape(row['target'])+'</pre><p>QA: '+html.escape(row['qa_status'])+'</p></section>')
        return ''.join(parts)+'</body></html>'
    literal = lambda value: '\n'.join('    '+line for line in str(value).splitlines())
    parts = [title, literal(snapshot['session_id']), 'REVIEW_SNAPSHOT · Agent: NOT_RUN', '']
    for row in rows:
        # Indentation makes user content literal in Markdown instead of executable HTML.
        parts += [literal(row['id']+' · '+row['status']+' · QA '+row['qa_status']), literal(row['location']),
                  literal('['+row['source_language']+']'), '\n'.join('    '+x for x in row['source'].splitlines()),
                  literal('['+row['target_language']+']'), '\n'.join('    '+x for x in row['target'].splitlines()), '']
    return '\n'.join(parts)+'\n'
