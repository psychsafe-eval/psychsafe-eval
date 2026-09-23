#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Make the repository root importable when this file is invoked directly
# (e.g. `python scripts/run_technical_pilot.py ...`) without requiring
# PYTHONPATH or an installed package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.core import BenchmarkRunner, RunConfig
from runner.adapters import OpenAIResponsesAdapter, AnthropicMessagesAdapter


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main():
    p=argparse.ArgumentParser(
        description="PsychSafe-Eval Phase 11.6 real-SUE technical pilot (excluded from benchmark results)."
    )
    p.add_argument("--provider", choices=["openai","anthropic"], required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--max-output-tokens", type=int, default=4096)
    args=p.parse_args()

    if args.provider=="openai":
        adapter=OpenAIResponsesAdapter()
        # Responses API uses max_output_tokens.
        provider_parameters={"max_output_tokens": args.max_output_tokens}
    else:
        adapter=AnthropicMessagesAdapter()
        provider_parameters={"max_tokens": args.max_output_tokens}

    config=RunConfig(
        provider=args.provider,
        model=args.model,
        seed=args.seed,
        provider_parameters=provider_parameters,
    )
    runner=BenchmarkRunner(ROOT, adapter)
    record=runner.run(config)

    run_dir=ROOT/"results"/"runs"/f"technical-pilot-{utc_stamp()}-{record.run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    execution_path=run_dir/"execution.json"
    runner.write_execution_record(record, execution_path)

    pilot_meta={
        "phase":"11.6",
        "pilot_type":"real-SUE technical pilot",
        "prospectively_excluded_from_benchmark_results":True,
        "purpose":"implementation defect detection only; not benchmark scoring or redesign",
        "provider":args.provider,
        "model":args.model,
        "seed":args.seed,
        "run_id":record.run_id,
        "run_status":record.status,
        "execution_record":"execution.json",
    }
    (run_dir/"PILOT_METADATA.json").write_text(
        json.dumps(pilot_meta, indent=2)+"\n", encoding="utf-8"
    )
    print(json.dumps(pilot_meta, indent=2))
    return 0 if record.status=="complete" else 2

if __name__=="__main__":
    raise SystemExit(main())
