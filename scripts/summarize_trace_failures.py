from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.trace_analysis import write_trace_failure_summary


def _trace_paths(paths: list[Path], trace_dir: Path | None, output_path: Path) -> list[Path]:
    output: list[Path] = []
    output.extend(paths)
    if trace_dir is not None:
        output.extend(sorted(trace_dir.glob("*.json")))
    unique = []
    seen = set()
    resolved_output = output_path.resolve()
    for path in output:
        resolved = path.resolve()
        if resolved == resolved_output:
            continue
        if resolved not in seen:
            unique.append(path)
            seen.add(resolved)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize native trace failure modes for public-agent practice runs.")
    parser.add_argument("--trace", type=Path, action="append", default=[], help="A trace JSON file from trace_public_matchup.py.")
    parser.add_argument("--trace-dir", type=Path, help="Directory containing trace JSON files.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    paths = _trace_paths(args.trace, args.trace_dir, args.output)
    if not paths:
        raise SystemExit("no trace files supplied")
    summary = write_trace_failure_summary(paths, args.output)
    aggregate = summary["aggregate"]
    print(
        "trace_summary "
        f"reports={aggregate.get('reports', 0)} "
        f"wins={aggregate.get('wins', 0)} "
        f"losses={aggregate.get('losses', 0)} "
        f"empty_bench_attacks={aggregate.get('empty_bench_attacks', 0)} "
        f"active_overattach_steps={aggregate.get('active_overattach_steps', 0)} "
        f"board_pressure_steps={aggregate.get('board_pressure_steps', 0)}"
    )


if __name__ == "__main__":
    main()
