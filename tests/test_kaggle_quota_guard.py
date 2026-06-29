from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from ptcg.kaggle_quota_guard import _competition_attr, count_accepted_today, summarize_quota


def test_count_accepted_today_ignores_error_rows_and_other_days() -> None:
    utc_day = date(2026, 6, 25)
    rows = [
        SimpleNamespace(date=datetime(2026, 6, 25, 1, tzinfo=timezone.utc), status="COMPLETE"),
        SimpleNamespace(date="2026-06-25T02:00:00.000Z", status="SUBMITTED"),
        SimpleNamespace(date="2026-06-25T03:00:00.000Z", status="ERROR"),
        SimpleNamespace(date="2026-06-24T23:00:00.000Z", status="COMPLETE"),
    ]

    assert count_accepted_today(rows, utc_day) == 2


def test_summarize_quota_marks_reached_at_max_daily_non_error_count() -> None:
    utc_day = date(2026, 6, 25)
    rows = [
        SimpleNamespace(date=f"2026-06-25T0{hour}:00:00.000Z", status="COMPLETE")
        for hour in range(5)
    ]

    summary = summarize_quota(
        competition="pokemon-tcg-ai-battle",
        max_daily_submissions=5,
        submissions=rows,
        utc_day=utc_day,
    )

    assert summary.accepted_today == 5
    assert summary.remaining == 0
    assert summary.quota_reached is True


def test_competition_attr_reads_kaggle_snake_case_private_fields() -> None:
    competition = SimpleNamespace(_max_daily_submissions=5)

    assert _competition_attr(competition, "maxDailySubmissions") == 5
