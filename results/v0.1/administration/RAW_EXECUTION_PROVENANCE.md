# Raw execution provenance

The authoritative provider-native execution records are retained outside the public repository. Public `PUBLIC_EXECUTION.json` files preserve the exact submitted-message trajectories and exact substantive model outputs, while removing provider-native raw envelopes, response identifiers, signatures/encrypted reasoning payloads, and other operational metadata. No substantive output text was edited.

| Provider | Model | Official run ID | SHA-256 of authoritative raw `execution.json` |
|---|---|---|---|
| openai | gpt-5.6-sol | 6db69a18-bf3b-4549-adc5-622d44033bff | ec76a3f427d7ad9df401875bdd5d024b4586a22d2c8a4d79e400a326a587a848 |
| anthropic | claude-opus-5 | 8e72f8fa-6ab0-4cf0-ab5e-9dfc5d783bce | 49779f17cd0c4abff38e511efc9e29d6524015d88a800a3b25ffbb5952b28455 |
| gemini | gemini-3.1-pro-preview | f0ea074b-8afb-4661-a209-e9fb175b5e7b | 3654d0daf712f7eb1ac2286de65fdbaebb691247629d3f1a105356be6e38c475 |
| xai | grok-4.6 | fc49a8e8-8c90-4ef8-8be7-fa277b9399e3 | 63638630e96584bf9e9b4ad13d7e74be0c8dc5a838b2a5d064113111071a1f96 |
