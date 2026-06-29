from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


INITIAL_PUBLIC_KERNEL_REFS = [
    "skarin/phantom-dive-or-go-home-a-dragapult-ex-deck",
    "zoli800/top-dragapult-ex-tempo-control-agent",
    "zoli800/dragapult-v3-tempo-ptcg-ai-battle-agent",
    "pilkwang/pokemon-tcg-lucario-v2-strategy-baseline",
    "yu0307/16-real-city-league-top-cut-decks-deck-csv",
    "masamikobayashi/prize-card-tracking-1250-starmie",
    "ryotasueyoshi/rule-based-not-psychic-alakazam-best-5th",
    "pixiux/ptcg-mega-lucario-ex-v63",
]


@dataclass(frozen=True)
class PublicKernelRef:
    ref: str
    title: str
    author: str
    votes: int
    pulled_path: Path
    usage: str


def write_source_ledger(path: Path, refs: list[PublicKernelRef]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Public Source Ledger",
        "",
        "Public notebooks are used for research, opponent gates, and strategy extraction; not copied as final submission.",
        "",
        "| ref | title | author | votes | pulled_path | usage |",
        "|---|---|---|---:|---|---|",
    ]
    for ref in refs:
        lines.append(
            f"| `{ref.ref}` | {ref.title} | {ref.author} | {ref.votes} | `{ref.pulled_path}` | {ref.usage} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
