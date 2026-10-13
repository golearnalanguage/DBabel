"""Independent round-trip invariants over generated synthetic native documents."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET
import zipfile

from hypothesis import given, settings, strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from docx_review_adapter import W_NS, apply_reviewed_docx, build_anchors
from test_docx_review_adapter import make_docx
from text_review_adapter import apply_reviewed_text, build_text_anchors
from xlsx_review_adapter import apply_reviewed_xlsx, build_anchors as xlsx_anchors
from review_model import default_decision, normalize_decision

TEXT = st.text(alphabet=list("Abc数据库éΩ🙂&<>\"' \u2028"), max_size=40)
RUN_SETTINGS = settings(max_examples=80, deadline=None, derandomize=True, database=None)


class NativeProperties(unittest.TestCase):
    @RUN_SETTINGS
    @given(data=st.data(), old=TEXT, replacement=TEXT)
    def test_docx_duplicate_paragraphs_only_change_the_approved_anchor(self, data, old, replacement):
        old, replacement = "Source " + old, "Target " + replacement
        cuts = sorted(data.draw(st.lists(st.integers(0, len(old)), max_size=8)))
        bounds = [0] + cuts + [len(old)]
        runs = [(old[a:b], index % 2 == 0) for index, (a, b) in enumerate(zip(bounds, bounds[1:]))]
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "in.docx", Path(directory) / "out.docx"
            make_docx(source, [runs, runs, runs], para_ids=["00112233", "44556677", "8899AABB"])
            original_bytes = source.read_bytes()
            units = [{"id": "U", "location": "docx:word/document.xml:p=1", "current_target": old}]
            decisions = {"U": {"status": "USER_EDITED", "approved_target": replacement}}
            apply_reviewed_docx(source, output, units, decisions, build_anchors(source, units))
            self.assertEqual(source.read_bytes(), original_bytes)
            with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
                self.assertEqual(before.namelist(), after.namelist())
                for name in before.namelist():
                    if name != "word/document.xml":
                        self.assertEqual(before.read(name), after.read(name))
                original = ET.fromstring(before.read("word/document.xml"))
                changed = ET.fromstring(after.read("word/document.xml"))
                paragraphs = changed.findall(".//{%s}p" % W_NS)
                actual = ["".join(p.itertext()) for p in paragraphs]
                self.assertEqual(actual, [old, replacement, old])
                self.assertEqual(ET.tostring(original.findall(".//{%s}p" % W_NS)[0]), ET.tostring(paragraphs[0]))
                self.assertEqual(ET.tostring(original.findall(".//{%s}p" % W_NS)[2]), ET.tostring(paragraphs[2]))
                self.assertEqual(len(original.findall(".//{%s}b" % W_NS)), len(changed.findall(".//{%s}b" % W_NS)))

    @RUN_SETTINGS
    @given(old=TEXT, replacement=TEXT, bom=st.booleans(), endings=st.lists(st.sampled_from(["\n", "\r", "\r\n"]), min_size=3, max_size=3))
    def test_text_bytes_preserve_bom_mixed_endings_and_duplicate_lines(self, old, replacement, bom, endings):
        old, replacement = "Source " + old, "Target " + replacement
        prefix = b"\xef\xbb\xbf" if bom else b""
        # A blank LF after a CR would merge into one CRLF delimiter, so the
        # blank physical line uses CRLF while other rows vary independently.
        endings = [endings[0], "\r\n", endings[1], endings[2]]
        rows = [old, "", old, "Untouched\u2028tail"]
        raw = prefix + "".join(text + eol for text, eol in zip(rows, endings)).encode()
        expected_rows = [old, "", replacement, "Untouched\u2028tail"]
        expected = prefix + "".join(text + eol for text, eol in zip(expected_rows, endings)).encode()
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "in.txt", Path(directory) / "out.txt"
            source.write_bytes(raw)
            units = [{"id": "U", "location": "line:3", "current_target": old}]
            apply_reviewed_text(source, output, units, {"U": {"status": "USER_EDITED", "approved_target": replacement}}, build_text_anchors(source, units))
            self.assertEqual(output.read_bytes(), expected)
            self.assertEqual(source.read_bytes(), raw)
            with self.assertRaises(FileExistsError):
                apply_reviewed_text(source, output, units, {"U": {"status": "USER_EDITED", "approved_target": replacement}}, build_text_anchors(source, units))
            self.assertEqual(output.read_bytes(), expected)

    @RUN_SETTINGS
    @given(replacement=TEXT)
    def test_xlsx_formula_and_package_parts_survive_an_approved_cell_edit(self, replacement):
        replacement = "Target " + replacement
        namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        formula = '<c r="B1"><f>SUM(1,2)</f><v>3</v></c>'
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "in.xlsx", Path(directory) / "out.xlsx"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="' + namespace + '"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Source</t></is></c>' + formula + '</row></sheetData></worksheet>')
                archive.writestr("xl/workbook.xml", '<workbook xmlns="' + namespace + '"><sheets><sheet name="Keep" sheetId="1"/></sheets></workbook>')
                archive.writestr("xl/styles.xml", b"synthetic unchanged styles")
                archive.writestr("xl/media/image1.bin", b"synthetic unchanged media")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            units = [{"id": "U", "location": "xl/worksheets/sheet1.xml:A1", "current_target": "Source"}]
            apply_reviewed_xlsx(source, output, units, {"U": {"status": "USER_EDITED", "approved_target": replacement}}, xlsx_anchors(source, units))
            with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
                self.assertEqual(before.namelist(), after.namelist())
                for name in before.namelist():
                    if name != "xl/worksheets/sheet1.xml":
                        self.assertEqual(before.read(name), after.read(name))
                payload = after.read("xl/worksheets/sheet1.xml")
                self.assertIn(formula.encode(), payload)
                cell = ET.fromstring(payload).find(".//{%s}c[@r='A1']" % namespace)
                self.assertEqual("".join(cell.itertext()), replacement)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)

    @RUN_SETTINGS
    @given(target=TEXT)
    def test_a_material_human_edit_invalidates_prior_qa(self, target):
        unit = {"id": "U", "current_target": "Current", "suggested_target": "Suggested"}
        accepted = normalize_decision(unit, {"status": "ACCEPT_SUGGESTION"}, default_decision("U"))
        prior_qa = {"status": "PASSED", "error_count": 0, "warning_count": 0, "issue_fingerprints": []}
        accepted["recheck"] = prior_qa
        edited = normalize_decision(unit, {"status": "USER_EDITED", "approved_target": "Edited " + target, "recheck": prior_qa}, accepted)
        self.assertEqual(edited["approved_target"], "Edited " + target)
        self.assertEqual(edited["revision"], accepted["revision"] + 1)
        self.assertEqual(edited["recheck"]["status"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
