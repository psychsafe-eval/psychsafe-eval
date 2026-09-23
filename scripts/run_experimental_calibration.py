#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.adapters import AnthropicMessagesAdapter, OpenAIResponsesAdapter
from runner.calibration import ExperimentalCalibrationRunner
from runner.core import RunConfig


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main():
    p = argparse.ArgumentParser(description="PsychSafe-Eval Phase 12.3 experimental candidate calibration (excluded from benchmark results).")
    p.add_argument("--provider", choices=["anthropic", "openai"], required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--max-output-tokens", type=int, default=16000)
    p.add_argument("--max-run-cost-usd", type=float, default=10.00)
    p.add_argument("--effort", choices=["low", "medium", "high", "max"], default=None)
    p.add_argument("--thinking", choices=["adaptive", "disabled"], default=None)
    args = p.parse_args()

    if args.provider == "anthropic":
        adapter = AnthropicMessagesAdapter()
        provider_parameters = {"max_tokens": args.max_output_tokens}
        if args.effort:
            provider_parameters["output_config"] = {"effort": args.effort}
        if args.thinking == "adaptive":
            provider_parameters["thinking"] = {"type": "adaptive"}
        elif args.thinking == "disabled":
            provider_parameters["thinking"] = {"type": "disabled"}
    else:
        if args.effort or args.thinking:
            p.error("--effort/--thinking in this entry point are currently defined for Anthropic calibration only.")
        adapter = OpenAIResponsesAdapter()
        provider_parameters = {"max_output_tokens": args.max_output_tokens}

    config = RunConfig(provider=args.provider, model=args.model, seed=args.seed, provider_parameters=provider_parameters)
    runner = ExperimentalCalibrationRunner(ROOT, adapter)
    if args.provider == "anthropic":
        record = runner.run(
            config, max_cost_usd=args.max_run_cost_usd,
            input_usd_per_mtok=5.0, output_usd_per_mtok=25.0,
        )
    else:
        record = runner.run(config)

    run_dir = ROOT / "results" / "calibration" / f"phase12.3-{utc_stamp()}-{record.run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    runner.write_execution_record(record, run_dir / "execution.json")
    meta = {
        "phase": "12.3",
        "run_type": "experimental_calibration",
        "prospectively_excluded_from_benchmark_results": True,
        "provider": args.provider,
        "model_requested": args.model,
        "seed": args.seed,
        "run_id": record.run_id,
        "run_status": record.status,
        "execution_record": "execution.json",
        "max_output_tokens": args.max_output_tokens,
        "max_run_cost_usd": args.max_run_cost_usd if args.provider == "anthropic" else None,
        "cost_accounting": record.cost_accounting,
    }
    (run_dir / "CALIBRATION_METADATA.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0 if record.status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
