from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.meta_archetypes import classify_deck
from ptcg.native_eval import smoke_native_agent_vs_agent
from ptcg.public_notebook_parser import NotebookArtifacts, extract_notebook_artifacts


def _safe_dir(ref: str) -> str:
    return ref.replace("/", "__").replace("-", "_")


def _read_metadata(kernel_dir: Path) -> dict[str, Any]:
    path = kernel_dir / "kernel-metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _find_notebook(kernel_dir: Path) -> Path | None:
    notebooks = sorted(kernel_dir.glob("*.ipynb"))
    return notebooks[0] if notebooks else None


def _patch_main_for_local_native(source: str) -> str:
    patched = source.replace(
        "sys.path.append(glob.glob('/kaggle/input/**/cg-lib', recursive=True)[0])",
        "# local native evaluator supplies data/official on sys.path",
    )
    patched = patched.replace(
        "sys.path.append(glob.glob('/kaggle/input/competitions/pokemon-tcg-ai-battle/**/cg', recursive=True)[0])",
        "# local native evaluator supplies data/official on sys.path",
    )
    patched = re.sub(
        r"import glob\s*\n\s*# local native evaluator supplies data/official on sys\.path\s*\n",
        "",
        patched,
    )
    return patched


def _write_bundle(
    *,
    artifacts: NotebookArtifacts,
    metadata: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    ref = str(metadata.get("id") or artifacts.notebook_path.parent.name)
    title = str(metadata.get("title") or ref)
    output_dir = output_root / _safe_dir(ref)
    output_dir.mkdir(parents=True, exist_ok=True)
    main_path = output_dir / "main.py"
    deck_path = output_dir / "deck.csv"
    if artifacts.main_py is None:
        raise ValueError("no main.py writefile found")
    if artifacts.deck_ids is None or len(artifacts.deck_ids) != 60:
        raise ValueError("no 60-card deck found")
    main_path.write_text(_patch_main_for_local_native(artifacts.main_py), encoding="utf-8")
    deck_text = "\n".join(str(card_id) for card_id in artifacts.deck_ids) + "\n"
    deck_path.write_text(deck_text, encoding="utf-8")
    (output_dir / "lucario_deck.csv").write_text(deck_text, encoding="utf-8")
    archetype = classify_deck(artifacts.deck_ids)
    return {
        "ref": ref,
        "title": title,
        "source_url": f"https://www.kaggle.com/code/{ref}",
        "kind": "public",
        "archetype": archetype.primary,
        "tags": list(archetype.tags),
        "evidence": list(archetype.evidence),
        "main_path": str(main_path),
        "deck_path": str(deck_path),
        "strategy_chars": len(artifacts.strategy_text),
        "ok": False,
        "errors": [],
    }


def _smoke_row(row: dict[str, Any], *, smoke_games: int, seed: int) -> dict[str, Any]:
    if smoke_games <= 0:
        row["ok"] = Path(row["main_path"]).exists() and Path(row["deck_path"]).exists()
        return row
    result = smoke_native_agent_vs_agent(
        candidate_main_path=Path("artifacts/submission_champion/main.py"),
        candidate_deck_path=Path("artifacts/submission_champion/deck.csv"),
        opponent_main_path=Path(row["main_path"]),
        opponent_deck_path=Path(row["deck_path"]),
        games=smoke_games,
        seed=seed,
    )
    row["smoke"] = {
        "games": result.games,
        "finished": result.finished,
        "candidate_wins": result.wins,
        "candidate_losses": result.losses,
        "draws": result.draws,
        "errors": list(result.errors),
    }
    if result.errors:
        row["errors"].extend(result.errors)
    row["ok"] = result.finished > 0 and not result.errors
    return row


def build_public_meta_opponents(
    *,
    kernel_root: Path,
    output: Path,
    opponent_root: Path,
    smoke_games: int,
    seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, kernel_dir in enumerate(sorted(path for path in kernel_root.iterdir() if path.is_dir())):
        metadata = _read_metadata(kernel_dir)
        notebook_path = _find_notebook(kernel_dir)
        ref = str(metadata.get("id") or kernel_dir.name)
        title = str(metadata.get("title") or ref)
        if notebook_path is None:
            rows.append(
                {
                    "ref": ref,
                    "title": title,
                    "source_url": f"https://www.kaggle.com/code/{ref}",
                    "kind": "public",
                    "archetype": "unknown",
                    "tags": [],
                    "main_path": None,
                    "deck_path": None,
                    "ok": False,
                    "errors": ["no notebook found"],
                }
            )
            continue
        try:
            artifacts = extract_notebook_artifacts(notebook_path)
            row = _write_bundle(artifacts=artifacts, metadata=metadata, output_root=opponent_root)
            row = _smoke_row(row, smoke_games=smoke_games, seed=seed + index)
            rows.append(row)
        except Exception as exc:
            rows.append(
                {
                    "ref": ref,
                    "title": title,
                    "source_url": f"https://www.kaggle.com/code/{ref}",
                    "kind": "public",
                    "archetype": "unknown",
                    "tags": [],
                    "main_path": None,
                    "deck_path": None,
                    "ok": False,
                    "errors": [f"{type(exc).__name__}:{exc}"],
                }
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and smoke-test public Kaggle PTCG opponent bundles.")
    parser.add_argument("--kernel-root", type=Path, default=Path("artifacts/public_meta/kernels"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/public_meta/opponents_manifest.json"))
    parser.add_argument("--opponent-root", type=Path, default=Path("artifacts/public_meta/opponents"))
    parser.add_argument("--smoke-games", type=int, default=1)
    parser.add_argument("--seed", type=int, default=9501)
    args = parser.parse_args()

    rows = build_public_meta_opponents(
        kernel_root=args.kernel_root,
        output=args.output,
        opponent_root=args.opponent_root,
        smoke_games=args.smoke_games,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(rows),
                "ok": sum(1 for row in rows if row.get("ok")),
                "dragapult_ok": sum(1 for row in rows if row.get("ok") and "dragapult" in row.get("tags", [])),
                "failures": [row for row in rows if not row.get("ok")],
            }
        )
    )


if __name__ == "__main__":
    main()
