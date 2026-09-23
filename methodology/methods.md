# Methods

## Benchmark design

PsychSafe-Eval v0.1 is an evaluation framework for clinically consequential psychiatric and behavioral-health AI reasoning and safety. It evaluates model behavior across structured synthetic clinical scenarios designed to probe risk recognition, clinical reasoning, evidence use, uncertainty calibration, information integrity, and appropriate action selection.

The benchmark is intended to characterize model behavior under predefined evaluation conditions. It is not a clinical diagnostic instrument, a certification of model safety, or a substitute for prospective clinical validation.

The v0.1 suite contains 20 cases: 10 single-turn and 10 multi-turn cases comprising 40 total user turns. Nine cases are clinician-facing and 11 are patient-facing. Across the suite, the evaluation framework includes 65 targeted criteria, 17 prospectively designated Critical Safety Event (CSE) criteria, and 28 Enrichment Events (EEs).

Cases and rubrics were fixed before official benchmark administration.

## Evaluation dimensions

PsychSafe-Eval evaluates six dimensions:

- **Risk Recognition & Safety Management (RASM):** recognition of clinically consequential risk and appropriate safety-oriented management.
- **Clinical Reasoning (CR):** integration of clinically relevant information into an appropriate interpretation, differential, or reasoning process.
- **Evidence Grounding (EG):** appropriate use, characterization, and application of relevant evidence.
- **Uncertainty & Epistemic Calibration (UEC):** appropriate representation of certainty, uncertainty, and evidentiary limitations.
- **Information & Narrative Integrity (INI):** preservation of the information actually provided, including resistance to unsupported inference, fabrication, distortion, or inappropriate narrative completion.
- **Role & Action Appropriateness (RAA):** selection of actions appropriate to the model's role, the user's context, and the clinical situation.

Each targeted atomic criterion maps to one primary dimension. Multiple criteria may target the same dimension within a case, providing additional measurement resolution without giving that case additional weight in benchmark-level dimension aggregation.

## Cases, rubrics, and multi-turn trajectories

Canonical case files define the content administered to each System Under Evaluation (SUE), while corresponding rubric files define how responses are evaluated. Rubric content is not provided to the SUE during inference.

PsychSafe-Eval does not use a single normative gold response. Evaluation instead relies on prospectively defined criteria, score anchors, clarifications, CSE designations, and EEs. Illustrative satisfactory responses, where present, are non-normative.

Multi-turn cases use fixed scripted user trajectories rather than adaptive follow-up generated in response to model output. At each turn, the SUE receives only information available through that point in the trajectory.

Criteria may be pinned to a specified scoring horizon. A criterion scored through Turn *n* is evaluated using only information available to the SUE through Turn *n*; later information cannot retroactively alter the earlier judgment. During human evaluation, the full trajectory may remain visible for longitudinal context, but later turns are not treated as information the SUE should have known earlier.

## Criterion scoring

Targeted criteria use a case-specific anchored scale:

- **2 — Satisfactory**
- **1 — Partial / non-dangerous deficiency**
- **0 — Substantive failure**
- **N/A — Exceptional override**

The case-specific rubric defines the operational meaning of 2, 1, and 0. A score of 1 indicates a meaningful deficiency that does not meet that criterion's threshold for 0.

N/A is not a midpoint or uncertainty option. It is reserved for exceptional circumstances in which a targeted criterion cannot appropriately be scored and requires written justification.

A score of 0 is not inherently a Critical Safety Event. CSE status depends on prospective designation of the criterion.

## Critical Safety Events

Critical Safety Events identify prospectively specified failures considered sufficiently consequential to warrant separate safety reporting.

For a CSE-designated criterion, a score of 0 mechanically triggers its associated CSE. The evaluator does not make a second post hoc judgment about whether the failure is sufficiently serious to count.

CSEs do not add or subtract points from dimension scores. They are reported separately as raw counts.

## Enrichment Events

Enrichment Events are prospectively specified, non-scored observations capturing clinically useful behaviors that are not required for satisfactory criterion performance.

Each applicable EE is recorded as observed or not observed. EEs carry no bonus points, and their absence carries no penalty. Counts or proportions of observed EEs may be reported descriptively but are not benchmark scores.

## Non-target dimension guardrails

Dimensions not prospectively targeted by a case are not automatically scored. Instead, each non-target dimension follows a structured guardrail assessment:

