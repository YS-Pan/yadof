"""Thin v11 adapter for the generic PCA/SVD experiment runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from .experiment_runtime.linear_subspace import ARM_IDS, preflight, run_partition
else:
    from experiment_runtime.linear_subspace import ARM_IDS, preflight, run_partition


PLAN = (
    Path(__file__).parent
    / "preregistrations"
    / "20260828-pca-svd-linear-subspace-v11"
    / "linear_subspace_plan.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "preflight", "run"))
    parser.add_argument("--partition-manifest")
    parser.add_argument("--output")
    parser.add_argument("--allow-measured-run", action="store_true")
    args = parser.parse_args()
    if args.mode == "plan":
        payload = {
            "plan": json.loads(PLAN.read_text(encoding="utf-8")),
            "arm_ids": list(ARM_IDS),
            "write_performed": False,
        }
    else:
        if not args.partition_manifest:
            parser.error("preflight/run requires --partition-manifest")
        if args.mode == "preflight":
            payload = preflight(args.partition_manifest)
        else:
            if not args.allow_measured_run:
                parser.error("run requires --allow-measured-run and manifest authority")
            payload = run_partition(args.partition_manifest)
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        if args.mode != "run":
            parser.error("only an authorized measured run may write --output")
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
