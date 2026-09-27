"""Patch selected XML text elements without reserializing surrounding markup.

Expat supplies namespace-aware byte locations. All bytes outside changed text
elements are copied verbatim, including namespace declarations and comments.
"""
import re
from xml.parsers import expat
from xml.sax.saxutils import escape


def text_spans(raw, namespace, local_name='t'):
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')) or b'\x00' in raw:
        raise ValueError('Native XML write-back requires UTF-8 XML.')
    raw.decode('utf-8-sig')
    parser = expat.ParserCreate(namespace_separator='|')
    spans, stack = [], []

    def tag_end(start):
        quote = None
        for i in range(start, len(raw)):
            c = raw[i]
            if quote:
                if c == quote:
                    quote = None
            elif c in (34, 39):
                quote = c
            elif c == 62:
                return i + 1
        raise ValueError('Unterminated XML tag')

    def start(name, attrs):
        begin = parser.CurrentByteIndex
        end = tag_end(begin)
        row = None
        if name == namespace + '|' + local_name:
            row = {'start': begin, 'content': end, 'empty': raw[begin:end].rstrip().endswith(b'/>')}
            spans.append(row)
        stack.append(row)

    def end(name):
        row = stack.pop()
        if row is not None:
            row['close'] = row['content'] if row['empty'] else parser.CurrentByteIndex
            row['end'] = row['content'] if row['empty'] else tag_end(parser.CurrentByteIndex)

    def reject_doctype(*args):
        raise ValueError('DTD declarations are unsupported in native XML write-back.')

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.Parse(raw, True)
    return spans


def patch_xml_text(raw, namespace, replacements):
    spans = text_spans(raw, namespace)
    if any(i < 0 or i >= len(spans) for i in replacements):
        raise ValueError('XML text-node anchor is out of range')
    for i, value in sorted(replacements.items(), reverse=True):
        if any(ord(c) < 32 and c not in '\t\n\r' for c in value):
            raise ValueError('Text contains an XML control character')
        row = spans[i]
        opening = raw[row['start']:row['content']]
        if value.startswith(' ') or value.endswith(' '):
            if re.search(rb'\sxml:space\s*=', opening):
                opening = re.sub(rb'xml:space\s*=\s*([\"\']).*?\1', b'xml:space="preserve"', opening)
            else:
                pos = opening.rfind(b'/>') if row['empty'] else len(opening)-1
                opening = opening[:pos] + b' xml:space="preserve"' + opening[pos:]
        closing = raw[row['close']:row['end']]
        if row['empty']:
            name = re.match(rb'<([^\s/>]+)', opening).group(1)
            opening = opening[:-2] + b'>'
            closing = b'</' + name + b'>'
        content = escape(value).replace('\r', '&#13;').encode('utf-8')
        raw = raw[:row['start']] + opening + content + closing + raw[row['end']:]
    return raw


def markup_skeleton(raw, namespace):
    """Mask only text values and their whitespace attribute for fidelity checks."""
    for row in reversed(text_spans(raw, namespace)):
        opening = raw[row['start']:row['content']]
        opening = re.sub(rb'\s+xml:space\s*=\s*([\"\']).*?\1', b'', opening)
        if row['empty']:
            name = re.match(rb'<([^\s/>]+)', opening).group(1)
            opening = opening[:-2] + b'>'
            closing = b'</' + name + b'>'
        else:
            closing = raw[row['close']:row['end']]
        raw = raw[:row['start']] + opening + b'__TEXT__' + closing + raw[row['end']:]
    return raw
