from __future__ import annotations

from pathlib import Path
import hashlib
import json
import yaml
import pytest

from runner.core import (
    AdapterResult, BenchmarkRunner, RunConfig,
    TechnicalFailure, AdministrationFailure,
)

ROOT = Path(__file__).resolve().parents[1]
MULTI = {"PSY-002": 2, "PSY-004": 2, "PSY-008": 2, "PSY-012": 3, "PSY-015": 3, "PSY-016": 4, "PSY-017": 5, "PSY-018": 3, "PSY-019": 3, "PSY-020": 3}


class DeterministicAdapter:
    name = "mechanical-deterministic"

    def __init__(self):
        self.call_index = 0

    def generate(self, *, model, messages, parameters):
        self.call_index += 1
        text = f"MECHANICAL_RESPONSE_{self.call_index}"
        return AdapterResult(
            raw_response={
                "fixture": True,
                "call_index": self.call_index,
                "messages": [dict(m) for m in messages],
            },
            substantive_output=text,
            finish_info={"reason": "fixture_complete"},
            provider_metadata={"fixture": True, "model": model},
        )


class RefusalLikeAdapter:
    name = "mechanical-refusal-like"

    def __init__(self):
        self.calls = 0

    def generate(self, *, model, messages, parameters):
        self.calls += 1
        return AdapterResult(
            raw_response={"fixture": True, "kind": "refusal_like"},
            substantive_output="MECHANICAL_REFUSAL_LIKE_RESPONSE",
            finish_info={"reason": "refusal_like_fixture"},
        )


class FailTwicePerRequestAdapter:
    """Each unique submitted conversation fails twice, then succeeds."""
    name = "mechanical-fail-twice"

    def __init__(self):
        self.counts = {}

    @staticmethod
    def key(messages):
        return json.dumps(messages, ensure_ascii=False, sort_keys=True)

    def generate(self, *, model, messages, parameters):
        key = self.key(messages)
        n = self.counts.get(key, 0) + 1
        self.counts[key] = n
        if n <= 2:
            raise TechnicalFailure("MECHANICAL_TRANSIENT_FAILURE")
        return AdapterResult(
            raw_response={"fixture": True, "attempt_for_request": n},
            substantive_output="MECHANICAL_RECOVERY_RESPONSE",
        )


class AlwaysTechnicalFailureAdapter:
    name = "mechanical-always-fail"

    def generate(self, *, model, messages, parameters):
        raise TechnicalFailure("MECHANICAL_PERSISTENT_FAILURE")


def _manifest():
    return yaml.safe_load((ROOT / "cases/manifest.yaml").read_text(encoding="utf-8"))


def test_authoritative_suite_integrity_and_manifest_contract():
    manifest = _manifest()
    entries = manifest["cases"]
    assert len(entries) == 20
    assert len({e["id"] for e in entries}) == 20
    assert sum(e["structure"] == "single_turn" for e in entries) == 10
    assert sum(e["structure"] == "multi_turn" for e in entries) == 10
    assert {e["id"]: e["turn_count"] for e in entries if e["turn_count"] > 1} == MULTI

    for entry in entries:
        case_path = ROOT / "cases" / entry["path"]
        rubric_path = ROOT / "cases" / entry["rubric_path"]
        case_doc = yaml.safe_load(case_path.read_text(encoding="utf-8"))
        rubric_doc = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
        # Manifest digests are canonical serialization digests embedded in each
        # document, not raw-file SHA-256 values. Raw byte integrity is validated
        # independently against the repository SHA256SUMS authority.
        assert case_doc["integrity"]["content_sha256"] == entry["content_sha256"]
        assert rubric_doc["integrity"]["rubric_sha256"] == entry["rubric_sha256"]


def test_full_20_case_end_to_end_execution_and_history_exactness():
    cfg = RunConfig(provider="fixture", model="fixture", seed=115)
    rec = BenchmarkRunner(ROOT, DeterministicAdapter()).run(cfg)
    assert rec.status == "complete"
    assert len(rec.cases) == 20

    manifest = _manifest()
    canonical = {}
    for entry in manifest["cases"]:
        canonical[entry["id"]] = yaml.safe_load(
            (ROOT / "cases" / entry["path"]).read_text(encoding="utf-8")
        )

    for case_rec in rec.cases:
        case = canonical[case_rec.case_id]
        assert len(case_rec.turns) == case["structure"]["turn_count"]
        for i, turn_rec in enumerate(case_rec.turns):
            # Current user turn is exact canonical content.
            assert turn_rec.submitted_messages[-1] == {
                "role": "user",
                "content": case["turns"][i]["content"],
            }
            # Complete prior history is retained; no cross-case context.
            assert len(turn_rec.submitted_messages) == 2 * i + 1
            assert turn_rec.submitted_messages[0]["role"] == "user"


