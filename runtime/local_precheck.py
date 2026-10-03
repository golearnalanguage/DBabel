"""Cheap document checks run locally before any provider request."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Sequence

from runtime.translation import protected_literals
from runtime.translation_memory import matches


def inspect_segments(segments: Sequence[Dict[str, Any]], source_language: str,
                     target_language: str) -> Dict[str, Any]:
    counts = Counter(str(row.get("text") or "") for row in segments)
    duplicate_count = sum(n - 1 for source, n in counts.items() if source and n > 1)
    indexed = matches([{"id": str(index), "source": row.get("text", ""), "text_role": "PROSE"}
                       for index, row in enumerate(segments)], source_language, target_language)
    protected_count = 0
    typo_locations = []
    for row in segments:
        source = str(row.get("text") or "")
        protected_count += len(protected_literals(source))
        if "操用户" in source:
            typo_locations.append(str(row.get("location") or ""))
    return {"extracted_segments": len(segments),
            "repeated_source_segments": duplicate_count,
            "exact_translation_memory_matches": len(indexed),
            "protected_literal_occurrences": protected_count,
            "possible_source_typo_locations": typo_locations[:20],
            "provider_requests_for_exact_matches": 0}
