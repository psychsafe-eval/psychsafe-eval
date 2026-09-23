#!/usr/bin/env python3
"""Live synthetic/non-benchmark smoke test for the xAI stateless adapter."""
from __future__ import annotations

import json

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.adapters import XAIResponsesAdapter


def main() -> None:
    adapter = XAIResponsesAdapter()
    params = {"reasoning": {"effort": "xhigh"}}

    r1 = adapter.generate(
        model="grok-4.6",
        messages=[{
            "role": "user",
            "content": "Remember the code word ORCHID. Reply with exactly: TURN1_OK",
        }],
        parameters=params,
    )
    native = r1.provider_metadata["assistant_message_content"]
    r2 = adapter.generate(
        model="grok-4.6",
        messages=[
            {"role": "user", "content": "Remember the code word ORCHID. Reply with exactly: TURN1_OK"},
            {"role": "assistant", "content": native},
            {"role": "user", "content": "Reply with only the code word I asked you to remember."},
        ],
        parameters=params,
    )

    report = {
        "synthetic_non_benchmark_smoke": True,
        "model": "grok-4.6",
        "turn1_output": r1.substantive_output,
        "turn2_output": r2.substantive_output,
        "turn1_status": r1.finish_info.get("status"),
        "turn2_status": r2.finish_info.get("status"),
        "turn1_usage": r1.provider_metadata.get("usage"),
        "turn2_usage": r2.provider_metadata.get("usage"),
        "turn1_item_types": [x.get("type") for x in r1.provider_metadata["assistant_message_content"]],
        "turn2_item_types": [x.get("type") for x in r2.provider_metadata["assistant_message_content"]],
        "turn1_encrypted_reasoning_present": any(
            x.get("type") == "reasoning" and bool(x.get("encrypted_content"))
            for x in r1.provider_metadata["assistant_message_content"]
        ),
        "turn2_encrypted_reasoning_present": any(
            x.get("type") == "reasoning" and bool(x.get("encrypted_content"))
            for x in r2.provider_metadata["assistant_message_content"]
        ),
        "store": False,
        "reasoning_effort": "xhigh",
        "include": ["reasoning.encrypted_content"],
    }
    print(json.dumps(report, indent=2))

    if r1.substantive_output.strip() != "TURN1_OK":
        raise SystemExit("Turn 1 synthetic contract failed.")
    if r2.substantive_output.strip() != "ORCHID":
        raise SystemExit("Turn 2 stateless continuation failed.")


if __name__ == "__main__":
    main()
