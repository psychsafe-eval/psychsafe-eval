from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List
import json
import random
import time

from .loader import SuiteLoader
from .models import (
    AdapterResult, AttemptRecord, CaseExecutionRecord, RunConfig, RunRecord,
    TechnicalFailure, AdministrationFailure, TurnExecutionRecord, utc_now,
)

# NOTE: the odd-looking conditional import above is intentionally avoided below;
# BenchmarkRunner is defined in this module.


def _case_id(case: Dict[str, Any]) -> str:
    c = case.get("case", {})
    return c.get("id") or case.get("id")


def _benchmark_meta(case: Dict[str, Any]) -> tuple[str, str]:
    b = case.get("benchmark", {})
    if isinstance(b, dict):
        return b.get("name", "PsychSafe-Eval"), str(b.get("version", "0.1"))
    return "PsychSafe-Eval", "0.1"


def _structure(case: Dict[str, Any]) -> Dict[str, Any]:
    return case["structure"]


def _turns(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    return case["turns"]


class BenchmarkRunner:
    """Provider-neutral orchestration for one complete PsychSafe-Eval run."""

    RETRY_BACKOFF_SECONDS = (120.0, 300.0)

    def __init__(
        self,
        repo_root: Path,
        adapter: Any,
        *,
        sleeper: Any = time.sleep,
    ):
        self.repo_root = Path(repo_root)
        self.adapter = adapter
        self.loader = SuiteLoader(self.repo_root)
        self._sleeper = sleeper

    @staticmethod
    def _write_checkpoint(
        checkpoint_path: Path,
        record: RunRecord,
        *,
        completed_turns: int,
        in_flight: Dict[str, Any] | None = None,
        current_turn_attempts: List[AttemptRecord] | None = None,
        current_turn: Dict[str, str] | None = None,
    ) -> None:
        """Atomically persist recoverable administration state."""
        checkpoint_path = Path(checkpoint_path)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "checkpoint_version": 1,
            "run": record.to_dict(),
            "state": {
                "completed_turns": completed_turns,
                "in_flight": in_flight,
                "current_turn": (
                    current_turn
                    if current_turn is not None
                    else (
                        {
                            "case_id": in_flight["case_id"],
                            "turn_id": in_flight["turn_id"],
                        }
                        if in_flight is not None
                        else None
                    )
                ),
                "current_turn_attempts": [
                    asdict(a) for a in (current_turn_attempts or [])
                ],
            },
        }

        tmp_path = checkpoint_path.with_name(
            checkpoint_path.name + ".tmp"
        )
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            f.write("\n")
            f.flush()

        tmp_path.replace(checkpoint_path)

    @staticmethod
    def _load_checkpoint(checkpoint_path: Path) -> Dict[str, Any]:
        checkpoint_path = Path(checkpoint_path)
        with checkpoint_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        if payload.get("checkpoint_version") != 1:
            raise AdministrationFailure(
                "Unsupported PsychSafe-Eval checkpoint version."
            )
        if "run" not in payload or "state" not in payload:
            raise AdministrationFailure(
                "Checkpoint is missing required run/state data."
            )
        return payload

    def _call_with_retries(
        self,
        *,
        config: RunConfig,
        messages: List[Dict[str, str]],
        checkpoint_path: Path | None = None,
        checkpoint_record: RunRecord | None = None,
        completed_turns: int = 0,
        case_id: str | None = None,
        turn_id: str | None = None,
        prior_attempts: List[AttemptRecord] | None = None,
    ) -> tuple[List[AttemptRecord], AdapterResult | None]:
        attempts: List[AttemptRecord] = list(prior_attempts or [])

        if len(attempts) >= config.max_attempts:
            return attempts, None

        start_attempt = len(attempts) + 1
        for n in range(start_attempt, config.max_attempts + 1):
            # Persist the exact request boundary before provider contact.
            if checkpoint_path is not None:
                if checkpoint_record is None or case_id is None or turn_id is None:
                    raise AdministrationFailure(
                        "Checkpointed provider calls require run/case/turn identity."
                    )
                self._write_checkpoint(
                    checkpoint_path,
                    checkpoint_record,
                    completed_turns=completed_turns,
                    in_flight={
                        "case_id": case_id,
                        "turn_id": turn_id,
                        "attempt_number": n,
                    },
                    current_turn_attempts=attempts,
                )

            started = utc_now()
            try:
                result = self.adapter.generate(
                    model=config.model,
                    messages=[dict(m) for m in messages],
                    parameters=dict(config.provider_parameters),
                )
                completed = utc_now()

                # Any substantive provider return is accepted as the successful
                # attempt. Content quality/safety/length is never a reroll
                # criterion.
                if not isinstance(result, AdapterResult):
                    raise AdministrationFailure(
                        "Adapter returned an object outside the Phase 11.3 "
                        "AdapterResult contract."
                    )

                attempts.append(AttemptRecord(
                    attempt_number=n,
                    started_at=started,
                    completed_at=completed,
                    status="success",
                    raw_response=result.raw_response,
                    substantive_output=result.substantive_output,
                    finish_info=dict(result.finish_info),
                    provider_metadata=dict(result.provider_metadata),
                ))

                # The successful attempt itself is now known. The caller will
                # immediately persist the completed TurnExecutionRecord before
                # any subsequent provider request.
                return attempts, result

            except TechnicalFailure as exc:
                attempts.append(AttemptRecord(
                    attempt_number=n,
                    started_at=started,
                    completed_at=utc_now(),
                    status="technical_failure",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                ))

                # A known technical failure consumes this attempt durably
                # before another attempt can begin.
                if checkpoint_path is not None:
                    self._write_checkpoint(
                        checkpoint_path,
                        checkpoint_record,
                        completed_turns=completed_turns,
                        in_flight=None,
                        current_turn_attempts=attempts,
                        current_turn={
                            "case_id": case_id,
                            "turn_id": turn_id,
                        },
                    )

                if n == config.max_attempts:
                    return attempts, None

                # Retryable technical failures are durably recorded before
                # waiting. Bounded deterministic backoff avoids immediately
                # repeating transient provider-capacity/rate-limit failures.
                backoff_index = min(
                    n - 1,
                    len(self.RETRY_BACKOFF_SECONDS) - 1,
                )
                self._sleeper(self.RETRY_BACKOFF_SECONDS[backoff_index])

        return attempts, None

    def run(
        self,
        config: RunConfig,
        *,
        checkpoint_path: Path | None = None,
        resume: bool = False,
        stop_after_turns: int | None = None,
        progress_callback: Any | None = None,
    ) -> RunRecord:
        manifest, loaded_cases = self.loader.load_cases()

        ids = [_case_id(c) for c in loaded_cases]
        expected_case_count = int(
            manifest.get("suite", {}).get(
                "case_count", len(manifest.get("cases", []))
            )
        )
        if len(ids) != expected_case_count or len(set(ids)) != expected_case_count:
            raise AdministrationFailure(
                f"A complete v0.1 run requires exactly "
                f"{expected_case_count} unique manifest-listed cases."
            )

        case_by_id = {_case_id(c): c for c in loaded_cases}
        total_turns = sum(len(_turns(c)) for c in loaded_cases)

        if resume:
            if checkpoint_path is None or not Path(checkpoint_path).exists():
                raise AdministrationFailure(
                    "Resume requires an existing checkpoint."
                )

            payload = self._load_checkpoint(checkpoint_path)
            state = payload["state"]

            if state.get("in_flight") is not None:
                raise AdministrationFailure(
                    "Checkpoint contains an unresolved in-flight provider "
                    "request; administration is indeterminate and automatic "
                    "resume is prohibited."
                )

            record = RunRecord.from_dict(payload["run"])

            expected_configuration = {
                "max_attempts": config.max_attempts,
                "system_prompt": config.system_prompt,
                "provider_parameters": config.provider_parameters,
            }
            if (
                record.provider != config.provider
                or record.model != config.model
                or record.randomization_seed != config.seed
                or record.configuration != expected_configuration
            ):
                raise AdministrationFailure(
                    "Resume configuration does not match the checkpointed "
                    "administration contract."
                )

            order = list(record.randomized_case_order)
            if set(order) != set(ids) or len(order) != expected_case_count:
                raise AdministrationFailure(
                    "Checkpoint case order does not match the canonical suite."
                )

            cases = [case_by_id[cid] for cid in order]
            completed_turns = int(state.get("completed_turns", 0))

            resumed_current_turn = state.get("current_turn")
            resumed_attempts = [
                AttemptRecord(**attempt_data)
                for attempt_data in state.get("current_turn_attempts", [])
            ]
        else:
            if checkpoint_path is not None and Path(checkpoint_path).exists():
                raise AdministrationFailure(
                    "Checkpoint already exists; refuse to overwrite a prior "
                    "administration. Use explicit resume instead."
                )

            cases = list(loaded_cases)
            rng = random.Random(config.seed)
            rng.shuffle(cases)
            order = [_case_id(c) for c in cases]

            benchmark_name, benchmark_version = _benchmark_meta(cases[0])
            record = RunRecord.new(
                benchmark_name=benchmark_name,
                benchmark_version=benchmark_version,
                config=config,
                case_order=order,
            )
            completed_turns = 0
            resumed_current_turn = None
            resumed_attempts = []

            if checkpoint_path is not None:
                self._write_checkpoint(
                    checkpoint_path,
                    record,
                    completed_turns=completed_turns,
                )

        # Existing completed records are authoritative on resume.
        completed_case_map = {c.case_id: c for c in record.cases}

        # Test-only clean-boundary instrumentation: permit construction of a
        # checkpoint before any provider request. Production launchers do not
        # expose stop_after_turns.
        if (
            stop_after_turns is not None
            and completed_turns >= stop_after_turns
        ):
            return record

        try:
            for index, case in enumerate(cases, start=1):
                cid = _case_id(case)
                structure = _structure(case)
                canonical_turns = _turns(case)

                if structure.get("trajectory") != "fixed":
                    raise AdministrationFailure(
                        f"{cid}: trajectory must be fixed."
                    )
                if structure.get("turn_count") != len(canonical_turns):
                    raise AdministrationFailure(
                        f"{cid}: canonical turn_count mismatch."
                    )

                existing_case = completed_case_map.get(cid)
                if existing_case is not None and (
                    existing_case.status != "success"
                    or len(existing_case.turns) == len(canonical_turns)
                ):
                    # Fully recorded cases are never administered again.
                    continue

                if existing_case is None:
                    c_started = utc_now()
                    turn_records: List[TurnExecutionRecord] = []
                else:
                    c_started = existing_case.started_at
                    turn_records = list(existing_case.turns)
                    record.cases.remove(existing_case)

                history: List[Dict[str, Any]] = []

                # Reconstruct exact model-visible history from persisted turns.
                for i, prior in enumerate(turn_records):
                    canonical = canonical_turns[i]
                    history.append({
                        "role": "user",
                        "content": canonical["content"],
                    })
                    successful_attempt = next(
                        (
                            a for a in prior.attempts
                            if a.attempt_number == prior.selected_attempt
                        ),
                        None,
                    )
                    if successful_attempt is None:
                        raise AdministrationFailure(
                            f"{cid}/{prior.turn_id}: persisted successful turn "
                            "has no selected successful attempt."
                        )
                    assistant_content = successful_attempt.provider_metadata.get(
                        "assistant_message_content"
                    )
                    if assistant_content is None:
                        assistant_content = prior.substantive_output
                    history.append({
                        "role": "assistant",
                        "content": assistant_content,
                    })

                case_status = "success"
                case_error = None

                for turn_index, turn in enumerate(
                    canonical_turns[len(turn_records):],
                    start=len(turn_records),
                ):
                    if turn.get("role") != "user":
                        raise AdministrationFailure(
                            f"{cid}: canonical case turns must be user turns."
                        )

                    history.append({
                        "role": "user",
                        "content": turn["content"],
                    })
                    submitted = [dict(m) for m in history]

                    prior_attempts = []
                    if resumed_current_turn == {
                        "case_id": cid,
                        "turn_id": turn["id"],
                    }:
                        prior_attempts = list(resumed_attempts)
                        # Consume restored retry state exactly once.
                        resumed_current_turn = None
                        resumed_attempts = []

                    if progress_callback is not None:
                        progress_callback({
                            "event": "turn_started",
                            "completed_turns": completed_turns,
                            "total_turns": total_turns,
                            "case_id": cid,
                            "turn_id": turn["id"],
                        })

                    attempts, result = self._call_with_retries(
                        config=config,
                        messages=submitted,
                        checkpoint_path=checkpoint_path,
                        checkpoint_record=record,
                        completed_turns=completed_turns,
                        case_id=cid,
                        turn_id=turn["id"],
                        prior_attempts=prior_attempts,
                    )

                    if result is None:
                        case_status = "technical_failure"
                        case_error = (
                            f"{cid}/{turn['id']}: technical failure after "
                            f"{config.max_attempts} attempts."
                        )
                        turn_records.append(TurnExecutionRecord(
                            turn_id=turn["id"],
                            submitted_messages=submitted,
                            attempts=attempts,
                            selected_attempt=None,
                            substantive_output=None,
                            status="technical_failure",
                        ))
                        record.cases.append(CaseExecutionRecord(
                            case_id=cid,
                            case_order_index=index,
                            structure_type=structure["type"],
                            started_at=c_started,
                            completed_at=utc_now(),
                            status=case_status,
                            turns=turn_records,
                            error=case_error,
                        ))
                        completed_case_map[cid] = record.cases[-1]
                        if checkpoint_path is not None:
                            self._write_checkpoint(
                                checkpoint_path,
                                record,
                                completed_turns=completed_turns,
                                in_flight=None,
                                current_turn_attempts=attempts,
                            )
                        break

                    turn_records.append(TurnExecutionRecord(
                        turn_id=turn["id"],
                        submitted_messages=submitted,
                        attempts=attempts,
                        selected_attempt=attempts[-1].attempt_number,
                        substantive_output=result.substantive_output,
                        status="success",
                    ))
                    completed_turns += 1

                    assistant_content = result.provider_metadata.get(
                        "assistant_message_content"
                    )
                    if assistant_content is None:
                        assistant_content = result.substantive_output
                    history.append({
                        "role": "assistant",
                        "content": assistant_content,
                    })

                    # Persist a partial case so a successful turn is durable
                    # before any subsequent provider request.
                    partial_case = CaseExecutionRecord(
                        case_id=cid,
                        case_order_index=index,
                        structure_type=structure["type"],
                        started_at=c_started,
                        completed_at=utc_now(),
                        status="success",
                        turns=list(turn_records),
                        error=None,
                    )
                    record.cases.append(partial_case)
                    completed_case_map[cid] = partial_case

                    if checkpoint_path is not None:
                        self._write_checkpoint(
                            checkpoint_path,
                            record,
                            completed_turns=completed_turns,
                            in_flight=None,
                        )

                    if progress_callback is not None:
                        progress_callback({
                            "event": "turn_completed",
                            "completed_turns": completed_turns,
                            "total_turns": total_turns,
                            "case_id": cid,
                            "turn_id": turn["id"],
                        })

                    if stop_after_turns is not None and (
                        completed_turns >= stop_after_turns
                    ):
                        return record

                    # The partial case will be replaced if another turn follows.
                    if turn_index + 1 < len(canonical_turns):
                        record.cases.remove(partial_case)

                else:
                    # Ensure the final complete case is represented exactly once.
                    previous = completed_case_map.get(cid)
                    if previous is not None and previous in record.cases:
                        record.cases.remove(previous)

                    final_case = CaseExecutionRecord(
                        case_id=cid,
                        case_order_index=index,
                        structure_type=structure["type"],
                        started_at=c_started,
                        completed_at=utc_now(),
                        status=case_status,
                        turns=turn_records,
                        error=case_error,
                    )
                    record.cases.append(final_case)
                    completed_case_map[cid] = final_case

                    if checkpoint_path is not None:
                        self._write_checkpoint(
                            checkpoint_path,
                            record,
                            completed_turns=completed_turns,
                            in_flight=None,
                        )

            record.cases.sort(key=lambda c: c.case_order_index)
            record.status = (
                "complete"
                if len(record.cases) == expected_case_count
                and all(c.status == "success" for c in record.cases)
                else "complete_with_failures"
            )
            record.completed_at = utc_now()

            if checkpoint_path is not None:
                self._write_checkpoint(
                    checkpoint_path,
                    record,
                    completed_turns=completed_turns,
                    in_flight=None,
                )

            return record

        except AdministrationFailure:
            record.status = "administration_failure"
            record.completed_at = utc_now()
            raise

    @staticmethod
    def write_execution_record(record: RunRecord, output_path: Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite an existing run record.
        with output_path.open("x", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, ensure_ascii=False, indent=2, default=str)
            f.write("\n")
