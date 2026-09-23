#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.core import BenchmarkRunner, RunConfig
from scripts.run_four_sue_technical_validation import (
    SUE_CONTRACTS,
    ProgressReporter,
    utc_stamp,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PsychSafe-Eval v0.1 official benchmark administration."
    )
    parser.add_argument(
        "--sue",
        choices=list(SUE_CONTRACTS),
        required=True,
        help="Frozen SUE to administer.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="Prospectively locked official case-order seed.",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        metavar="RUN_DIRECTORY",
        help="Resume a previously checkpointed official administration.",
    )
    args = parser.parse_args()

    contract = SUE_CONTRACTS[args.sue]

    config = RunConfig(
        provider=contract["provider"],
        model=contract["model"],
        seed=args.seed,
        provider_parameters=contract["provider_parameters"],
    )

    runner = BenchmarkRunner(ROOT, contract["adapter"]())

    if args.resume is None:
        run_dir = (
            ROOT
            / "results"
            / "runs"
            / f"v0.1-official-{args.sue}-{utc_stamp()}"
        )
        run_dir.mkdir(parents=True, exist_ok=False)
        resume = False
    else:
        run_dir = args.resume.expanduser().resolve()
        if not run_dir.is_dir():
            parser.error(f"--resume directory does not exist: {run_dir}")
        resume = True

    checkpoint_path = run_dir / "checkpoint.json"
    if resume and not checkpoint_path.is_file():
        parser.error(
            f"--resume directory has no checkpoint.json: {run_dir}"
        )

    execution_path = run_dir / "execution.json"
    if execution_path.exists():
        parser.error(
            f"execution.json already exists; run is already finalized: {run_dir}"
        )

    progress = ProgressReporter()

    record = runner.run(
        config,
        checkpoint_path=checkpoint_path,
        resume=resume,
        progress_callback=progress,
    )

    runner.write_execution_record(record, execution_path)

    official_meta = {
        "benchmark": "PsychSafe-Eval",
        "benchmark_version": "v0.1",
        "administration_type": "official benchmark administration",
        "official_benchmark_result": True,
        "technical_validation": False,
        "sue": contract["sue"],
        "provider": contract["provider"],
        "model": contract["model"],
        "seed": args.seed,
        "run_id": record.run_id,
        "run_status": record.status,
        "execution_record": "execution.json",
        "checkpoint_record": "checkpoint.json",
        "frozen_provider_parameters": contract["provider_parameters"],
        "canonical_suite_exposure": "PSY-001 through PSY-020 only",
        "demo_cases_included": False,
    }

    (run_dir / "OFFICIAL_ADMINISTRATION_METADATA.json").write_text(
        json.dumps(official_meta, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(official_meta, indent=2))
    return 0 if record.status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
