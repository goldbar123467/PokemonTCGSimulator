from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Archetype:
    primary: str
    tags: tuple[str, ...]
    evidence: tuple[str, ...]


def classify_deck(deck_ids: Iterable[int]) -> Archetype:
    ids = set(int(card_id) for card_id in deck_ids)
    if {119, 120, 121}.issubset(ids):
        return Archetype("dragapult_spread", ("dragapult", "spread"), ("contains 119/120/121 line",))
    if ids & {878, 879, 1171}:
        return Archetype(
            "hop_trevenant",
            ("hop_trevenant", "hop", "trevenant", "control"),
            ("contains Hop/Trevenant ids",),
        )
    if ids & {741, 742, 743}:
        return Archetype(
            "alakazam",
            ("alakazam", "psychic", "control"),
            ("contains Abra/Kadabra/Alakazam ids",),
        )
    if ids & {1219, 1220} or {1219, 1122}.issubset(ids):
        return Archetype(
            "team_rocket_petrel",
            ("team_rocket", "petrel", "disruption"),
            ("contains Team Rocket Petrel/Transceiver ids",),
        )
    if ids & {1030, 1031} or (17 in ids and 1229 in ids):
        return Archetype(
            "mega_starmie",
            ("starmie", "spread", "water"),
            ("contains Mega Starmie/Ignition Energy ids",),
        )
    if ids & {169, 190}:
        return Archetype(
            "archaludon",
            ("archaludon", "duraludon", "metal", "direct_aggression"),
            ("contains Duraludon/Archaludon ids",),
        )
    if ids & {673, 674, 675, 676, 677, 678}:
        return Archetype("lucario", ("lucario", "direct_aggression"), ("contains Lucario family ids",))
    if ids & {112, 305, 306, 235}:
        return Archetype("spread_unknown", ("spread",), ("contains known spread/support ids",))
    return Archetype("unknown", (), ())
