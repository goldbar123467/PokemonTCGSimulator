from __future__ import annotations

from typing import Any


def wilson_interval(wins: int, total: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    phat = float(wins) / float(total)
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (phat + z2 / (2.0 * total)) / denominator
    margin = (z / denominator) * ((phat * (1.0 - phat) / total + z2 / (4.0 * total * total)) ** 0.5)
    return round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)


def summarize_counts(
    *,
    games: int,
    finished: int,
    wins: int,
    losses: int,
    draws: int,
    errors: int,
    invalid_actions: int,
    timeouts: int,
) -> dict[str, Any]:
    crash_count = max(int(errors) - int(invalid_actions) - int(timeouts), 0)
    lower, upper = wilson_interval(int(wins), int(finished))
    return {
        "games": int(games),
        "finished": int(finished),
        "wins": int(wins),
        "losses": int(losses),
        "draws": int(draws),
        "errors": int(errors),
        "invalid_actions": int(invalid_actions),
        "timeouts": int(timeouts),
        "crash_count": crash_count,
        "win_rate": _rate(int(wins), int(finished)),
        "lower_ci": lower,
        "upper_ci": upper,
        "invalid_action_rate": _rate(int(invalid_actions), int(games)),
        "timeout_rate": _rate(int(timeouts), int(games)),
        "crash_rate": _rate(crash_count, int(games)),
    }


def row_stats(row: dict[str, Any]) -> dict[str, Any]:
    return summarize_counts(
        games=_to_int(row.get("games")),
        finished=_to_int(row.get("finished", row.get("games"))),
        wins=_to_int(row.get("wins")),
        losses=_to_int(row.get("losses")),
        draws=_to_int(row.get("draws")),
        errors=_to_int(row.get("errors")),
        invalid_actions=_to_int(row.get("invalid_actions")),
        timeouts=_to_int(row.get("timeouts")),
    )


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_counts(
        games=sum(_to_int(row.get("games")) for row in rows),
        finished=sum(_to_int(row.get("finished", row.get("games"))) for row in rows),
        wins=sum(_to_int(row.get("wins")) for row in rows),
        losses=sum(_to_int(row.get("losses")) for row in rows),
        draws=sum(_to_int(row.get("draws")) for row in rows),
        errors=sum(_to_int(row.get("errors")) for row in rows),
        invalid_actions=sum(_to_int(row.get("invalid_actions")) for row in rows),
        timeouts=sum(_to_int(row.get("timeouts")) for row in rows),
    )


def _rate(count: int, total: int) -> float:
    return round(float(count) / float(total), 6) if total else 0.0


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))
