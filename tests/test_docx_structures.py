import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from docx_review_adapter import (
    W_NS,
    build_anchors,
    extract_paragraphs,
)


def write_docx(path, body):
    document = ET.Element(
        "{%s}document" % W_NS
    )

    document.append(body)

    with zipfile.ZipFile(
        path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<Types xmlns="http://schemas.openxmlformats.org/'
                'package/2006/content-types">'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.'
                'wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
        )

        archive.writestr(
            "word/document.xml",
            ET.tostring(
                document,
                encoding="utf-8",
                xml_declaration=True,
            ),
        )


def add_text(parent, value):
    run = ET.SubElement(
        parent,
        "{%s}r" % W_NS,
    )

    text = ET.SubElement(
        run,
        "{%s}t" % W_NS,
    )

    text.text = value


class DocxStructureTests(unittest.TestCase):
    def test_table_hyperlink_and_content_control_are_extractable(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "structures.docx"

            body = ET.Element(
                "{%s}body" % W_NS
            )

            p1 = ET.SubElement(
                body,
                "{%s}p" % W_NS,
            )

            hyperlink = ET.SubElement(
                p1,
                "{%s}hyperlink" % W_NS,
            )

            add_text(
                hyperlink,
                "Linked text",
            )

            table = ET.SubElement(
                body,
                "{%s}tbl" % W_NS,
            )

            row = ET.SubElement(
                table,
                "{%s}tr" % W_NS,
            )

            cell = ET.SubElement(
                row,
                "{%s}tc" % W_NS,
            )

            p2 = ET.SubElement(
                cell,
                "{%s}p" % W_NS,
            )

            add_text(
                p2,
                "Table cell",
            )

            sdt = ET.SubElement(
                body,
                "{%s}sdt" % W_NS,
            )

            content = ET.SubElement(
                sdt,
                "{%s}sdtContent" % W_NS,
            )

            p3 = ET.SubElement(
                content,
                "{%s}p" % W_NS,
            )

            add_text(
                p3,
                "Controlled text",
            )

            write_docx(
                path,
                body,
            )

            rows = extract_paragraphs(path)

            self.assertEqual(
                [row["text"] for row in rows],
                [
                    "Linked text",
                    "Table cell",
                    "Controlled text",
                ],
            )

            for row in rows:
                self.assertEqual(
                    row["writeback_blockers"],
                    [],
                )

    def test_field_code_paragraph_blocks_native_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "field.docx"

            body = ET.Element(
                "{%s}body" % W_NS
            )

            paragraph = ET.SubElement(
                body,
                "{%s}p" % W_NS,
            )

            begin_run = ET.SubElement(
                paragraph,
                "{%s}r" % W_NS,
            )

            fld_begin = ET.SubElement(
                begin_run,
                "{%s}fldChar" % W_NS,
            )

            fld_begin.set(
                "{%s}fldCharType" % W_NS,
                "begin",
            )

            instruction_run = ET.SubElement(
                paragraph,
                "{%s}r" % W_NS,
            )

            instruction = ET.SubElement(
                instruction_run,
                "{%s}instrText" % W_NS,
            )

            instruction.text = " PAGE "

            separate_run = ET.SubElement(
                paragraph,
                "{%s}r" % W_NS,
            )

            fld_sep = ET.SubElement(
                separate_run,
                "{%s}fldChar" % W_NS,
            )

            fld_sep.set(
                "{%s}fldCharType" % W_NS,
                "separate",
            )

            add_text(
                paragraph,
                "42",
            )

            end_run = ET.SubElement(
                paragraph,
                "{%s}r" % W_NS,
            )

            fld_end = ET.SubElement(
                end_run,
                "{%s}fldChar" % W_NS,
            )

            fld_end.set(
                "{%s}fldCharType" % W_NS,
                "end",
            )

            write_docx(
                path,
                body,
            )

            rows = extract_paragraphs(path)

            self.assertEqual(
                rows[0]["text"],
                "42",
            )

            self.assertIn(
                "FIELD_CODE",
                rows[0]["writeback_blockers"],
            )

            units = [
                {
                    "id": "U1",
                    "location": "docx:word/document.xml:p=0",
                    "current_target": "42",
                }
            ]

            anchors = build_anchors(
                path,
                units,
            )

            self.assertEqual(
                anchors["U1"]["status"],
                "BLOCKED",
            )

            self.assertIn(
                "FIELD_CODE",
                anchors["U1"]["writeback_blockers"],
            )

    def test_tracked_change_paragraph_blocks_native_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tracked.docx"

            body = ET.Element(
                "{%s}body" % W_NS
            )

            paragraph = ET.SubElement(
                body,
                "{%s}p" % W_NS,
            )

            deleted = ET.SubElement(
                paragraph,
                "{%s}del" % W_NS,
            )

            deleted_run = ET.SubElement(
                deleted,
                "{%s}r" % W_NS,
            )

            deleted_text = ET.SubElement(
                deleted_run,
                "{%s}delText" % W_NS,
            )

            deleted_text.text = "Old"

            inserted = ET.SubElement(
                paragraph,
                "{%s}ins" % W_NS,
            )

            add_text(
                inserted,
                "New",
            )

            write_docx(
                path,
                body,
            )

            rows = extract_paragraphs(path)

            self.assertEqual(
                rows[0]["text"],
                "New",
            )

            self.assertIn(
                "TRACKED_CHANGE",
                rows[0]["writeback_blockers"],
            )

            units = [
                {
                    "id": "U1",
                    "location": "docx:word/document.xml:p=0",
                    "current_target": "New",
                }
            ]

            anchors = build_anchors(
                path,
                units,
            )

            self.assertEqual(
                anchors["U1"]["status"],
                "BLOCKED",
            )

            self.assertIn(
                "TRACKED_CHANGE",
                anchors["U1"]["writeback_blockers"],
            )


if __name__ == "__main__":
    unittest.main()
