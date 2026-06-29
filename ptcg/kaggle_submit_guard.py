from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ERROR_PATTERNS = (
    re.compile(r"\b[45]\d\d\s+Client Error\b", re.IGNORECASE),
    re.compile(r"\bBad Request\b", re.IGNORECASE),
    re.compile(r"\bCould not submit\b", re.IGNORECASE),
    re.compile(r"\bTraceback\b", re.IGNORECASE),
)

REF_RE = re.compile(r"(?m)^\s*(\d{6,})\s+")
STATUS_RE_TEMPLATE = r"(?m)^\s*{ref}\s+.*?SubmissionStatus\.([A-Z_]+)\b"


def contains_submit_error(text: str) -> bool:
    return any(pattern.search(text) for pattern in ERROR_PATTERNS)


def first_submission_ref(text: str) -> str | None:
    match = REF_RE.search(text)
    return match.group(1) if match else None


def submission_status_for_ref(text: str, ref: str) -> str | None:
    pattern = re.compile(STATUS_RE_TEMPLATE.format(ref=re.escape(ref)))
    match = pattern.search(text)
    return match.group(1) if match else None


def _read(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if b"\x00" in data[:200]:
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Kaggle submit/list CLI output.")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-output")
    check.add_argument("--path", type=Path, required=True)

    first = sub.add_parser("first-ref")
    first.add_argument("--path", type=Path, required=True)

    status = sub.add_parser("status")
    status.add_argument("--path", type=Path, required=True)
    status.add_argument("--ref", required=True)

    args = parser.parse_args(argv)
    text = _read(args.path)

    if args.command == "check-output":
        if contains_submit_error(text):
            print("kaggle_submit_error_detected", file=sys.stderr)
            return 1
        return 0
    if args.command == "first-ref":
        ref = first_submission_ref(text)
        if ref is None:
            return 1
        print(ref)
        return 0
    if args.command == "status":
        current_status = submission_status_for_ref(text, args.ref)
        if current_status is None:
            return 1
        print(current_status)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
