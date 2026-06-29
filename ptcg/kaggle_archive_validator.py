from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import traceback
from pathlib import Path
from typing import Any


REQUIRED_MEMBERS = ("main.py", "deck.csv", "cg/api.py")

STEP0_OBSERVATION = {
    "current": None,
    "logs": [],
    "remainingOverageTime": 600,
    "search_begin_input": None,
    "select": None,
    "step": 0,
}


class ArchiveValidationError(RuntimeError):
    pass


def _members(archive: Path) -> set[str]:
    with tarfile.open(archive, "r:gz") as tf:
        return {member.name.replace("\\", "/").lstrip("./") for member in tf.getmembers()}


def _read_deck_csv(deck_path: Path) -> tuple[list[int], str]:
    try:
        cards = [int(line.strip()) for line in deck_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except ValueError as exc:
        raise ArchiveValidationError("deck.csv must contain one integer card id per non-empty line") from exc
    if len(cards) != 60:
        raise ArchiveValidationError(f"deck.csv is not a 60-card deck: {len(cards)} cards")
    canonical = "".join(f"{card_id}\n" for card_id in cards).encode("ascii")
    return cards, hashlib.sha256(canonical).hexdigest().upper()


def validate_archive_startup(archive: Path) -> dict[str, Any]:
    archive = archive.resolve()
    members = _members(archive)
    missing = [member for member in REQUIRED_MEMBERS if member not in members]
    if missing:
        raise ArchiveValidationError(f"archive missing required members: {missing}")

    tmp = Path(tempfile.mkdtemp(prefix="ptcg_kaggle_strict_"))
    old_cwd = Path.cwd()
    old_path = sys.path[:]
    old_modules = set(sys.modules)
    try:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(tmp)

        deck_csv_cards, deck_csv_sha256 = _read_deck_csv(tmp / "deck.csv")
        env = {"__builtins__": __builtins__}
        main_path = tmp / "main.py"
        exec(compile(main_path.read_text(encoding="utf-8"), str(main_path), "exec"), env)
        agent = env.get("agent")
        if not callable(agent):
            raise ArchiveValidationError("main.py did not define callable agent")
        action = agent(dict(STEP0_OBSERVATION))
        ok = isinstance(action, list) and len(action) == 60 and all(isinstance(card, int) for card in action)
        if not ok:
            raise ArchiveValidationError(
                f"step-0 agent response is not a 60-card integer deck: {type(action).__name__}"
            )
        policy_module_loaded = False
        policy_loader = env.get("_load_policy_module")
        if callable(policy_loader):
            policy_loader()
            policy_module_loaded = True
        return {
            "archive": str(archive),
            "required_members_present": True,
            "strict_raw_exec_without_file_or_syspath": True,
            "deck_len": len(action),
            "deck_csv_len": len(deck_csv_cards),
            "deck_csv_sha256": deck_csv_sha256,
            "deck_csv_cards": deck_csv_cards,
            "agent_deck_matches_csv": list(action) == deck_csv_cards,
            "policy_module_loaded": policy_module_loaded,
        }
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path
        for name in set(sys.modules) - old_modules:
            if name == "cg" or name.startswith("cg."):
                sys.modules.pop(name, None)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strict Kaggle archive startup validation.")
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(validate_archive_startup(args.archive), sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"archive": str(args.archive), "error": str(exc)}, sort_keys=True), file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
