#!/usr/bin/env python3
"""Phase 11.5 mechanical validation entry point."""
from __future__ import annotations

from pathlib import Path
import hashlib, json, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]


def authoritative_hash_errors():
    errors=[]
    sums=ROOT/"SHA256SUMS"
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel=line.split("  ",1)
        path=ROOT/rel
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if actual != expected:
            errors.append({"path":rel,"expected":expected,"actual":actual})
    return errors


def main():
    hash_errors=authoritative_hash_errors()
    proc=subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT, capture_output=True, text=True
    )
    report={
        "phase":"11.5",
        "status":"PASS" if proc.returncode==0 and not hash_errors else "FAIL",
        "pytest_returncode":proc.returncode,
        "pytest_output":proc.stdout,
        "authoritative_hashes_valid":not hash_errors,
        "hash_errors":hash_errors,
        "live_sue_calls_made":False,
        "credentials_required":False,
    }
    out=ROOT/"phase_11_5_validation.json"
    out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
