# Runner layer — Phase 11.3

The provider-neutral core runner is implemented in `runner/core/`.

Locked behaviors implemented here:
- manifest-driven loading only;
- exactly 20 unique manifest-listed cases per complete v0.1 run;
- independently randomized case order with recorded seed;
- fresh context for every case;
- fixed, ordered, indivisible multi-turn trajectories;
- exact canonical user content;
- complete within-case user/assistant history;
- no PsychSafe-Eval-authored system prompt by default;
- maximum 3 attempts total (initial + 2 retries);
- retries only for adapter-signaled objective `TechnicalFailure`;
- any successful substantive return is accepted without quality/safety reroll;
- raw provider return and normalized/renderable substantive output coexist;
- execution records are create-only;
- no rubric loading, scoring, CSE detection, or safety interpretation.

Provider-specific API implementations remain Phase 11.4.
