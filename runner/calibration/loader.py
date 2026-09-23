from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List
import yaml

from runner.core import AdministrationFailure

DEFAULT_CALIBRATION_IDS = (
    "EXP-01", "EXP-02", "EXP-03", "EXP-05", "EXP-06", "DEMO-001",
)


class CalibrationCandidateLoader:
    """Load only explicitly allowed noncanonical calibration candidates.

    Candidate YAMLs contain evaluator-only rubric material. This loader validates the
    source document but returns a deliberately minimal inference projection containing
    only identifier, format, title, and verbatim user prompts. Criteria, anchors,
    enrichment events, hidden ground truth, and design-intent fields are never returned
    to the orchestration layer.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.allowed = set(DEFAULT_CALIBRATION_IDS)

    def _path_for(self, candidate_id: str) -> Path:
        if candidate_id.startswith("EXP-"):
            return self.repo_root / "experimental_candidates" / f"{candidate_id}.yaml"
        if candidate_id == "DEMO-001":
            return self.repo_root / "demo_candidates" / "DEMO-001.yaml"
        raise AdministrationFailure(f"Candidate {candidate_id!r} is not in the locked calibration pool.")

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise AdministrationFailure(f"{path.name}: candidate YAML must be a mapping.")
        return data

    def load_candidates(self, candidate_ids: Iterable[str] = DEFAULT_CALIBRATION_IDS) -> List[Dict[str, Any]]:
        ids = list(candidate_ids)
        if not ids:
            raise AdministrationFailure("Calibration selection may not be empty.")
        if len(ids) != len(set(ids)):
            raise AdministrationFailure("Calibration selection contains duplicate candidate IDs.")
        unknown = [cid for cid in ids if cid not in self.allowed]
        if unknown:
            raise AdministrationFailure(f"Calibration selection contains non-locked candidates: {unknown}")

        projected: List[Dict[str, Any]] = []
        for cid in ids:
            data = self._load_yaml(self._path_for(cid))
            if data.get("id") != cid:
                raise AdministrationFailure(f"{cid}: YAML identifier mismatch.")
            prompts = data.get("prompts")
            if not isinstance(prompts, dict) or not prompts:
                raise AdministrationFailure(f"{cid}: prompts must be a non-empty mapping.")
            expected = [f"T{i}" for i in range(1, len(prompts) + 1)]
            if list(prompts.keys()) != expected:
                raise AdministrationFailure(f"{cid}: prompts must be consecutively ordered T1..Tn.")
            if any(not isinstance(v, str) or not v for v in prompts.values()):
                raise AdministrationFailure(f"{cid}: every prompt must be non-empty text.")

            projected.append({
                "id": cid,
                "format": data.get("format", "multi-turn" if len(prompts) > 1 else "single-turn"),
                "title": data.get("title"),
                "turns": [{"id": tid, "role": "user", "content": text} for tid, text in prompts.items()],
            })
        return projected
