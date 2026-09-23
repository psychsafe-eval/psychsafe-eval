from __future__ import annotations

import subprocess
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_pilot_script_entrypoint_imports_without_pythonpath():
    proc = subprocess.run(
        [sys.executable, "scripts/run_technical_pilot.py", "--help"],
        cwd=ROOT, capture_output=True, text=True, env={"PATH": __import__("os").environ.get("PATH", "")},
    )
    assert proc.returncode == 0, proc.stderr
    assert "Phase 11.6 real-SUE technical pilot" in proc.stdout


def test_pytest_config_declares_repository_root_pythonpath():
    text=(ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "pythonpath = ." in text


def test_phase12_3_four_sue_technical_validation_contracts_are_frozen():
    import importlib.util
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_four_sue_technical_validation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_four_sue_technical_validation", script
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    contracts = module.SUE_CONTRACTS

    assert set(contracts) == {"openai", "anthropic", "gemini", "xai"}

    assert contracts["openai"]["sue"] == "SUE-1"
    assert contracts["openai"]["provider"] == "openai"
    assert contracts["openai"]["model"] == "gpt-5.6-sol"
    assert contracts["openai"]["provider_parameters"] == {
        "reasoning": {"effort": "max"},
        "max_output_tokens": 128000,
    }

    assert contracts["anthropic"]["sue"] == "SUE-2"
    assert contracts["anthropic"]["provider"] == "anthropic"
    assert contracts["anthropic"]["model"] == "claude-opus-5"
    assert contracts["anthropic"]["provider_parameters"] == {
        "max_tokens": 128000,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "max"},
    }

    assert contracts["gemini"]["sue"] == "SUE-3"
    assert contracts["gemini"]["provider"] == "gemini"
    assert contracts["gemini"]["model"] == "gemini-3.1-pro-preview"
    assert contracts["gemini"]["provider_parameters"] == {
        "generation_config": {
            "thinking_level": "high",
            "max_output_tokens": 65536,
        },
    }

    assert contracts["xai"]["sue"] == "SUE-4"
    assert contracts["xai"]["provider"] == "xai"
    assert contracts["xai"]["model"] == "grok-4.6"
    assert contracts["xai"]["provider_parameters"] == {
        "reasoning": {"effort": "xhigh"},
    }


