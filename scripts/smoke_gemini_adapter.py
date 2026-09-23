#!/usr/bin/env python3
"""Two-turn synthetic Gemini adapter smoke test. No benchmark case content."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.adapters import GeminiInteractionsAdapter


def main() -> int:
    adapter = GeminiInteractionsAdapter()
    params = {
        "generation_config": {
            "thinking_level": "high",
            "max_output_tokens": 65536,
        }
    }
    history = [{"role": "user", "content": "Remember the synthetic code word ORCHID. Reply exactly: TURN1_OK"}]
    first = adapter.generate(model="gemini-3.1-pro-preview", messages=history, parameters=params)
    history.append({"role": "assistant", "content": first.provider_metadata["assistant_message_content"]})
    history.append({"role": "user", "content": "What synthetic code word did I ask you to remember? Reply with only that word."})
    second = adapter.generate(model="gemini-3.1-pro-preview", messages=history, parameters=params)

    report = {
        "synthetic_non_benchmark_smoke": True,
        "model": second.provider_metadata.get("model"),
        "turn1_output": first.substantive_output,
        "turn2_output": second.substantive_output,
        "turn1_status": first.finish_info.get("status"),
        "turn2_status": second.finish_info.get("status"),
        "turn1_usage": first.provider_metadata.get("usage"),
        "turn2_usage": second.provider_metadata.get("usage"),
        "turn1_step_types": [s.get("type") for s in first.provider_metadata["assistant_message_content"]],
        "turn2_step_types": [s.get("type") for s in second.provider_metadata["assistant_message_content"]],
        "store": False,
        "thinking_level": "high",
        "max_output_tokens": 65536,
    }
    print(json.dumps(report, indent=2))
    return 0 if second.substantive_output.strip().upper() == "ORCHID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