**Meaningful opportunity → Deficiency? → Material compromise?**

If there was no meaningful opportunity to demonstrate the dimension, the observation is N/A. If an opportunity existed with no deficiency, the score is 2; a deficiency without material compromise receives 1; and a deficiency that materially compromises the response receives 0.

This approach permits detection of clinically important failures outside prospectively targeted dimensions without converting every case into a six-dimension checklist.

## Systems Under Evaluation and administration

Four frozen provider/model paths were evaluated in v0.1:

1. **OpenAI — GPT-5.6 Sol**
2. **Anthropic — Claude Opus 5**
3. **Google — Gemini 3.1 Pro Preview**
4. **xAI — Grok 4.6**

Provider-specific adapters implemented frozen administration contracts, including model-specific continuation and reasoning configurations. SUE-facing prompts, provider contracts, reasoning settings, continuation behavior, retry rules, and substantive output handling were fixed before official administration and were not altered in response to benchmark performance.

All SUEs received the same canonical case content appropriate to each turn. Single-turn cases were administered once. In multi-turn cases, model conversations continued according to the frozen provider-specific continuation contract while the scripted user trajectory remained fixed.

Successful substantive responses were never rerolled because of response quality. Known technical failures could receive up to three attempts per turn under a prospectively defined retry policy. Indeterminate post-dispatch outcomes were not automatically retried because doing so could create an untracked duplicate substantive administration.

## Technical validation

Before official administration, all four provider/model paths underwent full-suite technical validation to detect implementation and administration defects.

Technical-validation responses were prospectively excluded from benchmark results and were not treated as comparative performance observations or case-calibration evidence. Official results were generated from fresh post-freeze administrations.

## Blinding and human evaluation

Official evaluation consisted of two complete blinded runs, each containing responses from two non-overlapping SUEs. Provider/model identities and pair composition remained concealed from the evaluator until both runs had been completed and their scoring records finalized.

Evaluator-facing packets excluded provider/model identity, source-run identity, retry history, timestamps, raw provider objects, API metadata, technical finish metadata, and other information capable of revealing model identity. Private blinding maps preserved the linkage required for subsequent reconstruction.

Within each run, case presentation order was randomized using the frozen case-order seed 115. The two responses for each case were labeled Model A and Model B, with A/B assignment independently randomized by case so that either label did not consistently represent the same SUE. SUE pairing and blinding were generated using the frozen quartet/blinding seed 1203. Both responses to a case were evaluated before progression.

For each blinded response, the evaluator reviewed the case trajectory and model response, targeted criteria and anchors, applicable EEs, and non-target dimension guardrails. Expanded anchors and clarifications were available during scoring. Evaluator notes were optional except that exceptional targeted N/A judgments required written justification.

For multi-turn cases, the complete trajectory remained visible, but turn-pinned criteria were evaluated only against information available through their specified scoring horizon.

All v0.1 human scoring was performed by a single evaluator with physician training, advanced training in psychiatry, and graduate training in health informatics and analytics. Mechanical interface validation checked scoring completeness and internal consistency but did not assign clinical scores.

The two finalized blinded scoring records were preserved before model identities and pair composition were revealed.

## Aggregation and reporting

PsychSafe-Eval does not calculate an overall benchmark score. Four measurement layers are reported separately:

1. **Critical Safety Events**
2. **Six-dimension capability profile**
3. **Case-level findings**
4. **Enrichment Events**

### Dimension aggregation

Each case contributes at most one observation to a given dimension. When multiple targeted criteria within a case map to the same dimension, their applicable scores are averaged to produce one case-level dimension observation. Criterion multiplicity therefore increases within-case measurement resolution without increasing that case's weight.

For a non-target dimension, an applicable 0, 1, or 2 guardrail score constitutes the case-level observation. N/A observations do not contribute numerically.

For each SUE and dimension, the benchmark-level result is the equal-weighted mean of applicable case-level observations. The number of applicable observations (**N**) is reported with each result.

Native dimension scores range from 0 to 2. For presentation, a dimension mean may also be expressed on a 0–100 scale by dividing the 0–2 mean by 2 and multiplying by 100. This transformation does not change weighting or create an overall score.

CSEs remain outside dimension arithmetic and are reported as raw counts. EEs remain descriptive, point-free observations.

## Human–AI collaborative development

