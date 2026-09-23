from __future__ import annotations

import os
from typing import Any, Dict, List

from runner.core import AdapterResult, TechnicalFailure, AdministrationFailure
from .common import dump_sdk_object, require_nonempty_text


class XAIResponsesAdapter:
    """xAI Responses API adapter for stateless Grok administration.

    PsychSafe-Eval disables server-side conversation state (``store=False``)
    and requests encrypted reasoning content.  The exact provider-native output
    items are then carried forward inside a case so multi-turn continuation does
    not depend on ``previous_response_id`` or hidden server state.
    """

    name = "xai-responses"

    def __init__(self, client: Any = None):
        self._client = client

    def _client_or_create(self):
        if self._client is not None:
            return self._client
        try:
            import httpx
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional openai and httpx packages to use XAIResponsesAdapter."
            ) from exc
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            raise AdministrationFailure("XAI_API_KEY is not set.")
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            timeout=httpx.Timeout(3600.0),
        )
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
        return status == 429 or (isinstance(status, int) and status >= 500)

    @staticmethod
    def _response_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        history: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role == "user":
                if not isinstance(content, str):
                    raise AdministrationFailure("xAI user content must be canonical text.")
                history.append({"role": "user", "content": content})
            elif role == "assistant":
                if not isinstance(content, list) or not content:
                    raise AdministrationFailure(
                        "xAI multi-turn history requires exact provider-native output items."
                    )
                for item in content:
                    if not isinstance(item, dict) or not item.get("type"):
                        raise AdministrationFailure(
                            "xAI assistant history contained an invalid provider-native output item."
                        )
                    history.append(dict(item))
            else:
                raise AdministrationFailure(f"Unsupported xAI history role: {role!r}")
        return history

    def generate(
        self, *, model: str, messages: List[Dict[str, Any]], parameters: Dict[str, Any]
    ) -> AdapterResult:
        client = self._client_or_create()
        params = dict(parameters)

        if params.pop("store", False) not in (False, None):
            raise AdministrationFailure("xAI PsychSafe-Eval administration requires store=False.")
        if "previous_response_id" in params:
            raise AdministrationFailure(
                "xAI PsychSafe-Eval administration forbids previous_response_id."
            )
        if any(k in params for k in ("tools", "tool_choice", "parallel_tool_calls")):
            raise AdministrationFailure("xAI PsychSafe-Eval administration forbids tools.")

        # Encrypted reasoning is required for provider-native stateless
        # continuation.  Do not allow callers to silently omit or replace it.
        include = params.pop("include", None)
        if include not in (None, ["reasoning.encrypted_content"]):
            raise AdministrationFailure(
                "xAI PsychSafe-Eval administration requires only reasoning.encrypted_content include."
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
                raise TechnicalFailure(f"xAI {type(exc).__name__}: {exc}") from exc
            raise AdministrationFailure(
                f"xAI non-retryable API/configuration failure ({type(exc).__name__}): {exc}"
            ) from exc

        raw = dump_sdk_object(response)
        status = getattr(response, "status", None)
        if status in {"failed", "cancelled"}:
            raise TechnicalFailure(
                f"xAI response status={status}: {getattr(response, 'error', None)}"
            )

        text = require_nonempty_text(getattr(response, "output_text", None), "xAI")
        # xAI continuation state is provider-native and opaque.  Serialize
        # returned output items exactly as required for stateless replay,
        # omitting SDK fields whose value is None.  Retaining those fields can
        # invalidate xAI's encrypted/compacted continuation blob.
        output_items = []
        for item in (getattr(response, "output", None) or []):
            model_dump = getattr(item, "model_dump", None)
            if not callable(model_dump):
                raise AdministrationFailure(
                    "xAI returned an output item that cannot be faithfully serialized."
                )
            output_items.append(model_dump(exclude_none=True))
        if not output_items:
            raise AdministrationFailure("xAI returned text without provider-native output items.")

        reasoning_items = [item for item in output_items if item.get("type") == "reasoning"]
        if not reasoning_items or not all(item.get("encrypted_content") for item in reasoning_items):
            raise AdministrationFailure(
                "xAI response omitted encrypted reasoning required for stateless continuation."
            )

        return AdapterResult(
            raw_response=raw,
            substantive_output=text,
            finish_info={
                "status": status,
                "error": dump_sdk_object(getattr(response, "error", None)),
                "incomplete_details": dump_sdk_object(
                    getattr(response, "incomplete_details", None)
                ),
            },
            provider_metadata={
                "response_id": getattr(response, "id", None),
                "model": getattr(response, "model", model),
                "usage": dump_sdk_object(getattr(response, "usage", None)),
                "num_sources_used": getattr(getattr(response, "usage", None), "num_sources_used", None),
                "num_server_side_tools_used": getattr(
                    getattr(response, "usage", None), "num_server_side_tools_used", None
                ),
                "assistant_message_content": output_items,
            },
        )
