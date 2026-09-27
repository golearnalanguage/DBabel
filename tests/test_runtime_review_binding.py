import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(
    __file__
).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )

from review_model import load_bundle

from runtime.models import GenerationResponse
from runtime.post_translation import (
    prepare_post_translation,
)
from runtime.project import (
    sha256_file,
)
from runtime.review_binding import (
    ReviewBindingError,
    bind_review_session,
)
from runtime.semantic_adjudication import (
    adjudicate_semantics,
)


def translation_result(
    source,
    suggested,
):
    return {
        "format_version": "1.0",
        "status":
            "TRANSLATION_PROPOSED",
        "completion_allowed":
            False,
        "batch_count": 1,
        "unit_count": 1,
        "receipts": [],
        "units": [{
            "id": "U00001_en",
            "location": "line:1",
            "source": source,
            "target": "",
            "source_language":
                "zh-CN",
            "target_language":
                "en",
            "alignment":
                "ALIGNED",
            "context": {
                "text_role":
                    "PROSE",
            },
            "suggested_target":
                suggested,
            "proposal_decision":
                "REPLACE",
            "suggestion_reason":
                "test translation",
        }],
    }


class SemanticProvider:
    def __init__(
        self,
        outcome="NO_FINDING",
    ):
        self.outcome = outcome

    def generate(
        self,
        request,
    ):
        payload = json.loads(
            request.user
        )

        rows = []

        for unit in payload[
            "units"
        ]:
            if (
                self.outcome
                == "NO_FINDING"
            ):
                rows.append({
                    "id":
                        unit["id"],
                    "outcome":
                        "NO_FINDING",
                    "classification":
                        None,
                    "reason":
                        "No additional semantic risk surfaced.",
                    "next_action":
                        "",
                })
            else:
                rows.append({
                    "id":
                        unit["id"],
                    "outcome":
                        "REVIEW",
                    "classification":
                        "STANDARD_GENERAL",
                    "reason":
                        "Meaning requires human confirmation.",
                    "next_action":
                        "Review the proposed wording.",
                })

        return GenerationResponse(
            text=json.dumps(
                {"units": rows},
                ensure_ascii=False,
            ),
            model=
                "fake-semantic",
            provider=
                "fake-provider",
            response_id=
                "semantic-test",
            usage={
                "total_tokens": 10,
            },
        )


def build_inputs(
    source_path,
    source_text,
    suggested,
    semantic_outcome=
        "NO_FINDING",
):
    post = (
        prepare_post_translation(
            translation_result(
                source_text,
                suggested,
            ),
            source_language=
                "zh-CN",
            target_language=
                "en",
        )
    )

    semantic = (
        adjudicate_semantics(
            provider=
                SemanticProvider(
                    semantic_outcome
                ),
            post_translation=post,
            source_language=
                "zh-CN",
            target_language=
                "en",
            document_name=
                source_path.name,
        )
    )

    source_info = {
        "filename":
            source_path.name,
        "sha256":
            sha256_file(
                source_path
            ),
        "format":
            "txt",
        "coverage":
            "EXTRACTED_SCOPE",
        "native_export":
            True,
    }

    return (
        source_info,
        post,
        semantic,
    )


