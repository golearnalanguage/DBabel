import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from docx_review_adapter import W_NS
from review_model import read_jsonl


def make_docx(path, texts):
    doc = ET.Element("{%s}document" % W_NS)
    body = ET.SubElement(doc, "{%s}body" % W_NS)

    for value in texts:
        paragraph = ET.SubElement(body, "{%s}p" % W_NS)
        run = ET.SubElement(paragraph, "{%s}r" % W_NS)
        text = ET.SubElement(run, "{%s}t" % W_NS)
        text.text = value

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
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
                doc,
                encoding="utf-8",
                xml_declaration=True,
            ),
        )


class DocxAlignmentMapTests(unittest.TestCase):
    def run_extract(
        self,
        source,
        target,
        output,
        alignment_map,
    ):
        return subprocess.run(
            [
                sys.executable,
                str(
                    SCRIPTS
                    / "extract_docx_bilingual_units.py"
                ),
                str(source),
                str(target),
                "--output",
                str(output),
                "--alignment-map",
                str(alignment_map),
            ],
            capture_output=True,
            text=True,
        )

    def test_explicit_map_supports_split_merge_and_unaligned(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)

            source = d / "source.docx"
            target = d / "target.docx"
            output = d / "units.jsonl"
            alignment_map = d / "alignment.json"

            make_docx(
                source,
                ["S1", "S2", "S3", "S4", "S5"],
            )

            make_docx(
                target,
                ["T1", "T2", "T3", "T4", "T5"],
            )

            alignment_map.write_text(
                json.dumps(
                    {
                        "format_version": "1.0",
                        "alignments": [
                            {
                                "id": "A1",
                                "source": [1],
                                "target": [1],
                                "status": "ALIGNED",
                            },
                            {
                                "id": "A2",
                                "source": [2],
                                "target": [2, 3],
                                "status": "SPLIT",
                            },
                            {
                                "id": "A3",
                                "source": [3, 4],
                                "target": [4],
                                "status": "MERGED",
                            },
                            {
                                "id": "A4",
                                "source": [5],
                                "target": [],
                                "status": "UNALIGNED",
                            },
                            {
                                "id": "A5",
                                "source": [],
                                "target": [5],
                                "status": "UNALIGNED",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_extract(
                source,
                target,
                output,
                alignment_map,
            )

            self.assertEqual(
                result.returncode,
                0,
                result.stderr,
            )

            units = read_jsonl(output)

            self.assertEqual(
                [
                    unit["alignment"]
                    for unit in units
                ],
                [
                    "ALIGNED",
                    "SPLIT",
                    "MERGED",
                    "UNALIGNED",
                    "UNALIGNED",
                ],
            )

            self.assertEqual(
                units[1]["source"],
                "S2",
            )

            self.assertEqual(
                units[1]["target"],
                "T2\n\nT3",
            )

            self.assertEqual(
                len(units[1]["target_refs"]),
                2,
            )

            self.assertEqual(
                units[2]["source"],
                "S3\n\nS4",
            )

            self.assertEqual(
                units[2]["target"],
                "T4",
            )

            self.assertEqual(
                len(units[2]["source_refs"]),
                2,
            )

            self.assertEqual(
                units[3]["target"],
                "",
            )

            self.assertEqual(
                units[4]["source"],
                "",
            )

            self.assertEqual(
                units[0]["location"],
                units[0]["target_refs"][0],
            )

            self.assertEqual(
                units[1]["location"],
                "alignment:A2",
            )

    def test_alignment_map_requires_full_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)

            source = d / "source.docx"
            target = d / "target.docx"
            output = d / "units.jsonl"
            alignment_map = d / "alignment.json"

            make_docx(
                source,
                ["S1", "S2"],
            )

            make_docx(
                target,
                ["T1"],
            )

            alignment_map.write_text(
                json.dumps(
                    {
                        "format_version": "1.0",
                        "alignments": [
                            {
                                "id": "A1",
                                "source": [1],
                                "target": [1],
                                "status": "ALIGNED",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_extract(
                source,
                target,
                output,
                alignment_map,
            )

            self.assertNotEqual(
                result.returncode,
                0,
            )

            self.assertIn(
                "source paragraph coverage mismatch",
                result.stderr,
            )

            self.assertFalse(
                output.exists()
            )

    def test_alignment_map_rejects_duplicate_consumption(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)

            source = d / "source.docx"
            target = d / "target.docx"
            output = d / "units.jsonl"
            alignment_map = d / "alignment.json"

            make_docx(
                source,
                ["S1"],
            )

            make_docx(
                target,
                ["T1", "T2"],
            )

            alignment_map.write_text(
                json.dumps(
                    {
                        "format_version": "1.0",
                        "alignments": [
                            {
                                "id": "A1",
                                "source": [1],
                                "target": [1],
                                "status": "ALIGNED",
                            },
                            {
                                "id": "A2",
                                "source": [1],
                                "target": [2],
                                "status": "ALIGNED",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_extract(
                source,
                target,
                output,
                alignment_map,
            )

            self.assertNotEqual(
                result.returncode,
                0,
            )

            self.assertIn(
                "reuses source paragraph",
                result.stderr,
            )

            self.assertFalse(
                output.exists()
            )

    def test_alignment_status_must_match_cardinality(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)

            source = d / "source.docx"
            target = d / "target.docx"
            output = d / "units.jsonl"
            alignment_map = d / "alignment.json"

            make_docx(
                source,
                ["S1"],
            )

            make_docx(
                target,
                ["T1", "T2"],
            )

            alignment_map.write_text(
                json.dumps(
                    {
                        "format_version": "1.0",
                        "alignments": [
                            {
                                "id": "A1",
                                "source": [1],
                                "target": [1, 2],
                                "status": "ALIGNED",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = self.run_extract(
                source,
                target,
                output,
                alignment_map,
            )

            self.assertNotEqual(
                result.returncode,
                0,
            )

            self.assertIn(
                "status ALIGNED is inconsistent",
                result.stderr,
            )

            self.assertFalse(
                output.exists()
            )

    def test_review_session_preserves_alignment_references(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)

            target = d / "target.docx"
            units = d / "units.jsonl"
            bundle = d / "review.dbreview"

            make_docx(
                target,
                ["T1", "T2"],
            )

            units.write_text(
                json.dumps(
                    {
                        "id": "U1",
                        "source": "S1",
                        "target": "T1\n\nT2",
                        "location": "alignment:A1",
                        "alignment_id": "A1",
                        "alignment": "SPLIT",
                        "source_refs": [
                            "docx:word/document.xml:p=0"
                        ],
                        "target_refs": [
                            "docx:word/document.xml:p=0",
                            "docx:word/document.xml:p=1",
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(
                        SCRIPTS
                        / "create_review_session.py"
                    ),
                    str(units),
                    "--original",
                    str(target),
                    "--output",
                    str(bundle),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                result.stderr,
            )

            review_units = read_jsonl(
                bundle / "units.jsonl"
            )

            unit = review_units[0]

            self.assertEqual(
                unit["alignment_id"],
                "A1",
            )

            self.assertEqual(
                unit["alignment"],
                "SPLIT",
            )

            self.assertEqual(
                unit["source_refs"],
                [
                    "docx:word/document.xml:p=0"
                ],
            )

            self.assertEqual(
                unit["target_refs"],
                [
                    "docx:word/document.xml:p=0",
                    "docx:word/document.xml:p=1",
                ],
            )

            anchors = json.loads(
                (
                    bundle
                    / "anchors.json"
                ).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                anchors["U1"]["status"],
                "BLOCKED",
            )


if __name__ == "__main__":
    unittest.main()
