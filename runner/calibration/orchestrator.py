from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import random
import uuid

from runner.core import (
    AdapterResult, AttemptRecord, CaseExecutionRecord, RunConfig,
    TechnicalFailure, AdministrationFailure,
)
from runner.core.models import TurnExecutionRecord, utc_now
from .loader import CalibrationCandidateLoader, DEFAULT_CALIBRATION_IDS


@dataclass
class CalibrationRunRecord:
    run_id: str
    run_type: str
    phase: str
    prospectively_excluded_from_benchmark_results: bool
    provider: str
    model_requested: str
    randomization_seed: int
    randomized_case_order: List[str]
    started_at: str
    completed_at: Optional[str]
    status: str
    configuration: Dict[str, Any]
    cost_accounting: Dict[str, Any] = field(default_factory=dict)
    cases: List[CaseExecutionRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExperimentalCalibrationRunner:
    """Provider-neutral runner for the locked six-candidate calibration pool only."""

    def __init__(self, repo_root: Path, adapter: Any):
        self.repo_root = Path(repo_root)
        self.adapter = adapter
        self.loader = CalibrationCandidateLoader(self.repo_root)

    @staticmethod
    def _usage_cost_usd(usage: Dict[str, Any], *, input_usd_per_mtok: float, output_usd_per_mtok: float) -> float:
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return (input_tokens * input_usd_per_mtok + output_tokens * output_usd_per_mtok) / 1_000_000.0

    def _call_with_retries(
        self, *, config: RunConfig, messages: List[Dict[str, str]],
        cost_state: Optional[Dict[str, Any]] = None,
    ):
        attempts: List[AttemptRecord] = []
        for n in range(1, config.max_attempts + 1):
            started = utc_now()
            try:
                if cost_state is not None:
                    counter = getattr(self.adapter, "count_input_tokens", None)
                    if not callable(counter):
                        raise AdministrationFailure(
                            "Cost-capped calibration requires an adapter with count_input_tokens()."
                        )
                    input_tokens = counter(
                        model=config.model, messages=[dict(m) for m in messages],
                        parameters=dict(config.provider_parameters),
                    )
                    max_output_tokens = int(config.provider_parameters.get("max_tokens", 0) or 0)
                    worst_case_next = (
                        input_tokens * cost_state["input_usd_per_mtok"]
                        + max_output_tokens * cost_state["output_usd_per_mtok"]
                    ) / 1_000_000.0
                    if cost_state["actual_cost_usd"] + worst_case_next > cost_state["max_cost_usd"] + 1e-12:
                        raise AdministrationFailure(
                            "Run cost guard stopped before generation: actual spend plus the next "
                            f"request's worst-case token cost (${cost_state['actual_cost_usd'] + worst_case_next:.6f}) "
                            f"would exceed the ${cost_state['max_cost_usd']:.2f} run ceiling."
                        )
                    cost_state["preflight_checks"] += 1
                    cost_state["last_preflight_input_tokens"] = input_tokens
                    cost_state["last_preflight_worst_case_request_usd"] = worst_case_next

                result = self.adapter.generate(
                    model=config.model,
                    messages=[dict(m) for m in messages],
                    parameters=dict(config.provider_parameters),
                )
                if not isinstance(result, AdapterResult):
                    raise AdministrationFailure("Adapter returned an object outside the AdapterResult contract.")
                attempts.append(AttemptRecord(
                    attempt_number=n, started_at=started, completed_at=utc_now(), status="success",
                    raw_response=result.raw_response, substantive_output=result.substantive_output,
                    finish_info=dict(result.finish_info), provider_metadata=dict(result.provider_metadata),
                ))
                if cost_state is not None:
                    usage = dict(result.provider_metadata.get("usage") or {})
                    call_cost = self._usage_cost_usd(
                        usage, input_usd_per_mtok=cost_state["input_usd_per_mtok"],
                        output_usd_per_mtok=cost_state["output_usd_per_mtok"],
                    )
                    cost_state["actual_cost_usd"] += call_cost
                    cost_state["successful_billable_calls"] += 1
                    cost_state["input_tokens"] += int(usage.get("input_tokens", 0) or 0)
                    cost_state["output_tokens"] += int(usage.get("output_tokens", 0) or 0)
                return attempts, result
            except TechnicalFailure as exc:
                attempts.append(AttemptRecord(
                    attempt_number=n, started_at=started, completed_at=utc_now(), status="technical_failure",
                    error_type=type(exc).__name__, error_message=str(exc),
                ))
                if n == config.max_attempts:
                    return attempts, None
        return attempts, None

    def run(
        self, config: RunConfig, candidate_ids=DEFAULT_CALIBRATION_IDS, *,
        max_cost_usd: Optional[float] = None,
        input_usd_per_mtok: Optional[float] = None,
        output_usd_per_mtok: Optional[float] = None,
    ) -> CalibrationRunRecord:
        candidates = self.loader.load_candidates(candidate_ids)
        ids = [c["id"] for c in candidates]
        if set(ids) != set(DEFAULT_CALIBRATION_IDS) or len(ids) != len(DEFAULT_CALIBRATION_IDS):
            raise AdministrationFailure("This Phase 12.3 calibration run requires exactly the locked six-candidate pool.")

        cost_state = None
        if max_cost_usd is not None:
            if max_cost_usd <= 0 or input_usd_per_mtok is None or output_usd_per_mtok is None:
                raise AdministrationFailure("A positive run cost ceiling and both token prices are required together.")
            if input_usd_per_mtok < 0 or output_usd_per_mtok < 0:
                raise AdministrationFailure("Token prices cannot be negative.")
            cost_state = {
                "max_cost_usd": float(max_cost_usd),
                "input_usd_per_mtok": float(input_usd_per_mtok),
                "output_usd_per_mtok": float(output_usd_per_mtok),
                "actual_cost_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "successful_billable_calls": 0,
                "preflight_checks": 0,
            }

        rng = random.Random(config.seed)
        rng.shuffle(candidates)
        order = [c["id"] for c in candidates]
        record = CalibrationRunRecord(
            run_id=str(uuid.uuid4()), run_type="experimental_calibration", phase="12.3",
            prospectively_excluded_from_benchmark_results=True,
            provider=config.provider, model_requested=config.model,
            randomization_seed=config.seed, randomized_case_order=order,
            started_at=utc_now(), completed_at=None, status="running",
            configuration={
                "max_attempts": config.max_attempts,
                "system_prompt": config.system_prompt,
                "provider_parameters": dict(config.provider_parameters),
                "tools_enabled": False,
                "web_enabled": False,
                "retrieval_enabled": False,
            },
            cost_accounting=(dict(cost_state) if cost_state is not None else {}),
        )

        try:
            for index, case in enumerate(candidates, start=1):
                history: List[Dict[str, str]] = []
                turns: List[TurnExecutionRecord] = []
                case_status = "success"
                case_error = None
                c_started = utc_now()

                for turn in case["turns"]:
                    # Fixed user trajectory: source prompt enters verbatim regardless of prior answer.
                    history.append({"role": "user", "content": turn["content"]})
                    submitted = [dict(m) for m in history]
                    attempts, result = self._call_with_retries(
                        config=config, messages=submitted, cost_state=cost_state
                    )
                    if cost_state is not None:
                        record.cost_accounting = dict(cost_state)
                    if result is None:
                        case_status = "technical_failure"
                        case_error = f"{case['id']}/{turn['id']}: technical failure after {config.max_attempts} attempts."
                        turns.append(TurnExecutionRecord(
                            turn_id=turn["id"], submitted_messages=submitted, attempts=attempts,
                            selected_attempt=None, substantive_output=None, status="technical_failure",
                        ))
                        break
                    turns.append(TurnExecutionRecord(
                        turn_id=turn["id"], submitted_messages=submitted, attempts=attempts,
                        selected_attempt=attempts[-1].attempt_number,
                        substantive_output=result.substantive_output, status="success",
                    ))
                    # Carry forward the provider's actual selected assistant message. For
                    # Anthropic adaptive thinking this includes signed thinking blocks, which
                    # must be passed back unchanged for valid multi-turn continuity.
                    assistant_content = result.provider_metadata.get("assistant_message_content")
                    if assistant_content is None:
                        assistant_content = result.substantive_output
                    history.append({"role": "assistant", "content": assistant_content})

                record.cases.append(CaseExecutionRecord(
                    case_id=case["id"], case_order_index=index,
                    structure_type=case["format"], started_at=c_started,
                    completed_at=utc_now(), status=case_status, turns=turns, error=case_error,
                ))

            record.status = (
                "complete" if len(record.cases) == 6 and all(c.status == "success" for c in record.cases)
                else "complete_with_failures"
            )
            record.completed_at = utc_now()
            return record
        except AdministrationFailure:
            record.status = "administration_failure"
            record.completed_at = utc_now()
            raise

    @staticmethod
    def write_execution_record(record: CalibrationRunRecord, output_path: Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, ensure_ascii=False, indent=2, default=str)
            f.write("\n")
