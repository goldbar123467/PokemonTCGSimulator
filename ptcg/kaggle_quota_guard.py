from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class QuotaSummary:
    competition: str
    utc_date: str
    max_daily_submissions: int | None
    accepted_today: int
    remaining: int | None
    quota_reached: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "competition": self.competition,
            "utc_date": self.utc_date,
            "maxDailySubmissions": self.max_daily_submissions,
            "acceptedToday": self.accepted_today,
            "remaining": self.remaining,
            "quotaReached": self.quota_reached,
        }


def _status_name(submission: Any) -> str:
    status = getattr(submission, "status", None)
    if status is None:
        status = getattr(submission, "_status", "")
    return getattr(status, "name", str(status)).upper()


def _submission_date(submission: Any) -> date | None:
    value = getattr(submission, "date", None)
    if value is None:
        value = getattr(submission, "_date", None)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).astimezone(timezone.utc).date()
        except ValueError:
            return None
    return None


def count_accepted_today(submissions: Iterable[Any], utc_day: date) -> int:
    count = 0
    for submission in submissions:
        if _submission_date(submission) != utc_day:
            continue
        if _status_name(submission) == "ERROR":
            continue
        count += 1
    return count


def summarize_quota(
    *,
    competition: str,
    max_daily_submissions: int | None,
    submissions: Iterable[Any],
    utc_day: date,
) -> QuotaSummary:
    accepted_today = count_accepted_today(submissions, utc_day)
    remaining = None if max_daily_submissions is None else max(0, max_daily_submissions - accepted_today)
    return QuotaSummary(
        competition=competition,
        utc_date=utc_day.isoformat(),
        max_daily_submissions=max_daily_submissions,
        accepted_today=accepted_today,
        remaining=remaining,
        quota_reached=remaining == 0 if remaining is not None else False,
    )


def _competition_attr(competition: Any, name: str) -> Any:
    snake = []
    for char in name:
        if char.isupper():
            snake.append("_")
            snake.append(char.lower())
        else:
            snake.append(char)
    snake_name = "".join(snake)
    for candidate in (name, snake_name, f"_{name}", f"_{snake_name}"):
        value = getattr(competition, candidate, None)
        if value is not None:
            return value
    return None


def _find_competition(api: Any, competition_ref: str) -> Any:
    response = api.competitions_list(search=competition_ref.replace("-", " "))
    competitions = getattr(response, "competitions", getattr(response, "_competitions", []))
    for competition in competitions:
        ref = str(_competition_attr(competition, "ref") or "")
        url = str(_competition_attr(competition, "url") or "")
        if ref.endswith(f"/{competition_ref}") or url.endswith(f"/{competition_ref}") or ref == competition_ref:
            return competition
    raise RuntimeError(f"competition not found in Kaggle API search: {competition_ref}")


def live_quota_summary(competition: str) -> QuotaSummary:
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    info = _find_competition(api, competition)
    max_daily = _competition_attr(info, "maxDailySubmissions")
    submissions = api.competition_submissions(competition)
    return summarize_quota(
        competition=competition,
        max_daily_submissions=int(max_daily) if max_daily is not None else None,
        submissions=submissions,
        utc_day=datetime.now(timezone.utc).date(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Kaggle daily submission quota before upload.")
    parser.add_argument("--competition", required=True)
    args = parser.parse_args(argv)
    summary = live_quota_summary(args.competition)
    print(json.dumps(summary.as_dict(), sort_keys=True))
    return 1 if summary.quota_reached else 0


if __name__ == "__main__":
    raise SystemExit(main())
