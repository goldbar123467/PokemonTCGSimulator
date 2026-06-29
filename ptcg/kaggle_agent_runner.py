from __future__ import annotations

import argparse
import inspect
import json
import os
import shutil
import sys
import tarfile
import tempfile
import traceback
from pathlib import Path
from typing import Any

from ptcg.kaggle_archive_validator import ArchiveValidationError, REQUIRED_MEMBERS


class AgentDecisionError(RuntimeError):
    pass


def decode_agent_action(action: Any, observation: dict[str, Any]) -> dict[str, Any]:
    select = observation.get("select") if isinstance(observation, dict) else {}
    if not isinstance(select, dict):
        select = {}
    raw_options = select.get("option") or []
    options = [option for option in raw_options if isinstance(option, dict)]
    min_count = _int_or(select.get("minCount"), 0)
    max_count = _int_or(select.get("maxCount"), len(options))

    selected_indexes: list[int] = []
    match_mode = "unmatched"
    invalid_reason: str | None = None

    if isinstance(action, int):
        action_values: Any = [int(action)]
    elif isinstance(action, tuple):
        action_values = list(action)
    else:
        action_values = action

    if isinstance(action_values, list) and all(isinstance(value, int) for value in action_values):
        compact_values = [int(value) for value in action_values]
        if all(0 <= value < len(options) for value in compact_values):
            selected_indexes = compact_values
            match_mode = "option_indexes"
        else:
            compact_match = _compact_option_payload_indexes(compact_values, options)
            if compact_match is not None:
                selected_indexes = compact_match
                match_mode = "compact_option_payload"
            else:
                invalid_reason = "integer action values do not map to legal option indexes"
    elif isinstance(action_values, dict):
        payload_match = _option_payload_indexes([action_values], options)
        if payload_match is not None:
            selected_indexes = payload_match
            match_mode = "option_payload"
        else:
            invalid_reason = "option payload does not match any legal option"
    elif isinstance(action_values, list) and all(isinstance(value, dict) for value in action_values):
        payload_match = _option_payload_indexes(action_values, options)
        if payload_match is not None:
            selected_indexes = payload_match
            match_mode = "option_payload"
        else:
            invalid_reason = "one or more option payloads do not match legal options"
    else:
        invalid_reason = f"unsupported action type: {type(action).__name__}"

    if invalid_reason is None and len(set(selected_indexes)) != len(selected_indexes):
        invalid_reason = "duplicate option indexes are not legal"
    if invalid_reason is None and not (min_count <= len(selected_indexes) <= max_count):
        invalid_reason = f"selected {len(selected_indexes)} options outside legal range {min_count}-{max_count}"

    matched_options = [options[index] for index in selected_indexes if 0 <= index < len(options)]
    return {
        "legal": invalid_reason is None,
        "match_mode": match_mode,
        "selected_option_indexes": selected_indexes,
        "matched_option": matched_options[0] if matched_options else None,
        "matched_options": matched_options,
        "option_count": len(options),
        "min_count": min_count,
        "max_count": max_count,
        "invalid_reason": invalid_reason,
    }


def run_archive_agent_decision(archive: Path, observation: dict[str, Any]) -> dict[str, Any]:
    archive = archive.resolve()
    _require_members(archive)

    tmp = Path(tempfile.mkdtemp(prefix="ptcg_kaggle_decision_"))
    old_cwd = Path.cwd()
    old_path = sys.path[:]
    old_modules = set(sys.modules)
    try:
        with tarfile.open(archive, "r:gz") as tf:
            _safe_extract(tf, tmp)

        env: dict[str, Any] = {"__builtins__": __builtins__}
        main_path = tmp / "main.py"
        exec(compile(main_path.read_text(encoding="utf-8"), str(main_path), "exec"), env)
        agent = env.get("agent")
        if not callable(agent):
            raise AgentDecisionError("main.py did not define callable agent")

        agent_observation = _agent_observation(observation)
        raw_action = _call_agent(agent, agent_observation)
        decision = decode_agent_action(raw_action, agent_observation)
        return {
            "archive": str(archive),
            "raw_action": _json_safe(raw_action),
            "decision": decision,
            "kaggle_submission_made": False,
        }
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path
        for name in set(sys.modules) - old_modules:
            if name == "cg" or name.startswith("cg."):
                sys.modules.pop(name, None)
        shutil.rmtree(tmp, ignore_errors=True)


def _require_members(archive: Path) -> None:
    with tarfile.open(archive, "r:gz") as tf:
        members = {member.name.replace("\\", "/").lstrip("./") for member in tf.getmembers()}
    missing = [member for member in REQUIRED_MEMBERS if member not in members]
    if missing:
        raise ArchiveValidationError(f"archive missing required members: {missing}")


def _safe_extract(tf: tarfile.TarFile, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    for member in tf.getmembers():
        if member.issym() or member.islnk():
            raise ArchiveValidationError(f"archive contains unsupported link member: {member.name}")
        member_target = (target_root / member.name).resolve()
        if not _is_relative_to(member_target, target_root):
            raise ArchiveValidationError(f"archive member escapes extraction root: {member.name}")
    tf.extractall(target_root)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _agent_observation(observation: dict[str, Any]) -> dict[str, Any]:
    copied = json.loads(json.dumps(observation))
    copied.setdefault("logs", [])
    copied.setdefault("remainingOverageTime", 600)
    copied.setdefault("search_begin_input", None)
    copied.setdefault("step", 1)
    return copied


def _call_agent(agent: Any, observation: dict[str, Any]) -> Any:
    try:
        signature = inspect.signature(agent)
    except (TypeError, ValueError):
        try:
            return agent(observation, None)
        except TypeError:
            return agent(observation)

    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    accepts_varargs = any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    if accepts_varargs or len(positional) >= 2:
        return agent(observation, None)
    return agent(observation)


def _option_payload_indexes(payloads: list[dict[str, Any]], options: list[dict[str, Any]]) -> list[int] | None:
    selected: list[int] = []
    for payload in payloads:
        matched_index = None
        for index, option in enumerate(options):
            if index in selected:
                continue
            if _payload_matches_option(payload, option):
                matched_index = index
                break
        if matched_index is None:
            return None
        selected.append(matched_index)
    return selected


def _payload_matches_option(payload: dict[str, Any], option: dict[str, Any]) -> bool:
    comparable = {key: value for key, value in payload.items() if value is not None}
    if not comparable:
        return False
    return all(option.get(key) == value for key, value in comparable.items())


def _compact_option_payload_indexes(values: list[int], options: list[dict[str, Any]]) -> list[int] | None:
    if not values:
        return []
    option_type = values[0]
    typed_options = [(index, option) for index, option in enumerate(options) if option.get("type") == option_type]
    if len(values) == 1:
        if len(typed_options) == 1:
            return [typed_options[0][0]]
        return None
    detail = values[1]
    for index, option in typed_options:
        if option.get("index") == detail or option.get("attackId") == detail or option.get("number") == detail:
            return [index]
    return None


def _int_or(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return repr(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Kaggle PTCG agent against a native observation.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--observation-file", type=Path, required=True)
    parser.add_argument("--report-file", type=Path)
    args = parser.parse_args(argv)

    try:
        observation = json.loads(args.observation_file.read_text(encoding="utf-8"))
        result = run_archive_agent_decision(args.archive, observation)
        if args.report_file is not None:
            args.report_file.parent.mkdir(parents=True, exist_ok=True)
            args.report_file.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result["report_path"] = str(args.report_file.resolve())
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"archive": str(args.archive), "error": str(exc)}, sort_keys=True), file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
