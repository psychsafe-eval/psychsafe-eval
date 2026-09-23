from pathlib import Path

from runner.core import (
    AdapterResult,
    BenchmarkRunner,
    RunConfig,
    TechnicalFailure,
    AdministrationFailure,
    IndeterminateAdministrationFailure,
)


ROOT = Path(__file__).resolve().parents[1]


class EchoFixtureAdapter:
    name = "fixture-echo"
    def generate(self, *, model, messages, parameters):
        return AdapterResult(
            raw_response={"fixture": True, "message_count": len(messages)},
            substantive_output="FIXTURE_RESPONSE",
            finish_info={"reason": "fixture"},
            provider_metadata={"fixture": True},
        )


class FlakyFixtureAdapter:
    name = "fixture-flaky"
    def __init__(self):
        self.calls = 0
    def generate(self, *, model, messages, parameters):
        self.calls += 1
        if self.calls <= 2:
            raise TechnicalFailure("fixture transport failure")
        return AdapterResult(raw_response={"ok": True}, substantive_output="FIXTURE_RESPONSE")


def test_complete_run_has_20_unique_cases_and_fixed_seed_order():
    cfg = RunConfig(provider="fixture", model="fixture", seed=20260917)
    r1 = BenchmarkRunner(ROOT, EchoFixtureAdapter()).run(cfg)
    r2 = BenchmarkRunner(ROOT, EchoFixtureAdapter()).run(cfg)
    assert r1.status == "complete"
    assert len(r1.cases) == 20
    assert len(set(r1.randomized_case_order)) == 20
    assert r1.randomized_case_order == r2.randomized_case_order


def test_multiturn_history_is_preserved_and_fresh_between_cases():
    cfg = RunConfig(provider="fixture", model="fixture", seed=7)
    rec = BenchmarkRunner(ROOT, EchoFixtureAdapter()).run(cfg)
    multi = {c.case_id: c for c in rec.cases if len(c.turns) > 1}
    assert set(multi) == {"PSY-002", "PSY-004", "PSY-008", "PSY-012", "PSY-015", "PSY-016", "PSY-017", "PSY-018", "PSY-019", "PSY-020"}
    for case in multi.values():
        for i, turn in enumerate(case.turns):
            # turn i sees i prior user+assistant pairs plus current user = 2*i+1 messages
            assert len(turn.submitted_messages) == 2 * i + 1
            assert turn.submitted_messages[-1]["role"] == "user"
    for case in rec.cases:
        assert case.turns[0].submitted_messages[0]["role"] == "user"
        assert len(case.turns[0].submitted_messages) == 1


def test_retry_is_limited_to_three_total_attempts_and_success_is_not_rerolled():
    cfg = RunConfig(provider="fixture", model="fixture", seed=1)
    adapter = FlakyFixtureAdapter()
    sleeps = []
    rec = BenchmarkRunner(ROOT, adapter, sleeper=sleeps.append).run(cfg)
    first_turn = rec.cases[0].turns[0]
    assert [a.status for a in first_turn.attempts] == [
        "technical_failure", "technical_failure", "success"
    ]
    assert first_turn.selected_attempt == 3
    assert sleeps == [120.0, 300.0]


