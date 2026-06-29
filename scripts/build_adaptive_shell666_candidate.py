from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PROFILE_SOURCES = {
    "default": ROOT / "artifacts/candidates/hard_gate_wide_refine/shell666_v05_elite_v07_elite_v62/main.py",
    "lucario": ROOT / "artifacts/candidates/anti_lucario_rule_tune/shell666_v49/main.py",
    "alakazam": ROOT / "artifacts/candidates/focused_tune/shell666_v08/main.py",
    "crustle": ROOT / "artifacts/candidates/hard_gate_wide_refine/shell666_v05_elite_v07_elite_v62/main.py",
    "nursrijan": ROOT / "artifacts/candidates/hard_gate_wide_refine/shell666_v05_elite_v07_elite_v54/main.py",
    "generic": ROOT / "artifacts/candidates/tuned_wide/shell666_v05/main.py",
}

BASE_MAIN = ROOT / "artifacts/candidates/lucario_energy_refine/shell666_v13/main.py"
BASE_DECK = ROOT / "artifacts/candidates/hard_gate_wide_refine/shell666_v05_elite_v07_elite_v62/deck.csv"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/candidates/adaptive_shell666/coverage_profile_v01"


def _extract_weights(path: Path) -> dict[str, float]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^WEIGHTS = (\{.*\})$", text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"missing WEIGHTS in {path}")
    return ast.literal_eval(match.group(1))


def _render_profiles(profile_sources: dict[str, Path]) -> str:
    profiles = {name: _extract_weights(path) for name, path in profile_sources.items()}
    return f"WEIGHT_PROFILES = {profiles!r}\nACTIVE_WEIGHTS = WEIGHT_PROFILES['default']"


def build(
    output_dir: Path,
    *,
    profile_sources: dict[str, Path] | None = None,
    base_main: Path | None = None,
    base_deck: Path | None = None,
    strategy: str = "adaptive shell666 profile selector from public-pool coverage",
) -> None:
    profile_sources = dict(profile_sources or DEFAULT_PROFILE_SOURCES)
    if "default" not in profile_sources:
        raise ValueError("profile_sources must include a default profile")
    base_main = base_main or BASE_MAIN
    base_deck = base_deck or BASE_DECK

    output_dir.mkdir(parents=True, exist_ok=True)
    main_text = base_main.read_text(encoding="utf-8")
    main_text = re.sub(
        r"WEIGHTS = \{.*\}",
        _render_profiles(profile_sources),
        main_text,
        count=1,
    )
    main_text = main_text.replace(
        "def _w(name: str, default: float) -> float:\n    return float(WEIGHTS.get(name, default))",
        "def _w(name: str, default: float) -> float:\n    return float(ACTIVE_WEIGHTS.get(name, default))",
    )
    main_text = main_text.replace(
        "    posture = _posture(obs_dict)\n",
        "    global ACTIVE_WEIGHTS\n    ACTIVE_WEIGHTS = _choose_profile(obs_dict)\n    posture = _posture(obs_dict)\n",
        1,
    )
    insert_after = "def _players(obs: dict):\n"
    choose_profile = """
def _opponent_card_ids(obs: dict) -> set[int]:
    current, your, us, them = _players(obs)
    ids = set()
    for zone in ("active", "bench", "discard"):
        for card in _zone_cards(them, zone):
            card_id = card.get("id")
            if isinstance(card_id, int):
                ids.add(card_id)
    return ids


def _choose_profile(obs: dict) -> dict:
    ids = _opponent_card_ids(obs)

    def profile(name: str) -> dict:
        return WEIGHT_PROFILES.get(name) or WEIGHT_PROFILES["default"]

    if ids & {673, 674, 675, 676, 677, 678, 1102, 1141, 1142, 1192}:
        return profile("lucario")
    if ids & {741, 742, 743, 305, 66, 1231, 1079, 1156}:
        return profile("alakazam")
    if ids & {119, 120, 121}:
        return profile("nursrijan")
    if ids & {1252, 1123}:
        return profile("crustle")
    if ids:
        return profile("generic")
    return profile("default")


"""
    main_text = main_text.replace(insert_after, choose_profile + insert_after, 1)
    main_text = re.sub(
        r"^STRATEGY = .*$",
        f"STRATEGY = {strategy!r}",
        main_text,
        count=1,
        flags=re.MULTILINE,
    )
    (output_dir / "main.py").write_text(main_text, encoding="utf-8")
    shutil.copyfile(base_deck, output_dir / "deck.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an adaptive shell666 profile-selector candidate.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--base-main", type=Path, default=BASE_MAIN)
    parser.add_argument("--base-deck", type=Path, default=BASE_DECK)
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Override or add a profile as name=path/to/main.py. Defaults are used unless overridden.",
    )
    parser.add_argument("--strategy", default="adaptive shell666 profile selector from public-pool coverage")
    args = parser.parse_args()

    profile_sources = dict(DEFAULT_PROFILE_SOURCES)
    for spec in args.profile:
        if "=" not in spec:
            raise ValueError(f"profile override must be name=path, got {spec!r}")
        name, value = spec.split("=", 1)
        profile_sources[name.strip()] = Path(value.strip())

    build(
        args.output_dir,
        profile_sources=profile_sources,
        base_main=args.base_main,
        base_deck=args.base_deck,
        strategy=args.strategy,
    )


if __name__ == "__main__":
    main()
