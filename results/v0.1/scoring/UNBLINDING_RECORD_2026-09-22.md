# PsychSafe-Eval v0.1 — Unblinding Record

Date: 2026-09-22

## Pre-unblinding checkpoint

Archive:
psychsafe-eval-v0.1-post-evaluation-pre-unblinding-2026-09-22.zip

SHA-256:
17d36613fd60ca9b2a5d42e634d8b7f43da69028499317fd5d52093dd9a9f33c

The checkpoint was created only after both blinded human-evaluation
runs had been finalized, validated, and preserved byte-for-byte.

## Finalized blinded scoring records

RUN-1:
official_evaluation_v0.1/RUN-1/FINALIZED_SCORING_RECORD.json
SHA-256:
5ec122989cfc6822d75aaf020be903bfda60c653cb4b10f58a7c9f4323aa3b65

RUN-2:
official_evaluation_v0.1/RUN-2/FINALIZED_SCORING_RECORD.json
SHA-256:
5904be92020b25ce4b832abf47593fa37dd35c1c994e4f8b99b78404ed57bc68

## Quartet unblinding

Quartet seed: 1203

RUN-1 SUE pair:
- OpenAI / gpt-5.6-sol
- Gemini / gemini-3.1-pro-preview

RUN-2 SUE pair:
- Anthropic / claude-opus-5
- xAI / grok-4.6

Per-case response identity was determined exclusively from the
authoritative private BLINDING_MAP.json files, not from response content.

## Response-level unblinding

Derived artifact:
official_evaluation_v0.1/UNBLINDED_SCORING_RECORD.json

SHA-256:
18bb92cc6d5e06630c3fff2194907cd9716c70e55f456b2e1dc4be7bde8966b5

Validation:
- joined finalized evaluations: 80
- canonical cases: 20
- evaluations per SUE: 20
- each canonical case represented exactly once by each of the four SUEs
- blinded_set_id joins: validated
- evaluator_id joins: validated
- presentation_index joins: validated
- response_id joins: validated
- duplicate joined records: 0

## Methodological boundary

All human scoring decisions were finalized and cryptographically
preserved before SUE identities were revealed.

UNBLINDED_SCORING_RECORD.json is a derived artifact. The two finalized
blinded scoring records remain the immutable human-judgment
sources of truth.
