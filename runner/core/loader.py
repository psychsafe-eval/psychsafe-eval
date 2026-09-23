from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import hashlib
import yaml


class SuiteLoader:
    """Loads only manifest-listed canonical cases.

    Rubric paths may exist in the manifest for repository linkage, but this loader
    never opens rubric files. This is an inference-isolation boundary.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.case_dir = self.repo_root / "cases"
        self.manifest_path = self.case_dir / "manifest.yaml"

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def load_manifest(self) -> Dict[str, Any]:
        with self.manifest_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError("Suite manifest must be a mapping.")
        return data

    def _manifest_entries(self, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Phase 11.1 manifest uses `cases`.
        entries = manifest.get("cases")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Manifest must contain a non-empty `cases` list.")
        return entries

    def load_cases(self) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        manifest = self.load_manifest()
        loaded: List[Dict[str, Any]] = []

        for entry in self._manifest_entries(manifest):
            rel = entry.get("case_path") or entry.get("path")
            if not rel:
                # tolerate manifest entries whose path is derivable from ID
                case_id = entry["id"] if "id" in entry else entry["case_id"]
                rel = f"cases/{case_id}.yaml"
            rel_path = Path(rel)
            # Authoritative manifest case_path values are relative to cases/.
            # Also accept repo-relative paths beginning with "cases/".
            path = (
                self.repo_root / rel_path
                if rel_path.parts and rel_path.parts[0] == "cases"
                else self.case_dir / rel_path
            )
            with path.open("r", encoding="utf-8") as f:
                case = yaml.safe_load(f)
            loaded.append(case)

        return manifest, loaded
