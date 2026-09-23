# Provider adapters

Adapters:

- `OpenAIResponsesAdapter` — OpenAI Responses API
- `AnthropicMessagesAdapter` — Anthropic Messages API
- `GeminiInteractionsAdapter` — Google Gemini Interactions API
- `XAIResponsesAdapter` — xAI Responses API (Grok)

All satisfy the provider-neutral result contract and use lazy SDK imports. Mechanical tests inject fake clients, so credentials or live calls are not required.

## Outcome classification

A returned substantive model response is preserved as the benchmark outcome even when it is a refusal, truncated/incomplete, poor, unsafe, short, or otherwise undesirable. Those are not retry criteria.

Retries are reserved for objective transient technical failures such as transport/timeouts, rate limits, and server/overload errors. Authentication errors, malformed requests, invalid parameters, nonexistent models, and comparable configuration defects are administration failures rather than retryable model attempts.

## State and raw data

OpenAI defaults `store=False`. Gemini requires `store=False` and forbids `previous_interaction_id`; its model-generated steps are preserved and resent exactly for stateless multi-turn continuity, including encrypted thought signatures. xAI likewise requires `store=False`, forbids `previous_response_id`, requests `reasoning.encrypted_content`, and preserves/resends exact provider-native output items for stateless multi-turn continuation. Provider responses are preserved in JSON-serializable form separately from normalized substantive text.

Provider adapters contain no rubric, scoring, CSE, or safety-interpretation logic.
