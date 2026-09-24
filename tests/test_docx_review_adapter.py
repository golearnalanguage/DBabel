import sys,tempfile,unittest,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from docx_review_adapter import build_anchors,apply_reviewed_docx,extract_paragraphs,round_trip_verify,verify_non_target_text_unchanged,DocxExportError,W_NS,W14_PARA_ID

def make_docx(path, paragraphs, para_ids=None):
    ns=W_NS
    doc=ET.Element('{%s}document'%ns);body=ET.SubElement(doc,'{%s}body'%ns)
    for index,runs in enumerate(paragraphs):
        p=ET.SubElement(body,'{%s}p'%ns)
        if para_ids:
            p.set(W14_PARA_ID,para_ids[index])
        for text,bold in runs:
            r=ET.SubElement(p,'{%s}r'%ns)
            if bold:
                rp=ET.SubElement(r,'{%s}rPr'%ns);ET.SubElement(rp,'{%s}b'%ns)
            t=ET.SubElement(r,'{%s}t'%ns);t.text=text
    data=ET.tostring(doc,encoding='utf-8',xml_declaration=True)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        z.writestr('word/document.xml',data)
        z.writestr('word/media/keep.bin',b'unchanged')

class DocxAdapterTests(unittest.TestCase):
    def test_safe_patch_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            orig=Path(td)/'in.docx';out=Path(td)/'out.docx'
            make_docx(orig,[[('The ',False),('database',True),(' is ready.',False)],[('Do not change me.',False)]])
            units=[{'id':'U1','location':'docx:word/document.xml:p=0','current_target':'The database is ready.'}]
            anchors=build_anchors(orig,units)
            self.assertEqual(anchors['U1']['status'],'RESOLVED')
            decisions={'U1':{'status':'USER_EDITED','approved_target':'The primary database is ready.'}}
            changed=apply_reviewed_docx(orig,out,units,decisions,anchors)
            self.assertEqual(changed,['U1'])
            self.assertEqual(extract_paragraphs(out)[0]['text'],'The primary database is ready.')
            self.assertEqual(extract_paragraphs(out)[1]['text'],'Do not change me.')
            self.assertTrue(round_trip_verify(out,units,decisions,anchors))
            self.assertTrue(verify_non_target_text_unchanged(orig,out,anchors,decisions,units))
            with zipfile.ZipFile(out) as z:self.assertEqual(z.read('word/media/keep.bin'),b'unchanged')

    def test_ambiguous_anchor_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            orig=Path(td)/'in.docx';out=Path(td)/'out.docx';make_docx(orig,[[('Same',False)],[('Same',False)]])
            units=[{'id':'U1','location':'unknown','current_target':'Same'}];anchors=build_anchors(orig,units)
            self.assertEqual(anchors['U1']['status'],'AMBIGUOUS')
            with self.assertRaises(DocxExportError):apply_reviewed_docx(orig,out,units,{'U1':{'status':'USER_EDITED','approved_target':'Changed'}},anchors)

    def test_anchor_prefers_word_para_id(self):
        with tempfile.TemporaryDirectory() as td:
            orig=Path(td)/'in.docx'
            out=Path(td)/'out.docx'

            make_docx(
                orig,
                [
                    [('First paragraph.',False)],
                    [('Second paragraph.',False)],
                ],
                para_ids=[
                    '00112233',
                    '44556677',
                ],
            )

            units=[
                {
                    'id':'U1',
                    'location':'docx:word/document.xml:p=0',
                    'current_target':'First paragraph.',
                }
            ]

            anchors=build_anchors(orig,units)

            self.assertEqual(
                anchors['U1']['para_id'],
                '00112233',
            )

            # Make the fallback ordinal deliberately wrong.
            # Export must still resolve the paragraph through w14:paraId.
            anchors['U1']['paragraph_ordinal']=1

            decisions={
                'U1':{
                    'status':'USER_EDITED',
                    'approved_target':'Updated first paragraph.',
                }
            }

            apply_reviewed_docx(
                orig,
                out,
                units,
                decisions,
                anchors,
            )

            rows=extract_paragraphs(out)

            self.assertEqual(
                rows[0]['text'],
                'Updated first paragraph.',
            )
            self.assertEqual(
                rows[1]['text'],
                'Second paragraph.',
            )

            self.assertTrue(
                round_trip_verify(
                    out,
                    units,
                    decisions,
                    anchors,
                )
            )

            self.assertTrue(
                verify_non_target_text_unchanged(
                    orig,
                    out,
                    anchors,
                    decisions,
                    units,
                )
            )

    def test_missing_word_para_id_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            orig=Path(td)/'in.docx'
            out=Path(td)/'out.docx'

            make_docx(
                orig,
                [[('Stable paragraph.',False)]],
                para_ids=['ABCDEF12'],
            )

            units=[
                {
                    'id':'U1',
                    'location':'docx:word/document.xml:p=0',
                    'current_target':'Stable paragraph.',
                }
            ]

            anchors=build_anchors(orig,units)

            self.assertEqual(
                anchors['U1']['para_id'],
                'ABCDEF12',
            )

            # Simulate structural drift after the anchor was created.
            make_docx(
                orig,
                [[('Stable paragraph.',False)]],
            )

            decisions={
                'U1':{
                    'status':'USER_EDITED',
                    'approved_target':'Updated paragraph.',
                }
            }

            with self.assertRaisesRegex(
                DocxExportError,
                'w14:paraId disappeared',
            ):
                apply_reviewed_docx(
                    orig,
                    out,
                    units,
                    decisions,
                    anchors,
                )

    def test_never_overwrite_original(self):
        with tempfile.TemporaryDirectory() as td:
            orig=Path(td)/'in.docx';make_docx(orig,[[('A',False)]])
            units=[{'id':'U1','location':'docx:word/document.xml:p=0','current_target':'A'}];anchors=build_anchors(orig,units)
            with self.assertRaises(DocxExportError):apply_reviewed_docx(orig,orig,units,{'U1':{'status':'KEEP_CURRENT','approved_target':'A'}},anchors)

if __name__=='__main__':unittest.main()