class ReviewBindingTests(
    unittest.TestCase
):
    def test_txt_layout_copy_reaches_full_human_review_gate(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = (
                root
                / "source.txt"
            )

            original = (
                "配置主库\n"
            ).encode("utf-8")

            source.write_bytes(
                original
            )

            (
                source_info,
                post,
                semantic,
            ) = build_inputs(
                source,
                "配置主库",
                "Configure the primary database.",
            )

            run_root = (
                root / "run"
            )
            run_root.mkdir()

            result = bind_review_session(
                repo_root=ROOT,
                run_root=run_root,
                source=source,
                source_info=
                    source_info,
                post_translation=
                    post,
                semantic_result=
                    semantic,
            )

            self.assertEqual(
                result["status"],
                "READY_FOR_HUMAN_REVIEW",
            )

            self.assertFalse(
                result[
                    "completion_allowed"
                ]
            )

            self.assertEqual(
                result["surface"],
                "FULL_LOCAL_WORKBENCH_READY",
            )

            self.assertEqual(
                source.read_bytes(),
                original,
            )

            bundle = Path(
                result[
                    "bundle_path"
                ]
            )

            data = load_bundle(
                bundle
            )

            unit = data[
                "units"
            ][0]

            self.assertEqual(
                unit[
                    "current_target"
                ],
                "配置主库",
            )

            self.assertEqual(
                unit[
                    "suggested_target"
                ],
                "Configure the primary database.",
            )

            self.assertNotIn(
                "approved_target",
                unit,
            )

            decision = data[
                "decisions"
            ][0]

            self.assertEqual(
                decision["status"],
                "UNREVIEWED",
            )

            anchor = data[
                "anchors"
            ][
                "U00001_en"
            ]

            self.assertEqual(
                anchor["status"],
                "RESOLVED",
            )

            session = data[
                "session"
            ]

            self.assertTrue(
                session[
                    "preparation"
                ][
                    "qa_report_bound"
                ]
            )

            self.assertTrue(
                session[
                    "preparation"
                ][
                    "audit_report_bound"
                ]
            )

            self.assertNotIn(
                "path_hint",
                session[
                    "original"
                ],
            )

    def test_deterministic_and_semantic_issues_are_both_bound(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = (
                root
                / "source.txt"
            )

            source.write_text(
                "端口为 5236。\n",
                encoding="utf-8",
            )

            (
                source_info,
                post,
                semantic,
            ) = build_inputs(
                source,
                "端口为 5236。",
                "The port is 5237.",
                semantic_outcome=
                    "REVIEW",
            )

            run_root = (
                root / "run"
            )
            run_root.mkdir()

            result = bind_review_session(
                repo_root=ROOT,
                run_root=run_root,
                source=source,
                source_info=
                    source_info,
                post_translation=
                    post,
                semantic_result=
                    semantic,
            )

            data = load_bundle(
                Path(
                    result[
                        "bundle_path"
                    ]
                )
            )

            unit = data[
                "units"
            ][0]

            self.assertTrue(
                unit[
                    "qa_issue_refs"
                ]
            )

            self.assertTrue(
                unit[
                    "finding_refs"
                ]
            )

            self.assertGreaterEqual(
                len(
                    data["issues"]
                ),
                2,
            )

    def test_source_hash_mismatch_fails_before_binding(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = (
                root
                / "source.txt"
            )

            source.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            (
                source_info,
                post,
                semantic,
            ) = build_inputs(
                source,
                "配置主库",
                "Configure the primary database.",
            )

            source_info[
                "sha256"
            ] = "0" * 64

            run_root = (
                root / "run"
            )
            run_root.mkdir()

            with self.assertRaises(
                ReviewBindingError
            ):
                bind_review_session(
                    repo_root=ROOT,
                    run_root=run_root,
                    source=source,
                    source_info=
                        source_info,
                    post_translation=
                        post,
                    semantic_result=
                        semantic,
                )

            self.assertFalse(
                (
                    run_root
                    / "review.dbreview"
                ).exists()
            )

    def test_non_native_source_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = (
                root
                / "source.txt"
            )

            source.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            (
                source_info,
                post,
                semantic,
            ) = build_inputs(
                source,
                "配置主库",
                "Configure the primary database.",
            )

            source_info[
                "native_export"
            ] = False

            run_root = (
                root / "run"
            )
            run_root.mkdir()

            with self.assertRaises(
                ReviewBindingError
            ):
                bind_review_session(
                    repo_root=ROOT,
                    run_root=run_root,
                    source=source,
                    source_info=
                        source_info,
                    post_translation=
                        post,
                    semantic_result=
                        semantic,
                )


if __name__ == "__main__":
    unittest.main()
