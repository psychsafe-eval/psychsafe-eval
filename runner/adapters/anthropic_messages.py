from __future__ import annotations

from typing import Any, Dict, List

from runner.core import AdapterResult, TechnicalFailure, AdministrationFailure, IndeterminateAdministrationFailure

from .common import dump_sdk_object


class AnthropicMessagesAdapter:

    """Direct Claude Messages API adapter."""

    name = "anthropic-messages"

    def __init__(self, client: Any = None):
        self._client = client

    def _client_or_create(self):
        if self._client is not None:
            return self._client

        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional Anthropic SDK to use AnthropicMessagesAdapter."
            ) from exc

        self._client = anthropic.Anthropic()
        return self._client

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> bool:
        # 429/5xx/timeout/connection/overload are retryable technical failures.
        name = type(exc).__name__
        if name in {
            "APIConnectionError",
            "APITimeoutError",
            "RateLimitError",
            "InternalServerError",
            "OverloadedError",
        }:
            return True

        status = getattr(exc, "status_code", None)
        return status == 429 or (isinstance(status, int) and status >= 500)

    @staticmethod
    def _validate_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Preserve canonical user text and provider-native assistant blocks."""
        prepared: List[Dict[str, Any]] = []

        for message in messages:
            role = message.get("role")
            content = message.get("content")

            if role == "user":
                if not isinstance(content, str):
                    raise AdministrationFailure(
                        "Anthropic user content must be canonical text."
                    )
                prepared.append({"role": "user", "content": content})
                continue

            if role == "assistant":
                if not isinstance(content, list) or not content:
                    raise AdministrationFailure(
                        "Anthropic assistant history must contain nonempty "
                        "provider-native content blocks."
                    )
                if not all(isinstance(block, dict) for block in content):
                    raise AdministrationFailure(
                        "Anthropic assistant history contained a non-dict "
                        "provider-native content block."
                    )
                prepared.append({"role": "assistant", "content": content})
                continue

            raise AdministrationFailure(
                f"Anthropic history contained unsupported role: {role!r}."
            )

        return prepared

    def count_input_tokens(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        parameters: Dict[str, Any],
    ) -> int:
        """Count model-visible input tokens without generating a response.

        ``max_tokens`` is output-only and is intentionally omitted from the
        count request.
        """
        client = self._client_or_create()
        params = dict(parameters)
        params.pop("max_tokens", None)

        # Official benchmark administration permits no Anthropic tools.
        for prohibited in ("tools", "tool_choice"):
            if prohibited in params:
                raise AdministrationFailure(
                    f"Anthropic benchmark administration prohibits {prohibited}."
                )

        prepared_messages = self._validate_messages(messages)

        try:
            counted = client.messages.count_tokens(
                model=model,
                messages=prepared_messages,
                **params,
            )
        except Exception as exc:
            if self._is_retryable_exception(exc):
                raise TechnicalFailure(
                    f"Anthropic token-count {type(exc).__name__}: {exc}"
                ) from exc
            raise AdministrationFailure(
                f"Anthropic token-count failure ({type(exc).__name__}): {exc}"
            ) from exc

        value = getattr(counted, "input_tokens", None)
        if not isinstance(value, int) or value < 0:
            raise AdministrationFailure(
                "Anthropic token-count response lacked valid input_tokens."
            )

        return value

    def generate(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        parameters: Dict[str, Any],
    ) -> AdapterResult:
        client = self._client_or_create()
        params = dict(parameters)

        # The official administration contract must specify the output ceiling
        # explicitly. Never silently substitute a smaller default.
        if "max_tokens" not in params:
            raise AdministrationFailure(
                "Anthropic benchmark administration requires explicit max_tokens."
            )

        max_tokens = params.pop("max_tokens")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
            raise AdministrationFailure(
                "Anthropic max_tokens must be a positive integer."
            )

        # No provider tools or tool-routing controls are permitted.
        for prohibited in ("tools", "tool_choice"):
            if prohibited in params:
                raise AdministrationFailure(
                    f"Anthropic benchmark administration prohibits {prohibited}."
                )

        prepared_messages = self._validate_messages(messages)

        try:
            # Large Opus 5 output ceilings require streaming in the Anthropic
            # Python SDK. The benchmark consumes only the reconstructed final
            # Message object, not incremental stream events.
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                messages=prepared_messages,
                **params,
            ) as stream:
                try:
                    response = stream.get_final_message()
                except Exception as exc:
                    name = type(exc).__name__
                    if name in {
                        "ReadTimeout",
                        "APITimeoutError",
                        "APIConnectionError",
                        "ReadError",
                        "RemoteProtocolError",
                    }:
                        raise IndeterminateAdministrationFailure(
                            "Anthropic generation was dispatched, but the final "
                            "streamed response was not received; provider-side "
                            "completion is indeterminate and automatic retry is "
                            f"prohibited ({name}): {exc}"
                        ) from exc
                    raise

        except IndeterminateAdministrationFailure:
            raise
        except Exception as exc:
            if self._is_retryable_exception(exc):
                raise TechnicalFailure(
                    f"Anthropic {type(exc).__name__}: {exc}"
                ) from exc
            raise AdministrationFailure(
                "Anthropic non-retryable API/configuration failure "
                f"({type(exc).__name__}): {exc}"
            ) from exc

        raw = dump_sdk_object(response)
        content = getattr(response, "content", None) or []
        stop_reason = getattr(response, "stop_reason", None)

        if not content:
            raise AdministrationFailure(
                "Anthropic returned no provider-native content blocks."
            )

        assistant_message_content: List[Dict[str, Any]] = []
        text_parts: List[str] = []

        for block in content:
            model_dump = getattr(block, "model_dump", None)
            if not callable(model_dump):
                raise AdministrationFailure(
                    "Anthropic returned a content block that cannot be "
                    "faithfully serialized."
                )

            native_block = model_dump(exclude_none=True)
            if not isinstance(native_block, dict):
                raise AdministrationFailure(
                    "Anthropic content-block serialization did not produce a dict."
                )

            block_type = native_block.get("type")

            if block_type == "thinking" and not native_block.get("signature"):
                raise AdministrationFailure(
                    "Anthropic returned a thinking block without its required signature."
                )

            if block_type == "text":
                block_text = native_block.get("text")
                if isinstance(block_text, str):
                    text_parts.append(block_text)

            assistant_message_content.append(native_block)

        text = "".join(text_parts)

        # A provider-native textless refusal is a substantive model outcome,
        # not a technical failure and not eligible for reroll. Other empty
        # returns remain administration failures.
        if not text.strip() and stop_reason != "refusal":
            raise AdministrationFailure(
                "Anthropic returned no substantive text outside a refusal outcome."
            )

        return AdapterResult(
            raw_response=raw,
            substantive_output=text,
            finish_info={
                "stop_reason": stop_reason,
                "stop_sequence": getattr(response, "stop_sequence", None),
            },
            provider_metadata={
                "response_id": getattr(response, "id", None),
                "model": getattr(response, "model", model),
                "usage": dump_sdk_object(getattr(response, "usage", None)),
                # Preserve exact provider-native assistant content so signed
                # thinking state can be replayed on the next fixed turn.
                "assistant_message_content": assistant_message_content,
            },
        )
