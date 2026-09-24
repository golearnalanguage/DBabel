import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from docx_review_adapter import W_NS,extract_paragraphs
from export_reviewed_document import export_bundle
from review_model import load_bundle,normalize_decision,save_decisions


def make_docx(path,text):
    texts=[text] if isinstance(text,str) else list(text)
    doc=ET.Element('{%s}document'%W_NS);body=ET.SubElement(doc,'{%s}body'%W_NS)
    for value in texts:
        p=ET.SubElement(body,'{%s}p'%W_NS);r=ET.SubElement(p,'{%s}r'%W_NS);t=ET.SubElement(r,'{%s}t'%W_NS);t.text=value
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('word/document.xml',ET.tostring(doc,encoding='utf-8',xml_declaration=True))


def qa_pass(repo_root,unit,target,glossary):
    return {'summary':{'units_checked':1,'error_count':0,'warning_count':0},'issues':[],'raw':{}}

class EndToEndTests(unittest.TestCase):
    def test_create_review_accept_and_export_verified_docx(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);orig=d/'target.docx';make_docx(orig,'The database is ready.')
            units=d/'units.jsonl';units.write_text(json.dumps({'id':'U0001','source':'数据库已就绪。','target':'The database is ready.','location':'docx:word/document.xml:p=0','source_language':'zh-CN','target_language':'en'},ensure_ascii=False)+'\n')
            audit=d/'audit.json';audit.write_text(json.dumps({'findings':[{'id':'F1','location':'docx:word/document.xml:p=0','original':'database','classification':'GENERIC_DB','decision':'REPLACE','recommendation':'primary database','reason':'Use the project-approved role term.','confidence':'HIGH','text_role':'body','protected':False,'verification_required':False,'evidence_refs':['E1']}],'sources':[{'id':'E1','source_title':'Approved terminology','source_type':'user_supplied_approved_resource','locator':'project://glossary','retrieved_at':'2026-09-24','evidence_state':'CURRENT','source_opened':True,'support_note':'Approved role term','authority_match':'HIGH','context_match':'HIGH','version_match':'NOT_APPLICABLE'}]},ensure_ascii=False))
            bundle=d/'manual.dbreview'
            subprocess.run([sys.executable,str(SCRIPTS/'create_review_session.py'),str(units),'--audit-report',str(audit),'--original',str(orig),'--output',str(bundle)],check=True,capture_output=True,text=True)
            subprocess.run([sys.executable,str(SCRIPTS/'validate_review_bundle.py'),str(bundle),'--repo-root',str(ROOT)],check=True,capture_output=True,text=True)
            data=load_bundle(bundle);u=data['units'][0]
            self.assertEqual(u['suggested_target'],'The primary database is ready.')
            prev=data['decisions'][0];dec=normalize_decision(u,{'status':'ACCEPT_SUGGESTION'},prev);save_decisions(bundle,[dec])
            out=d/'reviewed.docx';receipt=export_bundle(bundle,ROOT,orig,out,qa_runner=qa_pass)
            self.assertEqual(receipt['status'],'VERIFIED')
            self.assertEqual(extract_paragraphs(out)[0]['text'],'The primary database is ready.')
            self.assertTrue(receipt['round_trip']['checks'])

    def test_original_hash_change_blocks_export(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);orig=d/'target.docx';make_docx(orig,'A')
            units=d/'u.jsonl';units.write_text(json.dumps({'id':'U1','source':'甲','target':'A','location':'docx:word/document.xml:p=0'})+'\n');bundle=d/'x.dbreview'
            subprocess.run([sys.executable,str(SCRIPTS/'create_review_session.py'),str(units),'--original',str(orig),'--output',str(bundle)],check=True,capture_output=True,text=True)
            data=load_bundle(bundle);dec=normalize_decision(data['units'][0],{'status':'KEEP_CURRENT'},data['decisions'][0]);save_decisions(bundle,[dec])
            make_docx(orig,'B')
            out=d/'o.docx';receipt=export_bundle(bundle,ROOT,orig,out,qa_runner=qa_pass)
            self.assertEqual(receipt['status'],'BLOCKED')
            self.assertFalse(out.exists())
            self.assertTrue(any('SHA-256' in x for x in receipt['blockers']))

    def test_unequal_docx_alignment_never_silently_truncates(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            src=d/'source.docx'
            tgt=d/'target.docx'
            out=d/'units.jsonl'

            make_docx(src,['A','B'])
            make_docx(tgt,['A'])

            result=subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS/'extract_docx_bilingual_units.py'),
                    str(src),
                    str(tgt),
                    '--output',
                    str(out),
                    '--allow-structural-mismatch',
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode,0)
            self.assertIn(
                'refusing to drop unmatched content',
                result.stderr,
            )
            self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
