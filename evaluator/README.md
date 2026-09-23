# Blinded evaluator layer — paired human-interface candidate

The evaluator interface is a self-contained local HTML file. Canonical case identity and provider/model identity remain outside the evaluator-facing packet.

## Build a paired blinded packet

```bash
python evaluator/workflow.py pair <execution-A.json> <execution-B.json> <output_dir> --evaluator-id RATER-001 --seed 1203
```

The pairing seed controls randomized case order and independent Model A/B assignment within each case. `BLINDING_MAP.json` retains the private linkage. The evaluator-facing packet contains only run-local case numbering and Model A/B labels.

## Render the interface

```bash
python evaluator/interface.py <output_dir>/BLINDED_EVALUATION_PACKET.json <output_dir>/EVALUATOR_INTERFACE.html
open <output_dir>/EVALUATOR_INTERFACE.html
```

Key behavior: one case per screen; two blinded responses switchable as Model A/B; complete rubric in one scroll; targeted dimensions → Enrichment Events → non-targeted dimensions; automatic local autosave; draggable pane divider; sanitized Markdown rendering; exceptional targeted N/A requires explanation; missing required fields block forward navigation with visible highlighting; sequential forward case unlocking with backward review; final `Review & Complete` creates the finalized scoring record.

## Validate finalized scoring

```bash
python evaluator/workflow.py validate <packet.json> <scoring.json>
```

The legacy single-run `build` command remains available only for reproducibility of earlier workflow artifacts; the revised human interface requires paired schema 2.0 packets.

## Four-SUE official evaluation packet construction

For the official four-SUE evaluation, use the `quartet` command after all four fresh official execution records are complete. Supply the four records in the frozen provider order: OpenAI, Anthropic, Google, xAI. The default quartet seed is 1203.

```bash
python evaluator/workflow.py quartet \
  <openai-execution.json> <anthropic-execution.json> <google-execution.json> <xai-execution.json> \
  <output_dir> --evaluator-id <EVALUATOR_ID> --seed 1203
```

This creates `RUN-1/` and `RUN-2/` evaluator-facing paired packets plus `EVALUATOR_RUN_INDEX.json`. Pair composition and canonical identities are retained only in `PRIVATE_FOUR_SUE_MAP.json` and each run's `BLINDING_MAP.json`. The evaluator must not inspect those private maps until both evaluation runs are finalized.
