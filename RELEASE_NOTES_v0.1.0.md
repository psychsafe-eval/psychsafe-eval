# PsychSafe-Eval v0.1.0

**Initial public release — September 23, 2026**

PsychSafe-Eval v0.1.0 is the first public release of an open clinical AI evaluation framework for clinically consequential reasoning and safety in psychiatry and behavioral health.

The release provides the benchmark itself, the methodology and evaluation protocol used for the official v0.1 evaluation, reproducibility tooling, public normalized administration records, finalized human scoring, aggregate results, and the public interactive website/demo.

## Benchmark

PsychSafe-Eval v0.1.0 contains:

- **20 fixed synthetic clinical cases**
  - 10 single-turn
  - 10 multi-turn
  - 40 total user turns
  - 9 clinician-facing
  - 11 patient-facing
- **65 prospectively defined targeted criteria**
- **6 evaluation dimensions**
  - Risk Recognition & Safety Management
  - Clinical Reasoning
  - Evidence Grounding
  - Uncertainty & Epistemic Calibration
  - Information & Narrative Integrity
  - Role & Action Appropriateness
- **17 prospectively designated Critical Safety Event criteria**
- **28 non-scored Enrichment Events**

Cases and rubrics were fixed before official benchmark administration. Multi-turn cases use fixed scripted trajectories to preserve comparability across evaluated systems.

PsychSafe-Eval does not define a single normative gold response and does not calculate an overall benchmark score.

## Official v0.1 evaluation

Four frozen provider/model paths were evaluated:

- OpenAI — **GPT-5.6 Sol**
- Anthropic — **Claude Opus 5**
- Google — **Gemini 3.1 Pro Preview**
- xAI — **Grok 4.6**

Official administration produced **80 SUE-by-case evaluations** across the 20-case suite.

Human evaluation generated:

- **260 targeted criterion judgments**
- **260 non-target dimension guardrail judgments**
- **112 Enrichment Event judgments**

All official scoring was performed by a single evaluator with physician training, advanced training in psychiatry, and graduate training in health informatics and analytics.

Evaluation was conducted in two blinded runs. Model identities and pair composition remained concealed until both scoring records had been completed, validated, and finalized.

## v0.1 results

PsychSafe-Eval reports four complementary result layers rather than collapsing performance into a composite score:

1. Critical Safety Events
2. Six-dimension capability profiles
3. Case-level findings
4. Enrichment Events

Across **68 prospectively designated Critical Safety Event opportunities**, the official evaluation identified **12 CSEs**:

| System Under Evaluation | CSEs |
| --- | ---: |
| GPT-5.6 Sol | **1** |
| Claude Opus 5 | **2** |
| Gemini 3.1 Pro Preview | **7** |
| Grok 4.6 | **2** |

The evaluation also identified both shared and system-specific patterns across the six capability dimensions and individual clinical trajectories. Some cases produced common areas of difficulty across all four systems while differing in severity; others produced sharply divergent behavior among systems.

Several consequential failures were multidimensional, and multi-turn cases exposed failures of longitudinal integration that would not necessarily be visible from isolated factual accuracy.

Enrichment Events provided a separate descriptive layer for clinically useful behaviors beyond minimum required performance. Of 28 opportunities per system, observed EEs were:

- GPT-5.6 Sol — **23/28**
- Claude Opus 5 — **26/28**
- Gemini 3.1 Pro Preview — **17/28**
- Grok 4.6 — **13/28**

Enrichment Events are non-scoring and should not be interpreted as an additional benchmark score or as compensating for Critical Safety Events or other deficiencies.

Complete dimension profiles, applicable sample sizes, case-level findings, CSE provenance, and interpretive boundaries are provided in the v0.1 Results.

## Reproducibility and provenance

The public repository preserves a source-of-truth hierarchy linking:

1. canonical case YAML;
2. canonical rubric YAML;
3. official execution records; and
4. finalized human scoring records.

The release also includes aggregate result artifacts, administration provenance, evaluation and runner source code, mechanical-validation tooling, and tests.

Public execution records preserve submitted trajectories and substantive model outputs while excluding provider-native operational metadata that is unnecessary for inspection of benchmark behavior. Cryptographic hashes link public provenance records to retained authoritative artifacts where applicable.

Two documented non-substantive post-freeze corrections were made during v0.1. Neither changed SUE-facing case content, targeted scoring semantics, official model responses, dimension scores, or required model re-administration.

## Human–AI collaborative development

PsychSafe-Eval was developed as a collaborative human–AI project.

**Concept, clinical direction, methodological decisions, and human evaluation:** Andre R. Alexander, MD, MSHIA

**Model-assisted design, adversarial review, writing, software development, validation, and analysis:** OpenAI GPT models

AI-assisted development was kept distinct from official benchmark evaluation. Systems Under Evaluation did not score their own official responses, and finalized blinded human scoring records were preserved before model identities were revealed.

All final benchmark design, scoring, interpretation, and release decisions were made by the human author.

## Scope and limitations

PsychSafe-Eval v0.1 is a 20-case synthetic benchmark designed to probe clinically consequential psychiatric and behavioral-health reasoning and safety. It is not a representative sample of all psychiatric encounters, clinical settings, or AI deployment conditions.

Results should not be interpreted as estimates of real-world clinical error rates, patient outcomes, or psychiatry-wide model performance.

Dimension coverage is intentionally uneven and results should be interpreted together with their applicable sample sizes. Evidence Grounding, in particular, contains only two applicable case-level observations per SUE in v0.1.

All v0.1 clinical scoring was performed by a single evaluator; inter-rater reliability has not yet been established.

Critical Safety Events are raw counts of prospectively designated failures under benchmark conditions rather than population safety-event rates. Enrichment Events are descriptive rather than scoring measures.

Results apply to the four evaluated provider/model paths under their frozen v0.1 administration configurations and should not be assumed to characterize later model versions or deployment configurations.

## Licensing and use

PsychSafe-Eval is an **open, publicly available benchmark**.

Copyright in the benchmark materials is retained by **Andre R. Alexander**. The benchmark may be viewed, downloaded, and used for AI evaluation, research, analysis, education, and publication of resulting findings under the PsychSafe-Eval Benchmark Use Terms.

Redistribution, republication, distribution of modified or derivative benchmark materials, incorporation into another distributed benchmark or dataset, and commercial redistribution require prior permission except where otherwise permitted by law.

Software components specifically identified as MIT-licensed are separately governed by the MIT License.

**© 2026 Andre R. Alexander. All rights reserved.**

## Release status

**Version:** 0.1.0  
**Release date:** September 23, 2026  
**Release type:** Initial public release

PsychSafe-Eval v0.1.0 establishes the first versioned public benchmark, evaluation methodology, official four-system results, and reproducibility record. Future releases may expand the case suite, evaluation evidence, tooling, or licensing terms through explicit versioned changes.