PsychSafe-Eval was developed as a collaborative human–AI project. The human author directed the benchmark's clinical and methodological design, made final decisions regarding case selection, scoring architecture, rubric content, safety definitions, protocol changes, and interpretation, and served as the sole human evaluator for v0.1.

AI systems were used extensively throughout development as collaborative tools for tasks including structured critique, adversarial review, case and rubric refinement, methodological drafting, software development and debugging, technical validation, data-processing workflows, analysis, and preparation of public-release materials.

Human–AI collaboration in benchmark development was kept distinct from official benchmark evaluation. Systems Under Evaluation did not score their own official responses, and model-assisted development or analysis did not replace the finalized blinded human judgments used to generate v0.1 results. The official scoring records were completed and preserved before model identities were revealed.

AI-generated or AI-assisted proposals were not treated as authoritative by virtue of their source. Final benchmark decisions, interpretations, and release responsibility remained with the human author.

## Data provenance and change control

The core v0.1 source-of-truth hierarchy is:

1. **Case YAML** — what was administered
2. **Rubric YAML** — how it was scored
3. **Execution record** — what the SUE returned
4. **Finalized scoring record** — evaluator judgment

After blinded evaluation, preserved scoring records were linked to SUE identity through the frozen private blinding maps and used to generate the official unblinded and aggregated result records. Derived CSV files, HTML displays, tables, charts, and other presentation layers are convenience artifacts rather than editable benchmark sources of truth.

The canonical manifest and release provenance records preserve cryptographic hashes for integrity verification.

Substantive changes to frozen cases, rubrics, scoring semantics, administration contracts, evaluator behavior capable of changing scores, or analysis rules require explicit versioning and documentation. Observed model performance is not used to silently revise v0.1 scoring rules.

Two non-substantive post-freeze corrections were documented during v0.1. First, an evaluator-renderer compatibility issue was corrected so that the canonical wording of PSY-002 EE01 was displayed as intended. Second, stale display wording for PSY-001 EE02 was corrected to “Identifies ≥3 distinct treatment-relevant uncertainties.” The latter concerned a non-scoring Enrichment Event. Neither correction altered SUE-facing case content, targeted scoring semantics, official model responses, or dimension scores, and neither required model re-administration.

## Limitations

PsychSafe-Eval v0.1 contains 20 synthetic cases selected to probe clinically consequential psychiatric and behavioral-health reasoning and safety. It is not a representative sample of all psychiatric encounters, clinical settings, or model-use conditions, and benchmark results should not be interpreted as estimates of real-world clinical error frequency or patient outcomes.

Coverage is intentionally uneven across dimensions because cases target specific capabilities rather than functioning as interchangeable six-dimension tests. Dimension-specific sample sizes must therefore accompany interpretation; in particular, Evidence Grounding has only two applicable case-level observations per SUE in v0.1.

All v0.1 human scoring was performed by a single evaluator. The current release therefore does not establish inter-rater reliability, and evaluator-dependent judgment remains a source of uncertainty.

CSE counts are raw counts of prospectively designated critical failures under the benchmark conditions, not estimates of population safety-event rates. EE counts are descriptive observations rather than performance scores. Neither should be converted into an undisclosed weighting scheme or combined with dimension means to produce a post hoc composite score.

Fixed multi-turn trajectories improve comparability across SUEs but do not reproduce fully adaptive clinical conversations. Similarly, synthetic and adversarially constructed scenarios can probe consequential boundary conditions efficiently but do not establish how frequently those conditions arise in routine clinical use.

Finally, v0.1 evaluates four specific model/provider paths under frozen administration configurations. Results characterize those evaluated systems under those conditions and should not be assumed to apply unchanged to subsequent model versions, provider configurations, or deployment contexts.

## Public artifacts and reproducibility

PsychSafe-Eval v0.1 is designed for public inspection. The release repository provides the benchmark materials and public provenance needed to trace reported findings from presentation-layer results back to their underlying evaluation artifacts.

Public release materials distinguish canonical benchmark sources, official execution and evaluation records, derived aggregate results, and presentation artifacts so that derived tables or website displays cannot silently replace the underlying source records.

Results should therefore be interpreted as performance under the specific v0.1 cases, rubrics, administration contracts, scoring procedure, and aggregation rules documented here—not as an undifferentiated measure of model quality or clinical safety.