def test_randomization_is_reproducible_by_seed_and_changes_across_seed():
    a = BenchmarkRunner(ROOT, DeterministicAdapter()).run(
        RunConfig(provider="fixture", model="fixture", seed=111)
    )
    b = BenchmarkRunner(ROOT, DeterministicAdapter()).run(
        RunConfig(provider="fixture", model="fixture", seed=111)
    )
    c = BenchmarkRunner(ROOT, DeterministicAdapter()).run(
        RunConfig(provider="fixture", model="fixture", seed=112)
    )
    assert a.randomized_case_order == b.randomized_case_order
    assert a.randomized_case_order != c.randomized_case_order


def test_every_request_can_recover_on_third_attempt_without_extra_retry():
    rec = BenchmarkRunner(
        ROOT,
        FailTwicePerRequestAdapter(),
        sleeper=lambda _: None,
    ).run(
        RunConfig(provider="fixture", model="fixture", seed=9)
    )
    assert rec.status == "complete"
    for case in rec.cases:
        for turn in case.turns:
            assert [a.status for a in turn.attempts] == [
                "technical_failure", "technical_failure", "success"
            ]
            assert turn.selected_attempt == 3


def test_substantive_refusal_like_output_is_never_rerolled():
    adapter = RefusalLikeAdapter()
    rec = BenchmarkRunner(ROOT, adapter).run(
        RunConfig(provider="fixture", model="fixture", seed=4)
    )
    expected_turns = sum(e["turn_count"] for e in _manifest()["cases"])
    assert adapter.calls == expected_turns
    assert all(
        len(turn.attempts) == 1 and turn.attempts[0].status == "success"
        for case in rec.cases for turn in case.turns
    )


def test_persistent_technical_failure_stops_each_case_at_failed_turn():
    rec = BenchmarkRunner(
        ROOT,
        AlwaysTechnicalFailureAdapter(),
        sleeper=lambda _: None,
    ).run(
        RunConfig(provider="fixture", model="fixture", seed=6)
    )
    assert rec.status == "complete_with_failures"
    assert len(rec.cases) == 20
    for case in rec.cases:
        assert case.status == "technical_failure"
        assert len(case.turns) == 1
        assert len(case.turns[0].attempts) == 3


def test_execution_record_round_trip_preserves_raw_and_normalized(tmp_path):
    rec = BenchmarkRunner(ROOT, DeterministicAdapter()).run(
        RunConfig(provider="fixture", model="fixture", seed=12)
    )
    out = tmp_path / "execution.json"
    BenchmarkRunner.write_execution_record(rec, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["randomization_seed"] == 12
    assert len(loaded["cases"]) == 20
    first_attempt = loaded["cases"][0]["turns"][0]["attempts"][0]
    assert first_attempt["raw_response"]["fixture"] is True
    assert first_attempt["substantive_output"].startswith("MECHANICAL_RESPONSE_")


def test_inference_code_has_no_rubric_evidence_or_scoring_imports():
    core_files = list((ROOT / "runner/core").glob("*.py"))
    adapter_files = list((ROOT / "runner/adapters").glob("*.py"))
    executable_sources = "\n".join(
        p.read_text(encoding="utf-8") for p in core_files + adapter_files
    )
    forbidden_imports = (
        "from rubrics", "import rubrics",
        "from evidence", "import evidence",
        "from evaluator", "import evaluator",
    )
    assert all(token not in executable_sources for token in forbidden_imports)
    assert "CSE" not in executable_sources
    assert "score_criterion" not in executable_sources


def test_no_live_credentials_are_required_for_mechanical_suite(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rec = BenchmarkRunner(ROOT, DeterministicAdapter()).run(
        RunConfig(provider="fixture", model="fixture", seed=14)
    )
    assert rec.status == "complete"