def test_execution_record_is_create_only(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=1)
    rec = BenchmarkRunner(ROOT, EchoFixtureAdapter()).run(cfg)
    path = tmp_path / "run.json"
    BenchmarkRunner.write_execution_record(rec, path)
    assert path.exists()
    try:
        BenchmarkRunner.write_execution_record(rec, path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Execution record overwrite should be refused.")


class AlwaysFailFixtureAdapter:
    name = "fixture-always-fail"
    def generate(self, *, model, messages, parameters):
        raise TechnicalFailure("fixture transport failure")


def test_exhausted_technical_failure_is_recorded_without_rerolling_beyond_three():
    cfg = RunConfig(provider="fixture", model="fixture", seed=3)
    sleeps = []
    rec = BenchmarkRunner(
        ROOT,
        AlwaysFailFixtureAdapter(),
        sleeper=sleeps.append,
    ).run(cfg)
    assert rec.status == "complete_with_failures"
    assert len(rec.cases) == 20
    for case in rec.cases:
        assert case.status == "technical_failure"
        assert len(case.turns) == 1
        assert len(case.turns[0].attempts) == 3

    # Each of 20 failed cases sleeps only between attempts 1->2 and 2->3.
    assert sleeps == [120.0, 300.0] * 20


def test_runner_source_does_not_reference_rubric_paths_for_loading():
    loader_source = (ROOT / "runner/core/loader.py").read_text(encoding="utf-8")
    orchestrator_source = (ROOT / "runner/core/orchestrator.py").read_text(encoding="utf-8")
    # Comments may document the isolation boundary; executable path construction may not target rubrics.
    forbidden = ['/"rubrics"', '/ "rubrics"', '"rubrics"/', '"rubrics" /']
    assert all(token not in loader_source for token in forbidden)
    assert all(token not in orchestrator_source for token in forbidden)

# ---------------------------------------------------------------------------
# Phase 12.3 crash-safe checkpoint/resume contract
# ---------------------------------------------------------------------------

import json


class CountingFixtureAdapter:
    name = "fixture-counting"

    def __init__(self):
        self.calls = 0

    def generate(self, *, model, messages, parameters):
        self.calls += 1
        return AdapterResult(
            raw_response={"call": self.calls},
            substantive_output=f"RESPONSE_{self.calls}",
            provider_metadata={
                "assistant_message_content": f"NATIVE_RESPONSE_{self.calls}"
            },
        )


class InterruptAfterSuccessAdapter:
    """Returns one substantive response, then simulates a local interruption."""

    name = "fixture-interrupt-after-success"

    def __init__(self):
        self.calls = 0

    def generate(self, *, model, messages, parameters):
        self.calls += 1
        if self.calls == 1:
            return AdapterResult(
                raw_response={"call": 1},
                substantive_output="FIRST_RESPONSE",
                provider_metadata={
                    "assistant_message_content": "FIRST_NATIVE_RESPONSE"
                },
            )
        raise KeyboardInterrupt("simulated local interruption")


def test_checkpoint_is_written_atomically_and_contains_run_identity(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=17)
    checkpoint = tmp_path / "checkpoint.json"

    runner = BenchmarkRunner(ROOT, CountingFixtureAdapter())
    rec = runner.run(cfg, checkpoint_path=checkpoint, stop_after_turns=1)

    assert checkpoint.exists()
    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert data["run"]["run_id"] == rec.run_id
    assert data["run"]["randomization_seed"] == 17
    assert data["run"]["provider"] == "fixture"
    assert data["run"]["model"] == "fixture"
    assert data["state"]["completed_turns"] == 1
    assert data["state"]["in_flight"] is None
    assert not list(tmp_path.glob("checkpoint.json.tmp*"))


def test_resume_does_not_reroll_persisted_successful_turn(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=19)
    checkpoint = tmp_path / "checkpoint.json"

    first_adapter = CountingFixtureAdapter()
    first_runner = BenchmarkRunner(ROOT, first_adapter)
    first_runner.run(cfg, checkpoint_path=checkpoint, stop_after_turns=1)
    assert first_adapter.calls == 1

    resumed_adapter = CountingFixtureAdapter()
    resumed_runner = BenchmarkRunner(ROOT, resumed_adapter)
    resumed = resumed_runner.run(
        cfg,
        checkpoint_path=checkpoint,
        resume=True,
        stop_after_turns=2,
    )

    assert resumed_adapter.calls == 1
    first_turn = resumed.cases[0].turns[0]
    assert first_turn.substantive_output == "RESPONSE_1"
    assert first_turn.attempts[-1].raw_response == {"call": 1}


def test_resume_reconstructs_exact_provider_native_multiturn_history(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=23)
    checkpoint = tmp_path / "checkpoint.json"

    runner = BenchmarkRunner(ROOT, CountingFixtureAdapter())
    partial = runner.run(cfg, checkpoint_path=checkpoint, stop_after_turns=1)

    first_case_id = partial.randomized_case_order[0]
    manifest, cases = runner.loader.load_cases()
    case_by_id = {_case_id_for_test(c): c for c in cases}

    # This test requires the first randomized case to be multi-turn.
    # If the seed ever changes suite ordering behavior, select a deterministic
    # seed whose first case is multi-turn rather than weakening the assertion.
    assert case_by_id[first_case_id]["structure"]["turn_count"] > 1

    class InspectingAdapter:
        name = "fixture-inspecting"

        def __init__(self):
            self.messages = None

        def generate(self, *, model, messages, parameters):
            self.messages = messages
            return AdapterResult(
                raw_response={"ok": True},
                substantive_output="SECOND_RESPONSE",
                provider_metadata={
                    "assistant_message_content": "SECOND_NATIVE_RESPONSE"
                },
            )

    inspecting = InspectingAdapter()
    resumed = BenchmarkRunner(ROOT, inspecting).run(
        cfg,
        checkpoint_path=checkpoint,
        resume=True,
        stop_after_turns=2,
    )

    assert inspecting.messages is not None
    assert inspecting.messages[1] == {
        "role": "assistant",
        "content": "NATIVE_RESPONSE_1",
    }
    assert resumed.cases[0].turns[0].substantive_output == "RESPONSE_1"


def _case_id_for_test(case):
    c = case.get("case", {})
    return c.get("id") or case.get("id")


class FailOnceThenInterruptAdapter:
    name = "fixture-fail-once-interrupt"

    def __init__(self):
        self.calls = 0

    def generate(self, *, model, messages, parameters):
        self.calls += 1
        if self.calls == 1:
            raise TechnicalFailure("known technical failure")
        raise KeyboardInterrupt("simulated interruption before next result")


def test_persisted_technical_failure_consumes_attempt_on_resume(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=29)
    checkpoint = tmp_path / "checkpoint.json"

    try:
        BenchmarkRunner(
            ROOT,
            FailOnceThenInterruptAdapter(),
            sleeper=lambda _: None,
        ).run(
            cfg, checkpoint_path=checkpoint
        )
    except KeyboardInterrupt:
        pass

    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert data["state"]["in_flight"] is not None

    # The known first technical failure must already be durably represented.
    attempts = data["state"]["current_turn_attempts"]
    assert len(attempts) == 1
    assert attempts[0]["attempt_number"] == 1
    assert attempts[0]["status"] == "technical_failure"


class IndeterminateFixtureAdapter:
    name = "fixture-indeterminate"

    def __init__(self):
        self.calls = 0

    def generate(self, *, model, messages, parameters):
        self.calls += 1
        raise IndeterminateAdministrationFailure(
            "simulated post-dispatch response loss"
        )


def test_indeterminate_administration_preserves_in_flight_without_retry(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=30)
    checkpoint = tmp_path / "checkpoint.json"
    adapter = IndeterminateFixtureAdapter()

    try:
        BenchmarkRunner(ROOT, adapter).run(
            cfg, checkpoint_path=checkpoint
        )
    except IndeterminateAdministrationFailure:
        pass
    else:
        raise AssertionError(
            "Indeterminate administration failure must propagate."
        )

    # The request must not enter the TechnicalFailure retry loop.
    assert adapter.calls == 1

    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert data["state"]["in_flight"] is not None
    assert data["state"]["in_flight"]["attempt_number"] == 1

    # No provider outcome was established, so no AttemptRecord may falsely
    # characterize this request as either a known failure or a success.
    assert data["state"]["current_turn_attempts"] == []


def test_unresolved_in_flight_checkpoint_refuses_automatic_resume(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=31)
    checkpoint = tmp_path / "checkpoint.json"

    try:
        BenchmarkRunner(ROOT, InterruptAfterSuccessAdapter()).run(
            cfg, checkpoint_path=checkpoint
        )
    except KeyboardInterrupt:
        pass

    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert data["state"]["in_flight"] is not None

    adapter = CountingFixtureAdapter()
    try:
        BenchmarkRunner(ROOT, adapter).run(
            cfg, checkpoint_path=checkpoint, resume=True
        )
    except AdministrationFailure as exc:
        assert "in-flight" in str(exc).lower() or "indeterminate" in str(exc).lower()
    else:
        raise AssertionError(
            "Resume must refuse an unresolved in-flight provider request."
        )

    assert adapter.calls == 0


def test_uninterrupted_and_safe_resumed_runs_preserve_same_administration(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=37)

    class DeterministicHistoryAdapter:
        name = "fixture-deterministic-history"

        def generate(self, *, model, messages, parameters):
            marker = f"RESPONSE_FOR_{messages[-1]['content']}"
            return AdapterResult(
                raw_response={"marker": marker},
                substantive_output=marker,
                provider_metadata={"assistant_message_content": marker},
            )

    uninterrupted = BenchmarkRunner(
        ROOT, DeterministicHistoryAdapter()
    ).run(cfg)

    checkpoint = tmp_path / "checkpoint.json"
    BenchmarkRunner(ROOT, DeterministicHistoryAdapter()).run(
        cfg, checkpoint_path=checkpoint, stop_after_turns=7
    )
    resumed = BenchmarkRunner(ROOT, DeterministicHistoryAdapter()).run(
        cfg, checkpoint_path=checkpoint, resume=True
    )

    assert uninterrupted.randomized_case_order == resumed.randomized_case_order
    assert [c.case_id for c in uninterrupted.cases] == [
        c.case_id for c in resumed.cases
    ]
    assert [
        [t.turn_id for t in c.turns] for c in uninterrupted.cases
    ] == [
        [t.turn_id for t in c.turns] for c in resumed.cases
    ]
    assert [
        [t.submitted_messages for t in c.turns] for c in uninterrupted.cases
    ] == [
        [t.submitted_messages for t in c.turns] for c in resumed.cases
    ]


def test_safe_resume_preserves_consumed_technical_failure_attempt_budget(tmp_path):
    cfg = RunConfig(provider="fixture", model="fixture", seed=41)
    checkpoint = tmp_path / "checkpoint.json"

    # Establish a legitimate new-run checkpoint without making a provider call.
    BenchmarkRunner(ROOT, CountingFixtureAdapter()).run(
        cfg,
        checkpoint_path=checkpoint,
        stop_after_turns=0,
    )

    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    first_case_id = data["run"]["randomized_case_order"][0]

    manifest, cases = BenchmarkRunner(
        ROOT, CountingFixtureAdapter()
    ).loader.load_cases()
    case_by_id = {_case_id_for_test(c): c for c in cases}
    first_turn_id = case_by_id[first_case_id]["turns"][0]["id"]

    # Simulate a clean persisted boundary after attempt 1 is known to have
    # failed technically, with no request currently in flight.
    data["state"]["in_flight"] = None
    data["state"]["current_turn"] = {
        "case_id": first_case_id,
        "turn_id": first_turn_id,
    }
    data["state"]["current_turn_attempts"] = [{
        "attempt_number": 1,
        "started_at": "fixture-start",
        "completed_at": "fixture-end",
        "status": "technical_failure",
        "error_type": "TechnicalFailure",
        "error_message": "known persisted failure",
        "raw_response": None,
        "substantive_output": None,
        "finish_info": {},
        "provider_metadata": {},
    }]
    checkpoint.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    class CaptureOneSuccessAdapter:
        name = "fixture-capture-one-success"

        def __init__(self):
            self.calls = 0

        def generate(self, *, model, messages, parameters):
            self.calls += 1
            return AdapterResult(
                raw_response={"ok": True},
                substantive_output="RESUMED_SUCCESS",
                provider_metadata={
                    "assistant_message_content": "RESUMED_NATIVE_SUCCESS"
                },
            )

    adapter = CaptureOneSuccessAdapter()
    resumed = BenchmarkRunner(ROOT, adapter).run(
        cfg,
        checkpoint_path=checkpoint,
        resume=True,
        stop_after_turns=1,
    )

    assert adapter.calls == 1
    first_turn = resumed.cases[0].turns[0]
    assert [a.attempt_number for a in first_turn.attempts] == [1, 2]
    assert [a.status for a in first_turn.attempts] == [
        "technical_failure",
        "success",
    ]
    assert first_turn.selected_attempt == 2


def test_progress_callback_reports_all_turn_boundaries_without_changing_counts():
    cfg = RunConfig(provider="fixture", model="fixture", seed=43)
    events = []

    class ProgressAdapter:
        name = "fixture-progress"

        def generate(self, *, model, messages, parameters):
            marker = f"RESPONSE_FOR_{messages[-1]['content']}"
            return AdapterResult(
                raw_response={"marker": marker},
                substantive_output=marker,
                provider_metadata={"assistant_message_content": marker},
            )

    record = BenchmarkRunner(ROOT, ProgressAdapter()).run(
        cfg,
        progress_callback=lambda event: events.append(dict(event)),
    )

    started = [e for e in events if e["event"] == "turn_started"]
    completed = [e for e in events if e["event"] == "turn_completed"]

    assert len(started) == 40
    assert len(completed) == 40

    assert [e["completed_turns"] for e in started] == list(range(40))
    assert [e["completed_turns"] for e in completed] == list(range(1, 41))

    assert all(e["total_turns"] == 40 for e in started + completed)
    assert completed[-1]["completed_turns"] == 40

    assert record.status == "complete"


def test_progress_callback_does_not_change_model_visible_administration():
    cfg = RunConfig(provider="fixture", model="fixture", seed=47)

    class CapturingAdapter:
        name = "fixture-progress-capture"

        def __init__(self):
            self.calls = []

        def generate(self, *, model, messages, parameters):
            copied = [dict(m) for m in messages]
            self.calls.append({
                "model": model,
                "messages": copied,
                "parameters": dict(parameters),
            })
            marker = f"RESPONSE_FOR_{messages[-1]['content']}"
            return AdapterResult(
                raw_response={"marker": marker},
                substantive_output=marker,
                provider_metadata={"assistant_message_content": marker},
            )

    without_progress = CapturingAdapter()
    record_without = BenchmarkRunner(ROOT, without_progress).run(cfg)

    with_progress = CapturingAdapter()
    events = []
    record_with = BenchmarkRunner(ROOT, with_progress).run(
        cfg,
        progress_callback=lambda event: events.append(dict(event)),
    )

    assert without_progress.calls == with_progress.calls
    assert record_without.randomized_case_order == record_with.randomized_case_order

    assert [
        [t.submitted_messages for t in c.turns]
        for c in record_without.cases
    ] == [
        [t.submitted_messages for t in c.turns]
        for c in record_with.cases
    ]

    assert len(events) == 80


def test_progress_callback_resume_starts_from_persisted_completed_turn_count(
    tmp_path,
):
    cfg = RunConfig(provider="fixture", model="fixture", seed=53)
    checkpoint = tmp_path / "checkpoint.json"

    BenchmarkRunner(ROOT, CountingFixtureAdapter()).run(
        cfg,
        checkpoint_path=checkpoint,
        stop_after_turns=7,
    )

    events = []
    BenchmarkRunner(ROOT, CountingFixtureAdapter()).run(
        cfg,
        checkpoint_path=checkpoint,
        resume=True,
        stop_after_turns=8,
        progress_callback=lambda event: events.append(dict(event)),
    )

    started = [e for e in events if e["event"] == "turn_started"]
    completed = [e for e in events if e["event"] == "turn_completed"]

    assert len(started) == 1
    assert len(completed) == 1
    assert started[0]["completed_turns"] == 7
    assert completed[0]["completed_turns"] == 8
    assert started[0]["total_turns"] == 40
    assert completed[0]["total_turns"] == 40
