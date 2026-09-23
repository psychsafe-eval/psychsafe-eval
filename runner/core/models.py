from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TechnicalFailure(RuntimeError):
    """Objective technical/API failure eligible for retry."""


class AdministrationFailure(RuntimeError):
    """Failure to preserve canonical administration; not a model-quality judgment."""


class IndeterminateAdministrationFailure(AdministrationFailure):
    """Provider request was dispatched but its substantive outcome is unknown.

    This failure is not eligible for automatic retry because the provider may
    have completed the administration even though the final response was not
    received and durably persisted.
    """


@dataclass(frozen=True)
class RunConfig:
    provider: str
    model: str
    seed: int
    max_attempts: int = 3
    system_prompt: Optional[str] = None
    provider_parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_attempts != 3:
            raise ValueError("PsychSafe-Eval v0.1 locks max_attempts at 3 (initial + 2 retries).")
        if self.system_prompt not in (None, ""):
            raise ValueError(
                "No PsychSafe-Eval-authored system prompt is permitted unless technically required."
            )


@dataclass
class AdapterResult:
    """Successful substantive provider return.

    `raw_response` preserves the provider return without replacement.
    `substantive_output` is the normalized/renderable model answer used downstream.
    """
    raw_response: Any
    substantive_output: str
    finish_info: Dict[str, Any] = field(default_factory=dict)
    provider_metadata: Dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(Protocol):
    """Common contract. Provider-specific implementation is Phase 11.4."""

    name: str

    def generate(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        parameters: Dict[str, Any],
    ) -> AdapterResult:
        ...


@dataclass
class AttemptRecord:
    attempt_number: int
    started_at: str
    completed_at: str
    status: str  # success | technical_failure
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Any = None
    substantive_output: Optional[str] = None
    finish_info: Dict[str, Any] = field(default_factory=dict)
    provider_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnExecutionRecord:
    turn_id: str
    submitted_messages: List[Dict[str, str]]
    attempts: List[AttemptRecord]
    selected_attempt: Optional[int]
    substantive_output: Optional[str]
    status: str  # success | technical_failure | administration_failure


@dataclass
class CaseExecutionRecord:
    case_id: str
    case_order_index: int
    structure_type: str
    started_at: str
    completed_at: str
    status: str
    turns: List[TurnExecutionRecord]
    error: Optional[str] = None


@dataclass
class RunRecord:
    run_id: str
    benchmark_name: str
    benchmark_version: str
    provider: str
    model: str
    randomization_seed: int
    randomized_case_order: List[str]
    started_at: str
    completed_at: Optional[str]
    status: str
    configuration: Dict[str, Any]
    cases: List[CaseExecutionRecord]

    @classmethod
    def new(
        cls, *, benchmark_name: str, benchmark_version: str,
        config: RunConfig, case_order: List[str]
    ) -> "RunRecord":
        return cls(
            run_id=str(uuid.uuid4()),
            benchmark_name=benchmark_name,
            benchmark_version=benchmark_version,
            provider=config.provider,
            model=config.model,
            randomization_seed=config.seed,
            randomized_case_order=list(case_order),
            started_at=utc_now(),
            completed_at=None,
            status="running",
            configuration={
                "max_attempts": config.max_attempts,
                "system_prompt": config.system_prompt,
                "provider_parameters": config.provider_parameters,
            },
            cases=[],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        """Reconstruct a persisted run/checkpoint without regenerating state."""
        cases = []
        for case_data in data.get("cases", []):
            turns = []
            for turn_data in case_data.get("turns", []):
                attempts = [
                    AttemptRecord(**attempt_data)
                    for attempt_data in turn_data.get("attempts", [])
                ]
                turns.append(TurnExecutionRecord(
                    turn_id=turn_data["turn_id"],
                    submitted_messages=turn_data["submitted_messages"],
                    attempts=attempts,
                    selected_attempt=turn_data.get("selected_attempt"),
                    substantive_output=turn_data.get("substantive_output"),
                    status=turn_data["status"],
                ))
            cases.append(CaseExecutionRecord(
                case_id=case_data["case_id"],
                case_order_index=case_data["case_order_index"],
                structure_type=case_data["structure_type"],
                started_at=case_data["started_at"],
                completed_at=case_data["completed_at"],
                status=case_data["status"],
                turns=turns,
                error=case_data.get("error"),
            ))

        return cls(
            run_id=data["run_id"],
            benchmark_name=data["benchmark_name"],
            benchmark_version=data["benchmark_version"],
            provider=data["provider"],
            model=data["model"],
            randomization_seed=data["randomization_seed"],
            randomized_case_order=list(data["randomized_case_order"]),
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            status=data["status"],
            configuration=dict(data["configuration"]),
            cases=cases,
        )
