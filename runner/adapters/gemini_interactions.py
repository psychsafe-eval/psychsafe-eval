from __future__ import annotations

from typing import Any, Dict, List

from runner.core import AdapterResult, TechnicalFailure, AdministrationFailure
from .common import dump_sdk_object, require_nonempty_text


class GeminiInteractionsAdapter:
    """Google Gemini Interactions API adapter.

    PsychSafe-Eval uses stateless Interactions (``store=False``) and carries the
    provider's model-generated steps forward verbatim inside each case. This is
    required for Gemini thinking signatures and prevents server-side state from
    becoming an uncontrolled administration variable.
    """

    name = "gemini-interactions"

    def __init__(self, client: Any = None):
        self._client = client

    def _client_or_create(self):
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional google-genai SDK to use GeminiInteractionsAdapter."
            ) from exc
        self._client = genai.Client()
        return self._client

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> bool:
        name = type(exc).__name__
        if name in {
            "APIConnectionError", "APITimeoutError", "RateLimitError",
            "InternalServerError", "ServerError", "ServiceUnavailableError",
        }:
            return True
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(exc, "code", None)
        return status == 429 or (isinstance(status, int) and status >= 500)

    @staticmethod
    def _interaction_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert provider-neutral history to Gemini stateless interaction steps.

        User messages become ``user_input`` steps. Assistant content must be the
        exact list of model-generated step dictionaries returned by Gemini on the
        preceding turn; those steps (including encrypted thought signatures) are
        spliced into history unchanged.
        """
        history: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role == "user":
                if not isinstance(content, str):
                    raise AdministrationFailure("Gemini user content must be canonical text.")
                history.append({
                    "type": "user_input",
                    "content": [{"type": "text", "text": content}],
                })
            elif role == "assistant":
                if not isinstance(content, list) or not content:
                    raise AdministrationFailure(
                        "Gemini multi-turn history requires exact provider-native assistant steps."
                    )
                for step in content:
                    if not isinstance(step, dict) or not step.get("type"):
                        raise AdministrationFailure(
                            "Gemini assistant history contained an invalid provider-native step."
                        )
                    history.append(dict(step))
            else:
                raise AdministrationFailure(f"Unsupported Gemini history role: {role!r}")
        return history

    def generate(
        self, *, model: str, messages: List[Dict[str, Any]], parameters: Dict[str, Any]
    ) -> AdapterResult:
        client = self._client_or_create()
        params = dict(parameters)

        # PsychSafe-Eval locks stateless administration. A caller cannot silently
        # enable server-side persistence or previous-interaction state.
        if params.pop("store", False) not in (False, None):
            raise AdministrationFailure("Gemini PsychSafe-Eval administration requires store=False.")
        if "previous_interaction_id" in params:
            raise AdministrationFailure(
                "Gemini PsychSafe-Eval administration forbids previous_interaction_id."
            )
        if any(k in params for k in ("tools", "tool_config", "agent", "environment")):
            raise AdministrationFailure("Gemini PsychSafe-Eval administration forbids tools/agents.")

        interaction_input = self._interaction_input(messages)

        try:
            response = client.interactions.create(
                model=model,
                input=interaction_input,
                store=False,
                **params,
            )
        except Exception as exc:
            if self._is_retryable_exception(exc):
                raise TechnicalFailure(f"Gemini {type(exc).__name__}: {exc}") from exc
            raise AdministrationFailure(
                f"Gemini non-retryable API/configuration failure "
                f"({type(exc).__name__}): {exc}"
            ) from exc

        raw = dump_sdk_object(response)
        status = getattr(response, "status", None)
        if status in {"failed", "cancelled"}:
            raise TechnicalFailure(
                f"Gemini interaction status={status}: {getattr(response, 'error', None)}"
            )

        # Completed/other returned states with text are substantive outcomes;
        # never reroll them based on response quality or length.
        text = require_nonempty_text(getattr(response, "output_text", None), "Gemini")
        steps = [dump_sdk_object(step) for step in (getattr(response, "steps", None) or [])]
        if not steps:
            raise AdministrationFailure("Gemini returned text without provider-native steps.")

        return AdapterResult(
            raw_response=raw,
            substantive_output=text,
            finish_info={
                "status": status,
                "error": dump_sdk_object(getattr(response, "error", None)),
            },
            provider_metadata={
                "interaction_id": getattr(response, "id", None),
                "model": getattr(response, "model", model),
                "service_tier": getattr(response, "service_tier", None),
                "usage": dump_sdk_object(getattr(response, "usage", None)),
                # Exact model-generated steps are required for stateless
                # multi-turn continuity, especially encrypted thought signatures.
                "assistant_message_content": steps,
            },
        )
