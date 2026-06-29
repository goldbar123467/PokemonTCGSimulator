from __future__ import annotations

from typing import Any


def manifest_row_tokens(row: dict[str, Any]) -> set[str]:
    tokens = {str(row.get("ref") or "").lower(), str(row.get("archetype") or "").lower()}
    tokens.update(str(tag).lower() for tag in row.get("tags") or [])
    return {token for token in tokens if token}


def row_matches_required_tag(row: dict[str, Any], required_tag: str) -> bool:
    tag = required_tag.lower()
    if not tag:
        return False
    return any(tag in token for token in manifest_row_tokens(row))


def select_with_required_tags(
    rows: list[dict[str, Any]],
    *,
    max_rows: int | None,
    required_tags: list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    if max_rows is None:
        return list(rows)
    if max_rows <= 0:
        return []

    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    for tag in required_tags:
        for row in rows:
            row_id = id(row)
            if row_id in selected_ids:
                continue
            if row_matches_required_tag(row, tag):
                selected.append(row)
                selected_ids.add(row_id)
                break
        if len(selected) >= max_rows:
            return selected[:max_rows]

    for row in rows:
        row_id = id(row)
        if row_id in selected_ids:
            continue
        selected.append(row)
        selected_ids.add(row_id)
        if len(selected) >= max_rows:
            break
    return selected[:max_rows]
