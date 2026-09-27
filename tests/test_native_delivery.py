"""Verify document structure and review provenance across native deliveries."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from docx_review_adapter import (W_NS, build_anchors, apply_reviewed_docx,
    verify_package_fidelity, extract_paragraphs, DocxExportError)
from review_exchange import create_intake, read_document
from review_model import load_bundle, normalize_decision, save_decisions
from export_reviewed_document import export_bundle
from text_review_adapter import build_text_anchors, apply_reviewed_text
from xml_text_patch import patch_xml_text, markup_skeleton


class NativeDeliveryTests(unittest.TestCase):
    def test_word_namespace_styles_tables_and_package_parts_survive(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td)/'in.docx', Path(td)/'out.docx'
            raw = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<w:document xmlns:w="'+W_NS+'" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
                   'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14">'
                   '<!-- keep exactly --><w:body><w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/></w:tblPr>'
                   '<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p w14:paraId="12345678">'
                   '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t>Alpha</w:t></w:r>'
                   '<w:r><w:t xml:space="preserve"> ready</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                   '<w:p><w:r><w:t>Untouched &amp; stable</w:t></w:r></w:p><w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>').encode()
            with zipfile.ZipFile(source, 'w') as z:
                z.comment = b'archive metadata'
                z.writestr('word/document.xml', raw)
                z.writestr('word/header1.xml', '<w:hdr xmlns:w="'+W_NS+'"><w:p><w:r><w:t>Header</w:t></w:r></w:p></w:hdr>')
                z.writestr('word/media/image1.png', b'image bytes')
                z.writestr('word/styles.xml', b'<styles/>')
            units = [{'id':'U1','location':'docx:word/document.xml:p=0','current_target':'Alpha ready'}]
            apply_reviewed_docx(source, output, units, {'U1':{'status':'USER_EDITED','approved_target':'Beta ready'}}, build_anchors(source, units))
            with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
                self.assertEqual(after.read('word/document.xml'), raw.replace(b'>Alpha<', b'>Beta<'))
                for name in ('word/header1.xml','word/media/image1.png','word/styles.xml'):
                    self.assertEqual(before.read(name), after.read(name))
                self.assertEqual(before.comment, after.comment)
            self.assertTrue(verify_package_fidelity(source, output))

    def test_xml_empty_nodes_escaping_and_space(self):
        raw = ('<w:p xmlns:w="'+W_NS+'"><w:r><w:t/><w:t data="a&gt;b">same</w:t></w:r></w:p>').encode()
        changed = patch_xml_text(raw, W_NS, {0:' A & <B> '})
        self.assertIn(b'xml:space="preserve"> A &amp; &lt;B&gt; </w:t>', changed)
        self.assertEqual(markup_skeleton(raw,W_NS), markup_skeleton(changed,W_NS))

    def test_inline_breaks_are_preserved_and_block_rewrite(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/'in.docx'
            with zipfile.ZipFile(source, 'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="'+W_NS+'"><w:body><w:p><w:r><w:t>A</w:t><w:br/><w:t>B</w:t></w:r></w:p></w:body></w:document>')
            units=[{'id':'U','current_target':'AB','location':'docx:word/document.xml:p=0'}]
            with self.assertRaises(DocxExportError):
                apply_reviewed_docx(source,Path(td)/'out.docx',units,{'U':{'status':'USER_EDITED','approved_target':'CD'}},build_anchors(source,units))

    def test_text_bom_mixed_eol_duplicate_lines_and_unicode_separator(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td)/'in.md', Path(td)/'out.md'
            source.write_bytes(b'\xef\xbb\xbf# Same\r\n\r\n# Same\n'+'A\u2028B\rTail'.encode())
            rows = read_document(source)['segments']
            self.assertEqual(rows[-1]['location'],'line:5')
            units=[{'id':'U','current_target':'# Same','location':'line:3'}]
            apply_reviewed_text(source,output,units,{'U':{'status':'USER_EDITED','approved_target':'# Updated'}},build_text_anchors(source,units))
            self.assertEqual(output.read_bytes(),source.read_bytes().replace(b'# Same\n', b'# Updated\n'))

    def test_intake_checkpoint_handoff_and_collision(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); source=base/'source.txt';source.write_bytes('第一行\r\n第二行\r\n'.encode())
            bundle=base/'review.dbreview'
            create_intake(source,bundle,'zh-CN',['en'])
            data=load_bundle(bundle)
            self.assertEqual(data['units'][0]['current_target'],'第一行')
            self.assertEqual(data['decisions'][0]['status'],'UNREVIEWED')
            first=normalize_decision(data['units'][0],{'status':'USER_EDITED','approved_target':'First line'},data['decisions'][0])
            save_decisions(bundle,[first,data['decisions'][1]])
            output=base/'reviewed.txt'
            receipt=export_bundle(bundle,ROOT,source,output,export_mode='CHECKPOINT',qa_runner=lambda *a:{'issues':[]})
            self.assertEqual(receipt['status'],'VERIFIED',receipt)
            self.assertEqual(output.read_bytes(),'First line\r\n第二行\r\n'.encode())
            handoff=json.loads(Path(str(output)+'.handoff.json').read_text())
            self.assertEqual(handoff['agent_review_status'],'NOT_RUN')
            self.assertEqual([r['export_action'] for r in handoff['units']],['CHANGED','NOT_EXPORTED'])
            self.assertIn('第二行',Path(str(output)+'.handoff.md').read_text())
            self.assertIn('class="pair"',Path(str(output)+'.bilingual.html').read_text())
            before=output.read_bytes()
            with self.assertRaises(ValueError):
                export_bundle(bundle,ROOT,source,output,qa_runner=lambda *a:{'issues':[]})
            self.assertEqual(output.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
