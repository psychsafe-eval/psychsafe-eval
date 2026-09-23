# PsychSafe-Eval

**An open clinical AI evaluation framework for safety and quality in psychiatry and medicine.**

PsychSafe-Eval v0.1 contains 20 fixed cases (10 single-turn, 10 multi-turn), 65 prospectively defined targeted criteria across six capability dimensions, 17 prospectively designated Critical Safety Event criteria, and 28 non-scored Enrichment Events.

The v0.1 release includes the canonical case and rubric sources, evaluation methodology, reproducibility tooling, public normalized records of the four official administrations, finalized human scoring, derived aggregate results, and the public interactive website/demo.

## Repository map

- `cases/` and `rubrics/` — canonical administered cases and hidden scoring specifications.
- `demo/` — non-counting public demonstration case.
- `serialization_spec.yaml` — benchmark serialization specification.
- `methodology/` — v0.1 methods and evaluation protocol.
- `evaluator/` — evaluator workflow and interface source.
- `runner/` — provider-neutral runner and provider adapters.
- `scripts/` — official administration, aggregation, and mechanical validation entry points.
- `tests/` — current mechanical and workflow tests.
- `results/v0.1/` — official administration records, finalized scoring, and aggregate results.
- `website/` — public PsychSafe-Eval website.
- `assets/` — project branding assets.

## Source-of-truth hierarchy

1. Case YAML defines what is administered.
2. Rubric YAML defines how it is scored.
3. Public execution records preserve the exact submitted trajectories and substantive outputs; hashes link them to the retained authoritative provider-native records.
4. Finalized scoring records preserve evaluator judgments.

Derived HTML, tables, charts, and reports are presentation layers rather than editable benchmark sources of truth.

## v0.1 evaluation

Official v0.1 administration evaluated GPT-5.6 Sol, Claude Opus 5, Gemini 3.1 Pro Preview, and Grok 4.6 using frozen administration contracts. Human scoring was completed in two blinded evaluation runs before model identities were unblinded. No overall composite score is reported; results are presented through dimension profiles, raw Critical Safety Event counts, case-level findings, and descriptive Enrichment Events.

## License and use

**PsychSafe-Eval is an open, publicly available benchmark.**

The benchmark may be downloaded and used for AI evaluation, research, analysis, education, and publication of resulting findings. Copyright in the benchmark materials is retained by **Andre R. Alexander, MD, MSHIA**.

Redistribution, republication, distribution of modified or derivative benchmark materials, incorporation into another distributed benchmark or dataset, and commercial redistribution require prior permission except where otherwise permitted by law.

Software source code in `evaluator/`, `runner/`, `scripts/`, and `tests/` is separately available under the MIT License. See `BENCHMARK_USE_TERMS.md` and `LICENSE-MIT`.

© 2026 Andre R. Alexander. All rights reserved.

## Credits

PsychSafe-Eval was developed as a collaborative human–AI project.

- **Concept, clinical direction, methodological decisions & human evaluation:** Andre R. Alexander, MD, MSHIA
- **Model-assisted design, adversarial review, writing, software development, validation & analysis:** OpenAI GPT models

All final benchmark design, scoring, interpretation, and release decisions were made by the human author. Official v0.1 SUE responses were evaluated under the blinded human-evaluation procedure described in the Methods.

## Status

**PsychSafe-Eval v0.1.0 — initial public release, September 23, 2026.**

See `RELEASE_NOTES_v0.1.0.md` for the release record and `results/v0.1/results.md` for the complete public Results narrative.
