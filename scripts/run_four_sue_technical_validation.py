#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.core import BenchmarkRunner, RunConfig
from runner.adapters import (
    OpenAIResponsesAdapter,
    AnthropicMessagesAdapter,
    GeminiInteractionsAdapter,
    XAIResponsesAdapter,
)


SUE_CONTRACTS = {
    "openai": {
        "sue": "SUE-1",
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "adapter": OpenAIResponsesAdapter,
        "provider_parameters": {
            "reasoning": {"effort": "max"},
            "max_output_tokens": 128000,
        },
    },
    "anthropic": {
        "sue": "SUE-2",
        "provider": "anthropic",
        "model": "claude-opus-5",
        "adapter": AnthropicMessagesAdapter,
        "provider_parameters": {
            "max_tokens": 128000,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "max"},
        },
    },
    "gemini": {
        "sue": "SUE-3",
        "provider": "gemini",
        "model": "gemini-3.1-pro-preview",
        "adapter": GeminiInteractionsAdapter,
        "provider_parameters": {
            "generation_config": {
                "thinking_level": "high",
                "max_output_tokens": 65536,
            },
        },
    },
    "xai": {
        "sue": "SUE-4",
        "provider": "xai",
        "model": "grok-4.6",
        "adapter": XAIResponsesAdapter,
        "provider_parameters": {
            "reasoning": {"effort": "xhigh"},
        },
    },
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class ProgressReporter:
    """Observational terminal progress for a PsychSafe-Eval administration."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.run_started = self.clock()
        self.turn_started = None

    def __call__(self, event):
        now = self.clock()
        kind = event["event"]
        completed = int(event["completed_turns"])
        total = int(event["total_turns"])
        case_id = event["case_id"]
        turn_id = event["turn_id"]

        if kind == "turn_started":
            self.turn_started = now
            percent = (completed / total * 100.0) if total else 0.0
            print(
                f"[{completed:02d}/{total:02d} | {percent:0.1f}%] "
                f"{case_id} / {turn_id} — requesting...",
                flush=True,
            )
            return

        if kind == "turn_completed":
            percent = (completed / total * 100.0) if total else 100.0
            call_elapsed = (
                now - self.turn_started
                if self.turn_started is not None
                else 0.0
            )
            run_elapsed = now - self.run_started
            print(
                f"[{completed:02d}/{total:02d} | {percent:0.1f}%] "
                f"{case_id} / {turn_id} — completed in "
                f"{call_elapsed:0.1f}s | run {run_elapsed:0.1f}s",
                flush=True,
            )
            self.turn_started = None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "PsychSafe-Eval Phase 12.3 prospectively excluded 20-case "
            "four-SUE technical validation."
        )
    )
    parser.add_argument(
        "--sue",
        choices=list(SUE_CONTRACTS),
        required=True,
        help="Frozen SUE administration to validate.",
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        metavar="RUN_DIRECTORY",
        help=(
            "Resume a previously checkpointed technical-validation run "
            "from its existing run directory."
        ),
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
        # Create the durable working directory before the first provider call.
        run_dir = (
            ROOT
            / "results"
            / "runs"
            / f"phase12.3-technical-validation-{args.sue}-{utc_stamp()}"
        )
        run_dir.mkdir(parents=True, exist_ok=False)
        resume = False
    else:
        run_dir = args.resume.expanduser().resolve()
        if not run_dir.is_dir():
            parser.error(
                f"--resume directory does not exist: {run_dir}"
            )
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

    validation_meta = {
        "phase": "12.3",
        "validation_type": "four-SUE 20-case technical validation",
        "prospectively_excluded_from_benchmark_results": True,
        "purpose": (
            "implementation and administration defect detection only; "
            "not benchmark scoring, model comparison, case redesign, "
            "or evidence for modifying canonical cases"
        ),
        "sue": contract["sue"],
        "provider": contract["provider"],
        "model": contract["model"],
        "seed": args.seed,
        "run_id": record.run_id,
        "run_status": record.status,
        "execution_record": "execution.json",
        "checkpoint_record": "checkpoint.json",
        "frozen_provider_parameters": contract["provider_parameters"],
        "canonical_suite_exposure": (
            "PSY-001 through PSY-020 intentionally administered for "
            "prospectively excluded technical validation"
        ),
    }

    (run_dir / "TECHNICAL_VALIDATION_METADATA.json").write_text(
        json.dumps(validation_meta, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(validation_meta, indent=2))
    return 0 if record.status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
