from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "artifacts" / "submission_3_cg_fix"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "starmie_lucario_guard_v1"
DEFAULT_ARCHIVE = ROOT / "artifacts" / "submission_starmie_lucario_guard_v1.tar.gz"
DEFAULT_POLICY_OUTPUT_DIR = ROOT / "artifacts" / "starmie_lucario_guard_policy_v1"
DEFAULT_POLICY_ARCHIVE = ROOT / "artifacts" / "submission_starmie_lucario_guard_policy_v1.tar.gz"
DEFAULT_ENERGY_OUTPUT_DIR = ROOT / "artifacts" / "starmie_lucario_energy_guard_v1"
DEFAULT_ENERGY_ARCHIVE = ROOT / "artifacts" / "submission_starmie_lucario_energy_guard_v1.tar.gz"


class C:
    STARYU = 1030
    CINDERACE = 666
    MEGA_STARMIE = 1031
    POKEGEAR = 1122
    MEGA_SIGNAL = 1145
    BUDDY_POFFIN = 1086
    CRUSHING_HAMMER = 1120
    NIGHT_STRETCHER = 1097
    SALVATORE = 1189
    BOSS_ORDERS = 1182
    WALLY = 1229
    HILDA = 1225
    LILLIE = 1227
    HERO_CAPE = 1159
    WATER_ENERGY = 3
    IGNITION_ENERGY = 17


LUCARIO_GUARD_DECK = [
    C.STARYU,
    C.STARYU,
    C.STARYU,
    C.STARYU,
    C.CINDERACE,
    C.CINDERACE,
    C.CINDERACE,
    C.CINDERACE,
    C.MEGA_STARMIE,
    C.MEGA_STARMIE,
    C.MEGA_STARMIE,
    C.MEGA_STARMIE,
    C.POKEGEAR,
    C.POKEGEAR,
    C.POKEGEAR,
    C.POKEGEAR,
    C.MEGA_SIGNAL,
    C.MEGA_SIGNAL,
    C.MEGA_SIGNAL,
    C.MEGA_SIGNAL,
    C.BUDDY_POFFIN,
    C.BUDDY_POFFIN,
    C.BUDDY_POFFIN,
    C.BUDDY_POFFIN,
    C.CRUSHING_HAMMER,
    C.CRUSHING_HAMMER,
    C.CRUSHING_HAMMER,
    C.CRUSHING_HAMMER,
    C.NIGHT_STRETCHER,
    C.NIGHT_STRETCHER,
    C.SALVATORE,
    C.SALVATORE,
    C.SALVATORE,
    C.SALVATORE,
    C.BOSS_ORDERS,
    C.BOSS_ORDERS,
    C.BOSS_ORDERS,
    C.WALLY,
    C.WALLY,
    C.WALLY,
    C.HILDA,
    C.HILDA,
    C.LILLIE,
    C.LILLIE,
    C.LILLIE,
    C.LILLIE,
    C.HERO_CAPE,
    C.WATER_ENERGY,
    C.WATER_ENERGY,
    C.WATER_ENERGY,
    C.WATER_ENERGY,
    C.WATER_ENERGY,
    C.WATER_ENERGY,
    C.WATER_ENERGY,
    C.WATER_ENERGY,
    C.WATER_ENERGY,
    C.IGNITION_ENERGY,
    C.IGNITION_ENERGY,
    C.IGNITION_ENERGY,
    C.IGNITION_ENERGY,
]


