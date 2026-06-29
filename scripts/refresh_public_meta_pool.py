from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.public_kaggle_research import INITIAL_PUBLIC_KERNEL_REFS, PublicKernelRef, write_source_ledger


def _safe_dir(ref: str) -> str:
    return ref.replace("/", "__").replace("-", "_")


def pull_kernel(ref: str, output_root: Path) -> Path:
    output_dir = output_root / _safe_dir(ref)
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["kaggle", "kernels", "pull", ref, "-p", str(output_dir), "--metadata"],
        check=True,
        text=True,
    )
    return output_dir


def read_metadata(path: Path, ref: str) -> PublicKernelRef:
    metadata = json.loads((path / "kernel-metadata.json").read_text(encoding="utf-8"))
    return PublicKernelRef(
        ref=ref,
        title=str(metadata.get("title") or ref),
        author=str(metadata.get("id", ref)).split("/")[0],
        votes=int(metadata.get("totalVotes") or metadata.get("votes") or 0),
        pulled_path=path,
        usage="opponent_gate_strategy",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull public Kaggle PTCG notebooks into a local research pool.")
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/public_meta/kernels"))
    parser.add_argument("--ledger", type=Path, default=Path("docs/public-source-ledger.md"))
    parser.add_argument("--refs", nargs="*", default=INITIAL_PUBLIC_KERNEL_REFS)
    args = parser.parse_args()

    pulled = []
    failures = []
    for ref in args.refs:
        try:
            path = pull_kernel(ref, args.output_root)
            pulled.append(read_metadata(path, ref))
        except Exception as exc:
            failures.append({"ref": ref, "error": f"{type(exc).__name__}:{exc}"})
    write_source_ledger(args.ledger, pulled)
    manifest_path = args.output_root.parent / "public_kernel_pull_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "pulled": [
                    {"ref": ref.ref, "title": ref.title, "pulled_path": str(ref.pulled_path), "usage": ref.usage}
                    for ref in pulled
                ],
                "failures": failures,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"pulled": len(pulled), "failures": failures, "manifest": str(manifest_path)}))


if __name__ == "__main__":
    main()
