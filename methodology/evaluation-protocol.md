# PsychSafe-Eval v0.1 — Official Four-SUE Pairing Protocol

Status: pre-administration frozen protocol candidate.

1. Four fresh, complete official execution records are required, one for each frozen SUE path.
2. The four records are supplied to `evaluator/workflow.py quartet` in this fixed input order: OpenAI, Anthropic, Google, xAI.
3. Quartet seed: **1203**.
4. The quartet builder randomly partitions the four records into two non-overlapping pairs using the frozen seed.
5. Each pair is passed to the paired-packet builder with a deterministically generated private pair seed.
6. Each paired packet independently randomizes case presentation order and Model A/B assignment by case.
7. Evaluator-facing outputs identify only `RUN-1`, `RUN-2`, `Model A`, and `Model B`.
8. Pair composition, provider/model identity, canonical case identity, canonical CSE identifiers, source run identity, and case-level A/B mapping remain in private maps only.
9. The evaluator completes and finalizes both runs before inspecting any private map or restoring SUE identity.
10. Pairing is not changed or rerolled on the basis of model responses or evaluator impressions.
