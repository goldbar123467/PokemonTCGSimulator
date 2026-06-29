from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class NotebookArtifacts:
    notebook_path: Path
    strategy_text: str
    main_py: str | None
    deck_csv: str | None
    deck_ids: list[int] | None


def _cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source)


def _writefile_target_and_body(source: str) -> tuple[str | None, str]:
    lines = source.splitlines()
    if not lines:
        return None, source
    first = lines[0].strip()
    if not first.startswith("%%writefile"):
        return None, source
    parts = first.split(maxsplit=1)
    if len(parts) != 2:
        return None, "\n".join(lines[1:]) + "\n"
    return Path(parts[1].strip()).name, "\n".join(lines[1:]) + "\n"


def _parse_deck_csv(text: str) -> list[int] | None:
    ids: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            ids.append(int(stripped))
        except ValueError:
            return None
    return ids if len(ids) == 60 else None


def _safe_parse(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _target_names(node: ast.Assign) -> set[str]:
    return {target.id for target in node.targets if isinstance(target, ast.Name)}


def _literal_list_from_assign(source: str, names: set[str]) -> list[int] | None:
    tree = _safe_parse(source)
    if tree is None:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not _target_names(node) & names:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (SyntaxError, ValueError, TypeError):
            continue
        if isinstance(value, list) and len(value) == 60 and all(isinstance(item, int) for item in value):
            return [int(item) for item in value]
    return None


def _literal_count_dict_from_assign(source: str, names: set[str]) -> list[int] | None:
    tree = _safe_parse(source)
    if tree is None:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not _target_names(node) & names:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (SyntaxError, ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        if not all(isinstance(card_id, int) and isinstance(count, int) for card_id, count in value.items()):
            continue
        if sum(value.values()) != 60:
            continue
        deck: list[int] = []
        for card_id, count in value.items():
            deck.extend([int(card_id)] * int(count))
        return deck
    return None


def _parse_inline_deck_counts(source: str) -> list[int] | None:
    pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\d+)\s*#.*?[xX]\s*(\d+)", re.MULTILINE)
    deck: list[int] = []
    for _name, card_id, count in pattern.findall(source):
        deck.extend([int(card_id)] * int(count))
    return deck if len(deck) == 60 else None


def _eval_int(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return int(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _eval_int(node.operand)
        return -value if value is not None else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _eval_int(node.operand)
    return None


def _eval_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return str(node.value)
    return None


def _eval_int_list_expr(node: ast.AST, values: dict[str, list[int]]) -> list[int] | None:
    if isinstance(node, ast.List):
        deck: list[int] = []
        for item in node.elts:
            value = _eval_int(item)
            if value is None:
                return None
            deck.append(value)
        return deck
    if isinstance(node, ast.Name) and node.id in values:
        return list(values[node.id])
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "list" and len(node.args) == 1:
            return _eval_int_list_expr(node.args[0], values)
        if node.func.id == "_apply" and len(node.args) == 3:
            deck = _eval_int_list_expr(node.args[0], values)
            card_id = _eval_int(node.args[1])
            delta = _eval_int(node.args[2])
            if deck is None or card_id is None or delta is None:
                return None
            result = list(deck)
            if delta < 0:
                for _ in range(-delta):
                    if card_id not in result:
                        return None
                    result.remove(card_id)
            else:
                result.extend([card_id] * delta)
            return result
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _eval_int_list_expr(node.left, values)
        right = _eval_int_list_expr(node.right, values)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left = _eval_int_list_expr(node.left, values)
        right_int = _eval_int(node.right)
        if left is not None and right_int is not None:
            return left * right_int
        left_int = _eval_int(node.left)
        right = _eval_int_list_expr(node.right, values)
        if left_int is not None and right is not None:
            return right * left_int
    return None


def _variant_deck_from_sources(sources: list[str]) -> list[int] | None:
    values: dict[str, list[int]] = {}
    variants: dict[str, list[int]] = {}
    selected_variant: str | None = None

    for source in sources:
        tree = _safe_parse(source)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = _target_names(node)
            if "DECK_VARIANT" in names:
                selected_variant = _eval_string(node.value) or selected_variant

            deck_value = _eval_int_list_expr(node.value, values)
            if deck_value is not None:
                for name in names:
                    values[name] = deck_value
                continue

            if "DECK_VARIANTS" in names and isinstance(node.value, ast.Dict):
                for key_node, value_node in zip(node.value.keys, node.value.values, strict=False):
                    key = _eval_string(key_node)
                    value = _eval_int_list_expr(value_node, values)
                    if key is not None and value is not None:
                        variants[key] = value

    if selected_variant is not None and selected_variant in variants:
        return variants[selected_variant]
    if "DECK" in values:
        return values["DECK"]
    if "BASELINE_DECK" in values:
        return values["BASELINE_DECK"]
    return None


def _literal_constants_from_sources(sources: list[str]) -> dict[str, object]:
    constants: dict[str, object] = {}
    for source in sources:
        tree = _safe_parse(source)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
                continue
            for name in _target_names(node):
                constants[name] = node.value.value
    return constants


def _string_assignments_from_sources(sources: list[str]) -> dict[str, str]:
    strings: dict[str, str] = {}
    for source in sources:
        tree = _safe_parse(source)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            value = _eval_string(node.value)
            if value is None:
                continue
            for name in _target_names(node):
                strings[name] = value
    return strings


def _main_section_registry_from_sources(sources: list[str]) -> list[str]:
    for source in sources:
        tree = _safe_parse(source)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign) or "MAIN_SECTION_REGISTRY" not in _target_names(node):
                continue
            if not isinstance(node.value, ast.List):
                continue
            names: list[str] = []
            for item in node.value.elts:
                if not isinstance(item, ast.Tuple) or len(item.elts) < 2:
                    continue
                section_ref = item.elts[1]
                if isinstance(section_ref, ast.Name):
                    names.append(section_ref.id)
            if names:
                return names
    return []


def _replace_constant_line(source: str, name: str, value: object) -> str:
    rendered = "True" if value is True else "False" if value is False else repr(value)
    return re.sub(rf"^{re.escape(name)}\s*=\s*.+$", f"{name} = {rendered}", source, count=1, flags=re.MULTILINE)


def _generated_main_from_sources(sources: list[str], deck_ids: list[int] | None) -> str | None:
    strings = _string_assignments_from_sources(sources)
    registry = _main_section_registry_from_sources(sources)
    if not registry or any(name not in strings for name in registry):
        return None

    main_py = "\n\n".join(strings[name].rstrip() for name in registry) + "\n"
    if deck_ids is not None:
        main_py = re.sub(
            r"EMBEDDED_DECK = \[\n(?:    [0-9, ]+\n)+\]",
            "EMBEDDED_DECK = " + repr(deck_ids),
            main_py,
            count=1,
        )

    constants = _literal_constants_from_sources(sources)
    replacements = {
        "USE_SEARCH": constants.get("USE_SEARCH_IN_AGENT"),
        "CRUSTLE_AWARE": constants.get("CRUSTLE_AWARE_IN_AGENT"),
        "SEARCH_NODE_BUDGET": constants.get("SEARCH_NODE_BUDGET"),
        "SEARCH_TIME_BUDGET_S": constants.get("SEARCH_TIME_BUDGET_S"),
        "SEARCH_ACTION_CAP": constants.get("SEARCH_ACTION_CAP"),
    }
    for name, value in replacements.items():
        if value is not None:
            main_py = _replace_constant_line(main_py, name, value)
    return main_py


def _direct_deck_from_source(source: str) -> list[int] | None:
    return (
        _literal_list_from_assign(source, {"DECK", "my_deck", "deck", "deck_ids"})
        or _literal_count_dict_from_assign(source, {"DECK_COUNTS", "deck_counts"})
        or _parse_inline_deck_counts(source)
    )


def extract_notebook_artifacts(notebook_path: Path) -> NotebookArtifacts:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    markdown_parts: list[str] = []
    code_parts: list[str] = []
    main_py: str | None = None
    deck_csv: str | None = None
    deck_ids: list[int] | None = None

    for cell in notebook.get("cells", []):
        source = _cell_source(cell)
        if cell.get("cell_type") == "markdown":
            markdown_parts.append(source)
            continue
        if cell.get("cell_type") != "code":
            continue

        filename, body = _writefile_target_and_body(source)
        parse_source = body if filename else source
        code_parts.append(parse_source)
        if filename == "main.py":
            main_py = body
            deck_ids = deck_ids or _direct_deck_from_source(body)
        elif filename is not None and filename.endswith(".csv"):
            deck_csv = body
            deck_ids = deck_ids or _parse_deck_csv(body)
        else:
            deck_ids = deck_ids or _direct_deck_from_source(source)

    if deck_ids is None:
        deck_ids = _variant_deck_from_sources(code_parts)
    if deck_ids is None:
        for source in code_parts:
            deck_ids = _literal_list_from_assign(source, {"BASELINE_DECK"})
            if deck_ids is not None:
                break

    main_py = main_py or _generated_main_from_sources(code_parts, deck_ids)

    return NotebookArtifacts(
        notebook_path=notebook_path,
        strategy_text="\n\n".join(markdown_parts),
        main_py=main_py,
        deck_csv=deck_csv,
        deck_ids=deck_ids,
    )
