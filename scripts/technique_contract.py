#!/usr/bin/env python3
"""Cross-contract validation for DBabel technique annotations."""

from pathlib import Path
from typing import Any, Dict, List

import yaml


def load_translation_registry(repo_root: Path) -> Dict[str, Any]:
    path = (
        Path(repo_root)
        / "config"
        / "translation_techniques.yaml"
    )

    value = yaml.safe_load(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(value, dict):
        raise ValueError(
            "translation technique registry must be an object"
        )

    return value


def validate_technique_annotation(
    annotation: Any,
    registry: Dict[str, Any],
) -> List[str]:
    if annotation is None:
        return []

    if not isinstance(annotation, dict):
        return [
            "technique annotation must be an object"
        ]

    technique_id = annotation.get(
        "technique_id"
    )

    techniques = {
        item.get("id"): item
        for item in (
            registry.get("techniques") or []
        )
        if isinstance(item, dict)
    }

    technique = techniques.get(
        technique_id
    )

    if technique is None:
        return [
            "unknown technique_id {}".format(
                technique_id
            )
        ]

    errors = []

    actual_risk = annotation.get("risk")
    expected_risk = technique.get("risk")

    if actual_risk != expected_risk:
        errors.append(
            "technique risk {} does not match catalog risk {}".format(
                actual_risk,
                expected_risk,
            )
        )

    declared_transformations = (
        set(
            technique.get(
                "allowed_transformations",
                [],
            )
        )
        | set(
            technique.get(
                "restricted_transformations",
                [],
            )
        )
    )

    annotated_transformations = set(
        annotation.get(
            "transformations",
            [],
        )
    )

    unknown_transformations = (
        annotated_transformations
        - declared_transformations
    )

    if unknown_transformations:
        errors.append(
            "transformations are not declared for {}: {}".format(
                technique_id,
                ", ".join(
                    sorted(
                        unknown_transformations
                    )
                ),
            )
        )

    declared_dimensions = set(
        (
            technique.get(
                "qa_mapping"
            )
            or {}
        ).get(
            "semantic_dimensions",
            [],
        )
    )

    annotated_dimensions = set(
        annotation.get(
            "quality_dimensions",
            [],
        )
    )

    unknown_dimensions = (
        annotated_dimensions
        - declared_dimensions
    )

    if unknown_dimensions:
        errors.append(
            "quality dimensions are not declared for {}: {}".format(
                technique_id,
                ", ".join(
                    sorted(
                        unknown_dimensions
                    )
                ),
            )
        )

    return errors
