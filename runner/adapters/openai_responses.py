from __future__ import annotations

from typing import Any, Dict, List

from runner.core import AdapterResult, TechnicalFailure, AdministrationFailure

from .common import dump_sdk_object, require_nonempty_text


class OpenAIResponsesAdapter:
    """OpenAI Responses API adapter for stateless PsychSafe-Eval administration.

    PsychSafe-Eval disables server-side conversation state (``store=False``)
    and explicitly requests encrypted reasoning content. Exact provider-native
    output items are carried forward inside a case so multi-turn continuation
    does not depend on ``previous_response_id`` or hidden server state.

    OpenAI may legitimately return no reasoning item on a turn that uses zero
    reasoning tokens. When reasoning items are returned, their encrypted
    content must be preserved for faithful stateless continuation.
    """

    name = "openai-responses"

    def __init__(self, client: Any = None):
        self._client = client

    def _client_or_create(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional OpenAI SDK to use OpenAIResponsesAdapter."
            ) from exc
        self._client = OpenAI()
        return self._client

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> bool:
        # Prefer typed SDK classes without requiring the package at import time.
        name = type(exc).__name__
        if name in {
            "APIConnectionError",
            "APITimeoutError",
            "RateLimitError",
            "InternalServerError",
            "ServerError",
            "ServiceUnavailableError",
        }:
            return True
        status = getattr(exc, "status_code", None)
        return status == 429 or (isinstance(status, int) and status >= 500)

    @staticmethod
    def _response_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        history: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")

            if role == "user":
                if not isinstance(content, str):
                    raise AdministrationFailure(
                        "OpenAI user content must be canonical text."
                    )
                history.append({"role": "user", "content": content})

            elif role == "assistant":
                if not isinstance(content, list) or not content:
                    raise AdministrationFailure(
                        "OpenAI multi-turn history requires exact "
                        "provider-native output items."
                    )
                for item in content:
                    if not isinstance(item, dict) or not item.get("type"):
                        raise AdministrationFailure(
                            "OpenAI assistant history contained an invalid "
                            "provider-native output item."
                        )
                    history.append(dict(item))

            else:
                raise AdministrationFailure(
                    f"Unsupported OpenAI history role: {role!r}"
                )

        return history

    def generate(
        self, *, model: str, messages: List[Dict[str, Any]], parameters: Dict[str, Any]
    ) -> AdapterResult:
        client = self._client_or_create()
        params = dict(parameters)

        # PsychSafe-Eval requires client-managed stateless continuation.
        if params.pop("store", False) not in (False, None):
            raise AdministrationFailure(
                "OpenAI PsychSafe-Eval administration requires store=False."
            )

        if "previous_response_id" in params:
            raise AdministrationFailure(
                "OpenAI PsychSafe-Eval administration forbids previous_response_id."
            )

        if any(k in params for k in ("tools", "tool_choice", "parallel_tool_calls")):
            raise AdministrationFailure(
                "OpenAI PsychSafe-Eval administration forbids tools."
            )

        # Explicitly request encrypted reasoning for provider-native stateless
        # continuation. Do not allow callers to silently omit or replace it.
        include = params.pop("include", None)
        if include not in (None, ["reasoning.encrypted_content"]):
            raise AdministrationFailure(
                "OpenAI PsychSafe-Eval administration requires only "
                "reasoning.encrypted_content include."
            )

        response_input = self._response_input(messages)

        try:
            response = client.responses.create(
                model=model,
                input=response_input,
                store=False,
                include=["reasoning.encrypted_content"],
                **params,
            )
        except Exception as exc:
            if self._is_retryable_exception(exc):
                raise TechnicalFailure(
                    f"OpenAI {type(exc).__name__}: {exc}"
                ) from exc
            # Authentication, invalid request, nonexistent model, etc. are
            # configuration/administration failures, not retryable transport failures.
            raise AdministrationFailure(
                f"OpenAI non-retryable API/configuration failure "
                f"({type(exc).__name__}): {exc}"
            ) from exc

        raw = dump_sdk_object(response)
        status = getattr(response, "status", None)

        if status in {"failed", "cancelled"}:
            raise TechnicalFailure(
                f"OpenAI response status={status}: "
                f"{getattr(response, 'error', None)}"
            )

        # "incomplete" is still a substantive provider return when text exists;
        # do not reroll merely because generation ended early.
        text = require_nonempty_text(
            getattr(response, "output_text", None), "OpenAI"
        )

        # Preserve exact provider-native output items for within-case replay.
        # Omit SDK fields whose value is None rather than introducing null
        # fields that were not part of the provider-native continuation state.
        output_items = []
        for item in (getattr(response, "output", None) or []):
            model_dump = getattr(item, "model_dump", None)
            if not callable(model_dump):
                raise AdministrationFailure(
                    "OpenAI returned an output item that cannot be faithfully serialized."
                )
            output_items.append(model_dump(exclude_none=True))

        if not output_items:
            raise AdministrationFailure(
                "OpenAI returned text without provider-native output items."
            )

        # A reasoning item is not required on every turn: GPT-5.6 Sol may use
        # zero reasoning tokens and return only a message item. But whenever a
        # reasoning item is present, encrypted_content is required so that its
        # provider-native state can be faithfully replayed.
        reasoning_items = [
            item for item in output_items if item.get("type") == "reasoning"
        ]
        if reasoning_items and not all(
            item.get("encrypted_content") for item in reasoning_items
        ):
            raise AdministrationFailure(
                "OpenAI response included reasoning without encrypted content "
                "required for stateless continuation."
            )

        incomplete = dump_sdk_object(
            getattr(response, "incomplete_details", None)
        )
        error = dump_sdk_object(getattr(response, "error", None))

        return AdapterResult(
            raw_response=raw,
            substantive_output=text,
            finish_info={
                "status": status,
                "incomplete_details": incomplete,
                "error": error,
            },
            provider_metadata={
                "response_id": getattr(response, "id", None),
                "model": getattr(response, "model", model),
                "usage": dump_sdk_object(getattr(response, "usage", None)),
                "assistant_message_content": output_items,
            },
        )