def _load_four_sue_launcher_for_test():
    import importlib.util

    script = ROOT / "scripts" / "run_four_sue_technical_validation.py"
    spec = importlib.util.spec_from_file_location(
        "run_four_sue_technical_validation_checkpoint_test", script
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_four_sue_launcher_creates_checkpoint_location_before_administration(
    tmp_path, monkeypatch
):
    module = _load_four_sue_launcher_for_test()
    module.ROOT = tmp_path

    events = []

    class FakeRecord:
        run_id = "fixture-run-id"
        status = "complete"

    class FakeRunner:
        def __init__(self, repo_root, adapter):
            self.repo_root = repo_root

        def run(self, config, **kwargs):
            checkpoint_path = kwargs["checkpoint_path"]
            events.append(
                {
                    "run_dir_exists": checkpoint_path.parent.exists(),
                    "checkpoint_path": checkpoint_path,
                    "kwargs": dict(kwargs),
                }
            )
            checkpoint_path.write_text(
                '{"checkpoint_version": 1}\n',
                encoding="utf-8",
            )
            return FakeRecord()

        def write_execution_record(self, record, path):
            path.write_text('{"status": "complete"}\n', encoding="utf-8")

    class FakeAdapter:
        pass

    monkeypatch.setattr(module, "BenchmarkRunner", FakeRunner)
    monkeypatch.setitem(
        module.SUE_CONTRACTS["openai"], "adapter", FakeAdapter
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_four_sue_technical_validation.py",
            "--sue",
            "openai",
            "--seed",
            "115",
        ],
    )

    assert module.main() == 0
    assert len(events) == 1
    event = events[0]
    assert event["run_dir_exists"] is True
    assert event["checkpoint_path"].name == "checkpoint.json"
    assert event["kwargs"]["resume"] is False
    assert "stop_after_turns" not in event["kwargs"]

    run_dir = event["checkpoint_path"].parent
    assert (run_dir / "execution.json").exists()
    metadata = json.loads(
        (run_dir / "TECHNICAL_VALIDATION_METADATA.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["checkpoint_record"] == "checkpoint.json"
    assert metadata["execution_record"] == "execution.json"
    assert metadata["run_id"] == "fixture-run-id"


def test_four_sue_launcher_resume_reuses_existing_run_directory(
    tmp_path, monkeypatch
):
    module = _load_four_sue_launcher_for_test()
    module.ROOT = tmp_path

    run_dir = (
        tmp_path
        / "results"
        / "runs"
        / "phase12.3-technical-validation-anthropic-existing"
    )
    run_dir.mkdir(parents=True)
    checkpoint = run_dir / "checkpoint.json"
    checkpoint.write_text('{"checkpoint_version": 1}\n', encoding="utf-8")

    calls = []

    class FakeRecord:
        run_id = "existing-run-id"
        status = "complete"

    class FakeRunner:
        def __init__(self, repo_root, adapter):
            pass

        def run(self, config, **kwargs):
            calls.append(dict(kwargs))
            return FakeRecord()

        def write_execution_record(self, record, path):
            path.write_text('{"status": "complete"}\n', encoding="utf-8")

    class FakeAdapter:
        pass

    monkeypatch.setattr(module, "BenchmarkRunner", FakeRunner)
    monkeypatch.setitem(
        module.SUE_CONTRACTS["anthropic"], "adapter", FakeAdapter
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_four_sue_technical_validation.py",
            "--sue",
            "anthropic",
            "--seed",
            "115",
            "--resume",
            str(run_dir),
        ],
    )

    assert module.main() == 0
    assert len(calls) == 1
    assert calls[0]["checkpoint_path"] == checkpoint
    assert calls[0]["resume"] is True
    assert callable(calls[0]["progress_callback"])
    assert "stop_after_turns" not in calls[0]
    assert (run_dir / "execution.json").exists()


def test_four_sue_launcher_help_exposes_resume_but_not_test_stop_hook():
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_four_sue_technical_validation.py",
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "--resume" in proc.stdout
    assert "stop-after-turns" not in proc.stdout


def test_four_sue_progress_reporter_formats_deterministic_turn_progress(capsys):
    module = _load_four_sue_launcher_for_test()

    times = iter([100.0, 105.0, 147.5])

    reporter = module.ProgressReporter(clock=lambda: next(times))

    reporter({
        "event": "turn_started",
        "completed_turns": 7,
        "total_turns": 40,
        "case_id": "PSY-012",
        "turn_id": "T2",
    })
    reporter({
        "event": "turn_completed",
        "completed_turns": 8,
        "total_turns": 40,
        "case_id": "PSY-012",
        "turn_id": "T2",
    })

    output = capsys.readouterr().out

    assert "[07/40 | 17.5%]" in output
    assert "PSY-012 / T2" in output
    assert "requesting..." in output

    assert "[08/40 | 20.0%]" in output
    assert "completed in 42.5s" in output
    assert "run 47.5s" in output


def test_four_sue_launcher_passes_progress_callback_to_runner(
    monkeypatch,
    tmp_path,
):
    module = _load_four_sue_launcher_for_test()

    captured = {}

    class FakeRecord:
        run_id = "fixture-run-id"
        status = "complete"

        def to_dict(self):
            return {
                "run_id": self.run_id,
                "status": self.status,
            }

    class FakeRunner:
        def __init__(self, repo_root, adapter):
            pass

        def run(self, config, **kwargs):
            captured.update(kwargs)
            callback = kwargs.get("progress_callback")
            assert callable(callback)
            return FakeRecord()

        def write_execution_record(self, record, output_path):
            output_path.write_text(
                json.dumps(record.to_dict()) + "\n",
                encoding="utf-8",
            )

    class FakeAdapter:
        pass

    monkeypatch.setattr(module, "BenchmarkRunner", FakeRunner)
    monkeypatch.setitem(
        module.SUE_CONTRACTS,
        "openai",
        {
            **module.SUE_CONTRACTS["openai"],
            "adapter": FakeAdapter,
        },
    )
    monkeypatch.setattr(module, "utc_stamp", lambda: "FIXTURE")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_four_sue_technical_validation.py",
            "--sue",
            "openai",
            "--seed",
            "115",
        ],
    )

    assert module.main() == 0
    assert callable(captured["progress_callback"])
    assert captured["resume"] is False
    assert "stop_after_turns" not in captured