def _require_source() -> None:
    missing = [path for path in (SOURCE_DIR / "main.py", SOURCE_DIR / "deck.csv", SOURCE_DIR / "cg") if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing source package pieces: {missing}")


def _validate_deck(deck: list[int]) -> None:
    counts = Counter(deck)
    if len(deck) != 60:
        raise ValueError(f"deck must contain 60 cards, got {len(deck)}")
    illegal = {card_id: count for card_id, count in counts.items() if card_id != C.WATER_ENERGY and count > 4}
    if illegal:
        raise ValueError(f"illegal non-basic counts: {illegal}")


def _read_source_deck() -> list[int]:
    return [int(line) for line in (SOURCE_DIR / "deck.csv").read_text(encoding="utf-8").splitlines() if line]


def _patched_main(source: str, *, gust_guard: bool = True) -> str:
    text = source
    text = text.replace("def agent(obs_dict):", "def agent(obs_dict, config=None):")
    text = text.replace(
        "    ULTRA_BALL = 1121\n",
        "    ULTRA_BALL = 1121\n\n\n"
        "LUCARIO_CHAIN_IDS = {673, 674, 675, 676, 677, 678}\n"
        "LUCARIO_SETUP_IDS = {673, 674, 675, 676, 677}\n",
    )
    text = text.replace(
        "    def _have_mega(self):\n"
        "        return any(p is not None and p.id == C.MEGA_STARMIE for p in self.my_board())\n",
        "    def _have_mega(self):\n"
        "        return any(p is not None and p.id == C.MEGA_STARMIE for p in self.my_board())\n\n"
        "    def _opponent_has_lucario_pressure(self):\n"
        "        return any(p is not None and p.id in LUCARIO_CHAIN_IDS\n"
        "                   for p in self.opponent.active + self.opponent.bench)\n\n"
        "    def _behind_on_prizes(self):\n"
        "        return len(getattr(self.me, \"prize\", []) or []) > len(getattr(self.opponent, \"prize\", []) or [])\n\n"
        "    def _has_backup_body(self):\n"
        "        return any(p is not None and p.id in (self.ATTACKER_IDS | {C.STARYU}) for p in self.me.bench)\n\n"
        "    def _lucario_energy_urgent(self):\n"
        "        return self._opponent_has_lucario_pressure() and not self.have_ready_attacker()\n\n"
        "    def _lucario_backup_urgent(self):\n"
        "        return self._opponent_has_lucario_pressure() and self._behind_on_prizes() and not self._has_backup_body()\n",
    )
    if gust_guard:
        text = text.replace(
            "        if cid == C.BOSS_ORDERS:                      # gust up a benched mon we can KO now\n"
            "            return 14500 if self._gust_ko_available() else 300\n",
            "        if cid == C.BOSS_ORDERS:                      # gust up setup pieces, not only KO targets\n"
            "            if self._opponent_has_lucario_pressure() and any(\n"
            "                    p is not None and p.id in LUCARIO_CHAIN_IDS for p in self.opponent.bench):\n"
            "                return 15000\n"
            "            return 14500 if self._gust_ko_available() else 300\n",
        )
    text = text.replace(
        "        # Water build-up: generic, gated by should_fuel (over-fill impossible).\n"
        "        if not self.should_fuel(p):\n"
        "            return -1\n"
        "        if not self.attach_helps(p, src):\n"
        "            return -1\n"
        "        return self.attach_priority(p, is_active)\n",
        "        # Water build-up: generic, gated by should_fuel, with a narrow Lucario-loss guard.\n"
        "        lucario_guard_attach = (\n"
        "            src is not None\n"
        "            and src.id == C.WATER_ENERGY\n"
        "            and self._lucario_backup_urgent()\n"
        "            and is_active\n"
        "            and p.id == C.CINDERACE\n"
        "        )\n"
        "        if not self.should_fuel(p) and not lucario_guard_attach:\n"
        "            return -1\n"
        "        if not self.attach_helps(p, src) and not lucario_guard_attach:\n"
        "            return -1\n"
        "        score = self.attach_priority(p, is_active)\n"
        "        if self._lucario_energy_urgent():\n"
        "            score += 18000\n"
        "        if lucario_guard_attach:\n"
        "            score += 16000\n"
        "        return score\n",
    )
    text = text.replace(
        "        if aid == TURBO_FLARE:\n"
        "            accel = 3000 if not self.have_ready_attacker() else 0\n"
        "            return 1200 + accel + min(dmg, 50)\n",
        "        if aid == TURBO_FLARE:\n"
        "            accel = 3000 if not self.have_ready_attacker() else 0\n"
        "            score = 1200 + accel + min(dmg, 50)\n"
        "            if self._lucario_backup_urgent() and not (dmg > 0 and opp.hp <= dmg):\n"
        "                score -= 9000\n"
        "            return score\n",
    )
    if gust_guard:
        text = text.replace(
            "        if o.playerIndex == self.op_index:\n"
            "            return self.gust_value(card)        # choosing the OPPONENT's new active -> gust the juiciest\n",
            "        if o.playerIndex == self.op_index:\n"
            "            if self._opponent_has_lucario_pressure():\n"
            "                if card.id in LUCARIO_SETUP_IDS:\n"
            "                    return 9000 - getattr(card, \"hp\", 0)\n"
            "                if card.id == 678 and getattr(o, \"area\", None) == AreaType.BENCH:\n"
            "                    return 8500 - getattr(card, \"hp\", 0) // 2\n"
            "            return self.gust_value(card)        # choosing the OPPONENT's new active -> gust the juiciest\n",
        )
    return text


def _write_deck(path: Path, deck: list[int]) -> None:
    path.write_text("\n".join(str(card_id) for card_id in deck) + "\n", encoding="utf-8")


def _make_archive(candidate_dir: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tf:
        for name in ("main.py", "deck.csv", "cg"):
            source = candidate_dir / name
            tf.add(source, arcname=name)


def build_lucario_guard_candidate(
    output_root: Path = DEFAULT_OUTPUT_DIR,
    *,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    return _build_candidate(
        output_root=output_root,
        archive_path=archive_path,
        deck=LUCARIO_GUARD_DECK,
        candidate_name="starmie_lucario_guard_v1",
        strategy=(
            "Mega Starmie ex tempo shell with full 4-4 Starmie line, Boss pressure, "
            "Lucario setup-piece gusting, and attach-before-churn guards."
        ),
        gust_guard=True,
    )


def build_lucario_guard_policy_candidate(
    output_root: Path = DEFAULT_POLICY_OUTPUT_DIR,
    *,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    _require_source()
    return _build_candidate(
        output_root=output_root,
        archive_path=archive_path,
        deck=_read_source_deck(),
        candidate_name="starmie_lucario_guard_policy_v1",
        strategy=(
            "Mega Starmie ex parent deck preserved; heuristic-only Lucario setup-piece gusting "
            "and attach-before-churn guards."
        ),
        gust_guard=True,
    )


def build_lucario_energy_guard_candidate(
    output_root: Path = DEFAULT_ENERGY_OUTPUT_DIR,
    *,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    _require_source()
    return _build_candidate(
        output_root=output_root,
        archive_path=archive_path,
        deck=_read_source_deck(),
        candidate_name="starmie_lucario_energy_guard_v1",
        strategy=(
            "Mega Starmie ex parent deck preserved; heuristic-only Lucario energy/backup guards "
            "without setup-piece gust override."
        ),
        gust_guard=False,
    )


def _build_candidate(
    *,
    output_root: Path,
    archive_path: Path | None,
    deck: list[int],
    candidate_name: str,
    strategy: str,
    gust_guard: bool,
) -> dict[str, Any]:
    _require_source()
    _validate_deck(deck)
    output_root = Path(output_root)
    archive_path = Path(archive_path) if archive_path is not None else output_root.with_suffix(".tar.gz")
    output_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SOURCE_DIR / "main.py", output_root / "main.py")
    shutil.rmtree(output_root / "cg", ignore_errors=True)
    shutil.copytree(SOURCE_DIR / "cg", output_root / "cg", ignore=shutil.ignore_patterns("__pycache__"))

    main_text = (SOURCE_DIR / "main.py").read_text(encoding="utf-8")
    (output_root / "main.py").write_text(_patched_main(main_text, gust_guard=gust_guard), encoding="utf-8")
    _write_deck(output_root / "deck.csv", deck)
    _make_archive(output_root, archive_path)

    report = {
        "candidate": candidate_name,
        "source_dir": str(SOURCE_DIR),
        "output_dir": str(output_root),
        "archive_path": str(archive_path),
        "deck_counts": dict(Counter(deck)),
        "strategy": strategy,
        "kaggle_submission_made": False,
    }
    (output_root / "build_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "candidate": report["candidate"],
        "main_path": output_root / "main.py",
        "deck_path": output_root / "deck.csv",
        "archive_path": archive_path,
        "report_path": output_root / "build_report.json",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build heuristic-only Starmie Lucario guard candidate.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--policy-only", action="store_true")
    parser.add_argument("--energy-only", action="store_true")
    args = parser.parse_args()
    if args.energy_only:
        output_dir = args.output_dir if args.output_dir != DEFAULT_OUTPUT_DIR else DEFAULT_ENERGY_OUTPUT_DIR
        archive = args.archive if args.archive != DEFAULT_ARCHIVE else DEFAULT_ENERGY_ARCHIVE
        result = build_lucario_energy_guard_candidate(output_dir, archive_path=archive)
    elif args.policy_only:
        output_dir = args.output_dir if args.output_dir != DEFAULT_OUTPUT_DIR else DEFAULT_POLICY_OUTPUT_DIR
        archive = args.archive if args.archive != DEFAULT_ARCHIVE else DEFAULT_POLICY_ARCHIVE
        result = build_lucario_guard_policy_candidate(output_dir, archive_path=archive)
    else:
        result = build_lucario_guard_candidate(args.output_dir, archive_path=args.archive)
    print(json.dumps({key: str(value) for key, value in result.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
