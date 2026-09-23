from types import SimpleNamespace
import pytest

from runner.adapters import OpenAIResponsesAdapter, AnthropicMessagesAdapter
from runner.core import TechnicalFailure, AdministrationFailure, IndeterminateAdministrationFailure


class FakeOpenAIResponses:
    def __init__(self, response=None, exc=None):
        self.response=response; self.exc=exc; self.calls=[]
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc: raise self.exc
        return self.response

class FakeOpenAIClient:
    def __init__(self, response=None, exc=None):
        self.responses=FakeOpenAIResponses(response, exc)

class FakeAnthropicStream:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc

    def __enter__(self):
        if self.exc:
            raise self.exc
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get_final_message(self):
        if self.exc:
            raise self.exc
        return self.response


class FakeAnthropicMessages:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeAnthropicStream(self.response, self.exc)


class FakeAnthropicClient:
    def __init__(self, response=None, exc=None):
        self.messages = FakeAnthropicMessages(response, exc)

def exc_type(name, status=None):
    cls=type(name,(Exception,),{})
    e=cls("fixture")
    if status is not None: e.status_code=status
    return e

def test_openai_success_preserves_raw_and_store_false():
    resp=SimpleNamespace(
        id="resp_fixture", model="fixture-model", status="completed",
        output_text="fixture answer", incomplete_details=None, error=None,
        usage={"input_tokens":10,"output_tokens":3},
        output=[
            SimpleNamespace(
                type="message",
                model_dump=lambda **kwargs: {
                    "type":"message",
                    "role":"assistant",
                    "status":"completed",
                    "content":[{"type":"output_text","text":"fixture answer","annotations":[]}],
                },
            )
        ],
        model_dump=lambda: {"id":"resp_fixture","status":"completed","output_text":"fixture answer"}
    )
    client=FakeOpenAIClient(resp)
    result=OpenAIResponsesAdapter(client).generate(
        model="fixture-model", messages=[{"role":"user","content":"hello"}], parameters={}
    )
    assert result.substantive_output=="fixture answer"
    assert result.raw_response["id"]=="resp_fixture"
    assert client.responses.calls[0]["store"] is False

def test_openai_incomplete_with_text_is_substantive_not_failure():
    resp=SimpleNamespace(
        id="r", model="m", status="incomplete", output_text="partial answer",
        incomplete_details={"reason":"max_output_tokens"}, error=None, usage=None,
        output=[
            SimpleNamespace(
                type="message",
                model_dump=lambda **kwargs: {
                    "type":"message",
                    "role":"assistant",
                    "status":"incomplete",
                    "content":[{"type":"output_text","text":"partial answer","annotations":[]}],
                },
            )
        ],
        model_dump=lambda: {"status":"incomplete","output_text":"partial answer"}
    )
    result=OpenAIResponsesAdapter(FakeOpenAIClient(resp)).generate(
        model="m", messages=[{"role":"user","content":"x"}], parameters={}
    )
    assert result.substantive_output=="partial answer"
    assert result.finish_info["status"]=="incomplete"

def test_openai_retryable_vs_nonretryable_errors():
    with pytest.raises(TechnicalFailure):
        OpenAIResponsesAdapter(FakeOpenAIClient(exc=exc_type("RateLimitError"))).generate(
            model="m", messages=[{"role":"user","content":"x"}], parameters={}
        )
    with pytest.raises(AdministrationFailure):
        OpenAIResponsesAdapter(FakeOpenAIClient(exc=exc_type("AuthenticationError"))).generate(
            model="m", messages=[{"role":"user","content":"x"}], parameters={}
        )

def _anthropic_block(data, calls=None):
    if calls is None:
        calls = []

    def model_dump(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("exclude_none"):
            return {k: v for k, v in data.items() if v is not None}
        return dict(data)

    return SimpleNamespace(
        type=data.get("type"),
        text=data.get("text"),
        thinking=data.get("thinking"),
        signature=data.get("signature"),
        model_dump=model_dump,
    )


def _anthropic_response(*, content, stop_reason="end_turn", model="claude-opus-5"):
    return SimpleNamespace(
        id="msg_fixture",
        model=model,
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage={"input_tokens": 10},
        model_dump=lambda: {
            "id": "msg_fixture",
            "model": model,
            "stop_reason": stop_reason,
        },
    )


def test_anthropic_streaming_success_joins_text_blocks_and_uses_explicit_max_tokens():
    blocks = [
        _anthropic_block({"type": "text", "text": "hello ", "citations": None}),
        _anthropic_block({"type": "text", "text": "world", "citations": None}),
    ]
    resp = _anthropic_response(content=blocks, model="fixture-model")
    client = FakeAnthropicClient(resp)

    result = AnthropicMessagesAdapter(client).generate(
        model="fixture-model",
        messages=[{"role": "user", "content": "hello"}],
        parameters={"max_tokens": 128000},
    )

    assert result.substantive_output == "hello world"
    assert client.messages.calls[0]["max_tokens"] == 128000
    assert result.provider_metadata["assistant_message_content"] == [
        {"type": "text", "text": "hello "},
        {"type": "text", "text": "world"},
    ]


def test_anthropic_refusal_text_is_preserved_as_substantive_outcome():
    resp = _anthropic_response(
        content=[
            _anthropic_block(
                {"type": "text", "text": "I can’t help with that.", "citations": None}
            )
        ],
        stop_reason="refusal",
        model="fixture",
    )

    result = AnthropicMessagesAdapter(FakeAnthropicClient(resp)).generate(
        model="fixture",
        messages=[{"role": "user", "content": "x"}],
        parameters={"max_tokens": 128000},
    )

    assert result.finish_info["stop_reason"] == "refusal"
    assert "help" in result.substantive_output


def test_anthropic_textless_refusal_is_substantive_and_preserves_signed_thinking():
    dump_calls = []
    thinking = _anthropic_block(
        {"type": "thinking", "thinking": "", "signature": "signed-refusal"},
        dump_calls,
    )
    resp = _anthropic_response(
        content=[thinking],
        stop_reason="refusal",
    )

    result = AnthropicMessagesAdapter(FakeAnthropicClient(resp)).generate(
        model="claude-opus-5",
        messages=[{"role": "user", "content": "x"}],
        parameters={
            "max_tokens": 128000,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "max"},
        },
    )

    assert result.substantive_output == ""
    assert result.finish_info["stop_reason"] == "refusal"
    assert result.provider_metadata["assistant_message_content"] == [
        {"type": "thinking", "thinking": "", "signature": "signed-refusal"}
    ]
    assert dump_calls == [{"exclude_none": True}]


def test_anthropic_post_dispatch_read_timeout_is_indeterminate():
    # Raise only after the stream has been entered, reproducing the failure
    # stage observed during the interrupted SUE-2 administration.
    read_timeout = exc_type("ReadTimeout")

    class FinalMessageReadTimeoutStream:
        def __enter__(self):
            return self

        def __exit__(self, exc_type_, exc, tb):
            return False

        def get_final_message(self):
            raise read_timeout

    class Messages:
        def __init__(self):
            self.calls = []

        def stream(self, **kwargs):
            self.calls.append(kwargs)
            return FinalMessageReadTimeoutStream()

    client = SimpleNamespace(messages=Messages())

    with pytest.raises(IndeterminateAdministrationFailure):
        AnthropicMessagesAdapter(client).generate(
            model="m",
            messages=[{"role": "user", "content": "x"}],
            parameters={"max_tokens": 128000},
        )


def test_anthropic_retryable_status_and_nonretryable_400():
    with pytest.raises(TechnicalFailure):
        AnthropicMessagesAdapter(
            FakeAnthropicClient(exc=exc_type("APIStatusError", 529))
        ).generate(
            model="m",
            messages=[{"role": "user", "content": "x"}],
            parameters={"max_tokens": 128000},
        )

    with pytest.raises(AdministrationFailure):
        AnthropicMessagesAdapter(
            FakeAnthropicClient(exc=exc_type("BadRequestError", 400))
        ).generate(
            model="m",
            messages=[{"role": "user", "content": "x"}],
            parameters={"max_tokens": 128000},
        )


def test_anthropic_preserves_native_assistant_content_for_multiturn_thinking():
    thinking_calls = []
    text_calls = []

    thinking = _anthropic_block(
        {"type": "thinking", "thinking": "", "signature": "sig"},
        thinking_calls,
    )
    text_block = _anthropic_block(
        {"type": "text", "text": "answer", "citations": None},
        text_calls,
    )
    resp = _anthropic_response(content=[thinking, text_block])

    result = AnthropicMessagesAdapter(FakeAnthropicClient(resp)).generate(
        model="claude-opus-5",
        messages=[{"role": "user", "content": "x"}],
        parameters={
            "max_tokens": 128000,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "max"},
        },
    )

    assert result.substantive_output == "answer"
    assert result.provider_metadata["assistant_message_content"] == [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "answer"},
    ]
    assert thinking_calls == [{"exclude_none": True}]
    assert text_calls == [{"exclude_none": True}]


def test_anthropic_multiturn_resends_exact_provider_native_assistant_blocks():
    native = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "TURN1_OK"},
    ]
    resp = _anthropic_response(
        content=[_anthropic_block({"type": "text", "text": "ORCHID"})]
    )
    client = FakeAnthropicClient(resp)

    result = AnthropicMessagesAdapter(client).generate(
        model="claude-opus-5",
        messages=[
            {"role": "user", "content": "Remember ORCHID."},
            {"role": "assistant", "content": native},
            {"role": "user", "content": "What was the word?"},
        ],
        parameters={
            "max_tokens": 128000,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "max"},
        },
    )

    assert result.substantive_output == "ORCHID"
    assert client.messages.calls[0]["messages"] == [
        {"role": "user", "content": "Remember ORCHID."},
        {"role": "assistant", "content": native},
        {"role": "user", "content": "What was the word?"},
    ]


def test_anthropic_rejects_missing_max_tokens_tools_and_unsigned_thinking():
    with pytest.raises(AdministrationFailure):
        AnthropicMessagesAdapter(FakeAnthropicClient()).generate(
            model="claude-opus-5",
            messages=[{"role": "user", "content": "x"}],
            parameters={},
        )

    with pytest.raises(AdministrationFailure):
        AnthropicMessagesAdapter(FakeAnthropicClient()).generate(
            model="claude-opus-5",
            messages=[{"role": "user", "content": "x"}],
            parameters={
                "max_tokens": 128000,
                "tools": [{"name": "fixture"}],
            },
        )

    unsigned = _anthropic_response(
        content=[
            _anthropic_block(
                {"type": "thinking", "thinking": "", "signature": ""}
            )
        ],
        stop_reason="refusal",
    )

    with pytest.raises(AdministrationFailure):
        AnthropicMessagesAdapter(FakeAnthropicClient(unsigned)).generate(
            model="claude-opus-5",
            messages=[{"role": "user", "content": "x"}],
            parameters={
                "max_tokens": 128000,
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": "max"},
            },
        )


def test_anthropic_empty_end_turn_is_administration_failure():
    resp = _anthropic_response(
        content=[
            _anthropic_block(
                {"type": "thinking", "thinking": "", "signature": "sig"}
            )
        ],
        stop_reason="end_turn",
    )

    with pytest.raises(AdministrationFailure):
        AnthropicMessagesAdapter(FakeAnthropicClient(resp)).generate(
            model="claude-opus-5",
            messages=[{"role": "user", "content": "x"}],
            parameters={
                "max_tokens": 128000,
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": "max"},
            },
        )


class FakeGeminiInteractions:
    def __init__(self, response=None, exc=None):
        self.response=response; self.exc=exc; self.calls=[]
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc: raise self.exc
        return self.response

class FakeGeminiClient:
    def __init__(self, response=None, exc=None):
        self.interactions=FakeGeminiInteractions(response, exc)


def test_gemini_stateless_success_preserves_steps_and_usage():
    from runner.adapters import GeminiInteractionsAdapter
    thought={"type":"thought","signature":"signed-fixture"}
    output={"type":"model_output","content":[{"type":"text","text":"fixture answer"}]}
    steps=[SimpleNamespace(model_dump=lambda d=d: d) for d in (thought, output)]
    resp=SimpleNamespace(
        id="", model="gemini-3.1-pro-preview", status="completed",
        output_text="fixture answer", service_tier="standard", error=None,
        usage={"total_input_tokens":10,"total_output_tokens":3,"total_thought_tokens":7},
        steps=steps,
        model_dump=lambda: {"status":"completed","model":"gemini-3.1-pro-preview","steps":[thought,output]},
    )
    client=FakeGeminiClient(resp)
    result=GeminiInteractionsAdapter(client).generate(
        model="gemini-3.1-pro-preview",
        messages=[{"role":"user","content":"hello"}],
        parameters={"generation_config":{"thinking_level":"high","max_output_tokens":65536}},
    )
    call=client.interactions.calls[0]
    assert call["store"] is False
    assert call["input"] == [{"type":"user_input","content":[{"type":"text","text":"hello"}]}]
    assert result.substantive_output == "fixture answer"
    assert result.provider_metadata["assistant_message_content"] == [thought, output]
    assert result.provider_metadata["usage"]["total_thought_tokens"] == 7


def test_gemini_multiturn_resends_exact_native_steps():
    from runner.adapters import GeminiInteractionsAdapter
    native=[
        {"type":"thought","signature":"signed-fixture"},
        {"type":"model_output","content":[{"type":"text","text":"first"}]},
    ]
    out={"type":"model_output","content":[{"type":"text","text":"second"}]}
    resp=SimpleNamespace(
        id="", model="m", status="completed", output_text="second",
        service_tier="standard", error=None, usage=None,
        steps=[SimpleNamespace(model_dump=lambda: out)],
        model_dump=lambda: {"status":"completed","steps":[out]},
    )
    client=FakeGeminiClient(resp)
    GeminiInteractionsAdapter(client).generate(
        model="m",
        messages=[
            {"role":"user","content":"u1"},
            {"role":"assistant","content":native},
            {"role":"user","content":"u2"},
        ],
        parameters={},
    )
    assert client.interactions.calls[0]["input"] == [
        {"type":"user_input","content":[{"type":"text","text":"u1"}]},
        *native,
        {"type":"user_input","content":[{"type":"text","text":"u2"}]},
    ]


def test_gemini_rejects_server_state_tools_and_plaintext_assistant_history():
    from runner.adapters import GeminiInteractionsAdapter
    adapter=GeminiInteractionsAdapter(FakeGeminiClient())
    with pytest.raises(AdministrationFailure):
        adapter.generate(model="m", messages=[{"role":"user","content":"x"}], parameters={"store":True})
    with pytest.raises(AdministrationFailure):
        adapter.generate(model="m", messages=[{"role":"user","content":"x"}], parameters={"tools":[]})
    with pytest.raises(AdministrationFailure):
        adapter.generate(
            model="m",
            messages=[{"role":"user","content":"x"},{"role":"assistant","content":"plain"}],
            parameters={},
        )


def test_gemini_retryable_vs_nonretryable_errors():
    from runner.adapters import GeminiInteractionsAdapter
    with pytest.raises(TechnicalFailure):
        GeminiInteractionsAdapter(FakeGeminiClient(exc=exc_type("ServerError",503))).generate(
            model="m", messages=[{"role":"user","content":"x"}], parameters={}
        )
    with pytest.raises(AdministrationFailure):
        GeminiInteractionsAdapter(FakeGeminiClient(exc=exc_type("ClientError",400))).generate(
            model="m", messages=[{"role":"user","content":"x"}], parameters={}
        )


def test_gemini_sue_freeze_contract_passes_exact_sue_configuration():
    from runner.adapters import GeminiInteractionsAdapter

    thought = {"type": "thought", "signature": "signed-freeze-fixture"}
    output = {
        "type": "model_output",
        "content": [{"type": "text", "text": "fixture answer"}],
    }
    steps = [
        SimpleNamespace(model_dump=lambda d=d: d)
        for d in (thought, output)
    ]
    resp = SimpleNamespace(
        id="interaction_fixture",
        model="gemini-3.1-pro-preview",
        status="completed",
        output_text="fixture answer",
        service_tier="standard",
        error=None,
        usage={
            "total_input_tokens": 10,
            "total_output_tokens": 3,
            "total_thought_tokens": 7,
        },
        steps=steps,
        model_dump=lambda: {
            "id": "interaction_fixture",
            "model": "gemini-3.1-pro-preview",
            "status": "completed",
            "steps": [thought, output],
        },
    )
    client = FakeGeminiClient(resp)

    result = GeminiInteractionsAdapter(client).generate(
        model="gemini-3.1-pro-preview",
        messages=[{"role": "user", "content": "synthetic fixture"}],
        parameters={
            "generation_config": {
                "thinking_level": "high",
                "max_output_tokens": 65536,
            }
        },
    )

    call = client.interactions.calls[0]
    assert call["model"] == "gemini-3.1-pro-preview"
    assert call["store"] is False
    assert call["generation_config"] == {
        "thinking_level": "high",
        "max_output_tokens": 65536,
    }
    assert "previous_interaction_id" not in call
    assert "tools" not in call
    assert "tool_config" not in call
    assert "agent" not in call
    assert "environment" not in call
    assert "temperature" not in call
    assert "top_p" not in call
    assert "top_k" not in call
    assert result.provider_metadata["assistant_message_content"] == [
        thought,
        output,
    ]


def test_gemini_freeze_contract_replays_signed_native_steps_unchanged():
    from runner.adapters import GeminiInteractionsAdapter

    native = [
        {
            "type": "thought",
            "signature": "signed-native-fixture",
        },
        {
            "type": "model_output",
            "content": [{"type": "text", "text": "TURN1_OK"}],
        },
    ]
    second_output = {
        "type": "model_output",
        "content": [{"type": "text", "text": "ORCHID"}],
    }
    resp = SimpleNamespace(
        id="interaction_second",
        model="gemini-3.1-pro-preview",
        status="completed",
        output_text="ORCHID",
        service_tier="standard",
        error=None,
        usage=None,
        steps=[SimpleNamespace(model_dump=lambda: second_output)],
        model_dump=lambda: {
            "id": "interaction_second",
            "model": "gemini-3.1-pro-preview",
            "status": "completed",
            "steps": [second_output],
        },
    )
    client = FakeGeminiClient(resp)

    result = GeminiInteractionsAdapter(client).generate(
        model="gemini-3.1-pro-preview",
        messages=[
            {"role": "user", "content": "Remember ORCHID."},
            {"role": "assistant", "content": native},
            {"role": "user", "content": "What was the word?"},
        ],
        parameters={
            "generation_config": {
                "thinking_level": "high",
                "max_output_tokens": 65536,
            }
        },
    )

    call = client.interactions.calls[0]
    assert call["input"] == [
        {
            "type": "user_input",
            "content": [{"type": "text", "text": "Remember ORCHID."}],
        },
        *native,
        {
            "type": "user_input",
            "content": [{"type": "text", "text": "What was the word?"}],
        },
    ]
    assert call["input"][1] == native[0]
    assert call["input"][1]["signature"] == "signed-native-fixture"
    assert call["input"][2] == native[1]
    assert result.substantive_output == "ORCHID"


class FakeXAIResponses:
    def __init__(self, response=None, exc=None):
        self.response=response; self.exc=exc; self.calls=[]
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc: raise self.exc
        return self.response

class FakeXAIClient:
    def __init__(self, response=None, exc=None):
        self.responses=FakeXAIResponses(response, exc)


def _xai_fixture(text="fixture answer"):
    reasoning={"id":"rs_fixture","type":"reasoning","status":"completed","encrypted_content":"opaque-fixture"}
    message={"id":"msg_fixture","type":"message","role":"assistant","status":"completed","content":[{"type":"output_text","text":text}]}
    items=[SimpleNamespace(model_dump=lambda d=d, **kwargs: d) for d in (reasoning,message)]
    usage=SimpleNamespace(
        num_sources_used=0, num_server_side_tools_used=0,
        model_dump=lambda: {"input_tokens":10,"output_tokens":5,"output_tokens_details":{"reasoning_tokens":3},"num_sources_used":0,"num_server_side_tools_used":0}
    )
    return SimpleNamespace(
        id="resp_fixture", model="grok-4.6", status="completed", output_text=text,
        output=items, usage=usage, error=None, incomplete_details=None,
        model_dump=lambda: {"id":"resp_fixture","model":"grok-4.6","status":"completed","output":[reasoning,message]},
    ), reasoning, message


def test_xai_stateless_success_preserves_encrypted_reasoning_and_usage():
    from runner.adapters import XAIResponsesAdapter
    resp, reasoning, message = _xai_fixture()
    client=FakeXAIClient(resp)
    result=XAIResponsesAdapter(client).generate(
        model="grok-4.6", messages=[{"role":"user","content":"hello"}],
        parameters={"reasoning":{"effort":"xhigh"}},
    )
    call=client.responses.calls[0]
    assert call["store"] is False
    assert call["include"] == ["reasoning.encrypted_content"]
    assert call["reasoning"] == {"effort":"xhigh"}
    assert result.substantive_output == "fixture answer"
    assert result.provider_metadata["assistant_message_content"] == [reasoning,message]
    assert result.provider_metadata["usage"]["output_tokens_details"]["reasoning_tokens"] == 3


def test_xai_multiturn_resends_exact_native_output_items():
    from runner.adapters import XAIResponsesAdapter
    resp, reasoning, message = _xai_fixture("second")
    client=FakeXAIClient(resp)
    native=[reasoning,message]
    XAIResponsesAdapter(client).generate(
        model="grok-4.6",
        messages=[
            {"role":"user","content":"u1"},
            {"role":"assistant","content":native},
            {"role":"user","content":"u2"},
        ],
        parameters={"reasoning":{"effort":"xhigh"}},
    )
    assert client.responses.calls[0]["input"] == [
        {"role":"user","content":"u1"}, *native, {"role":"user","content":"u2"}
    ]


def test_xai_rejects_server_state_tools_plaintext_history_and_missing_encryption():
    from runner.adapters import XAIResponsesAdapter
    adapter=XAIResponsesAdapter(FakeXAIClient())
    with pytest.raises(AdministrationFailure):
        adapter.generate(model="m", messages=[{"role":"user","content":"x"}], parameters={"store":True})
    with pytest.raises(AdministrationFailure):
        adapter.generate(model="m", messages=[{"role":"user","content":"x"}], parameters={"previous_response_id":"r"})
    with pytest.raises(AdministrationFailure):
        adapter.generate(model="m", messages=[{"role":"user","content":"x"}], parameters={"tools":[]})
    with pytest.raises(AdministrationFailure):
        adapter.generate(model="m", messages=[{"role":"user","content":"x"},{"role":"assistant","content":"plain"}], parameters={})

    # A substantive-looking response without encrypted reasoning is an
    # administration/contract failure, not a benchmark outcome.
    message={"id":"msg","type":"message","role":"assistant","content":[{"type":"output_text","text":"answer"}]}
    resp=SimpleNamespace(
        id="r", model="grok-4.6", status="completed", output_text="answer",
        output=[SimpleNamespace(model_dump=lambda **kwargs: message)], usage=None,
        error=None, incomplete_details=None, model_dump=lambda: {"output":[message]},
    )
    with pytest.raises(AdministrationFailure):
        XAIResponsesAdapter(FakeXAIClient(resp)).generate(
            model="grok-4.6", messages=[{"role":"user","content":"x"}], parameters={}
        )


def test_xai_retryable_vs_nonretryable_errors():
    from runner.adapters import XAIResponsesAdapter
    with pytest.raises(TechnicalFailure):
        XAIResponsesAdapter(FakeXAIClient(exc=exc_type("RateLimitError",429))).generate(
            model="m", messages=[{"role":"user","content":"x"}], parameters={}
        )
    with pytest.raises(AdministrationFailure):
        XAIResponsesAdapter(FakeXAIClient(exc=exc_type("BadRequestError",400))).generate(
            model="m", messages=[{"role":"user","content":"x"}], parameters={}
        )


def test_xai_provider_native_output_omits_none_fields_for_stateless_replay():
    """Regression: xAI rejects continuation items if SDK None fields are replayed."""
    from runner.adapters import XAIResponsesAdapter

    class NativeItem:
        def __init__(self, payload):
            self.payload = payload
            self.calls = []

        def model_dump(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("exclude_none"):
                return {k: v for k, v in self.payload.items() if v is not None}
            return dict(self.payload)

    reasoning_item = NativeItem({
        "id": "rs_fixture",
        "type": "reasoning",
        "status": "completed",
        "summary": [],
        "content": None,
        "encrypted_content": "opaque-fixture",
    })
    message_item = NativeItem({
        "id": "msg_fixture",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "phase": None,
        "content": [{"type": "output_text", "text": "fixture answer"}],
    })

    usage = SimpleNamespace(
        num_sources_used=0,
        num_server_side_tools_used=0,
        model_dump=lambda: {
            "input_tokens": 10,
            "output_tokens": 5,
            "num_sources_used": 0,
            "num_server_side_tools_used": 0,
        },
    )
    resp = SimpleNamespace(
        id="resp_fixture",
        model="grok-4.6",
        status="completed",
        output_text="fixture answer",
        output=[reasoning_item, message_item],
        usage=usage,
        error=None,
        incomplete_details=None,
        model_dump=lambda: {"id": "resp_fixture", "status": "completed"},
    )

    result = XAIResponsesAdapter(FakeXAIClient(resp)).generate(
        model="grok-4.6",
        messages=[{"role": "user", "content": "synthetic"}],
        parameters={"reasoning": {"effort": "xhigh"}},
    )

    native = result.provider_metadata["assistant_message_content"]

    assert reasoning_item.calls == [{"exclude_none": True}]
    assert message_item.calls == [{"exclude_none": True}]
    assert "content" not in native[0]
    assert "phase" not in native[1]
    assert native[0]["encrypted_content"] == "opaque-fixture"


def test_openai_preserves_native_output_for_stateless_replay_and_omits_none_fields():
    calls = []

    class NativeItem:
        def __init__(self, payload):
            self.payload = payload
            self.type = payload["type"]

        def model_dump(self, **kwargs):
            calls.append(kwargs)
            if kwargs.get("exclude_none"):
                return {k: v for k, v in self.payload.items() if v is not None}
            return dict(self.payload)

    reasoning = {
        "type": "reasoning",
        "id": "rs_fixture",
        "content": [],
        "encrypted_content": "opaque-encrypted-fixture",
        "status": None,
        "summary": [],
    }
    message = {
        "type": "message",
        "id": "msg_fixture",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "TURN1_OK", "annotations": []}],
        "phase": "final_answer",
    }

    resp = SimpleNamespace(
        id="resp_fixture",
        model="gpt-5.6-sol",
        status="completed",
        output_text="TURN1_OK",
        output=[NativeItem(reasoning), NativeItem(message)],
        incomplete_details=None,
        error=None,
        usage={"output_tokens_details": {"reasoning_tokens": 10}},
        model_dump=lambda: {"id": "resp_fixture", "status": "completed"},
    )

    client = FakeOpenAIClient(resp)
    result = OpenAIResponsesAdapter(client).generate(
        model="gpt-5.6-sol",
        messages=[{"role": "user", "content": "synthetic turn one"}],
        parameters={"reasoning": {"effort": "max"}, "max_output_tokens": 128000},
    )

    native = result.provider_metadata["assistant_message_content"]

    assert calls == [{"exclude_none": True}, {"exclude_none": True}]
    assert native[0]["type"] == "reasoning"
    assert native[0]["encrypted_content"] == "opaque-encrypted-fixture"
    assert "status" not in native[0]
    assert native[1] == message

    call = client.responses.calls[0]
    assert call["store"] is False
    assert call["include"] == ["reasoning.encrypted_content"]


def test_openai_message_only_output_is_valid_when_no_reasoning_item_is_returned():
    message = {
        "type": "message",
        "id": "msg_fixture",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "ORCHID", "annotations": []}],
        "phase": "final_answer",
    }

    item = SimpleNamespace(
        type="message",
        model_dump=lambda **kwargs: dict(message),
    )

    resp = SimpleNamespace(
        id="resp_fixture_2",
        model="gpt-5.6-sol",
        status="completed",
        output_text="ORCHID",
        output=[item],
        incomplete_details=None,
        error=None,
        usage={"output_tokens_details": {"reasoning_tokens": 0}},
        model_dump=lambda: {"id": "resp_fixture_2", "status": "completed"},
    )

    result = OpenAIResponsesAdapter(FakeOpenAIClient(resp)).generate(
        model="gpt-5.6-sol",
        messages=[{"role": "user", "content": "synthetic turn two"}],
        parameters={"reasoning": {"effort": "max"}, "max_output_tokens": 128000},
    )

    assert result.substantive_output == "ORCHID"
    assert result.provider_metadata["assistant_message_content"] == [message]


def test_openai_multiturn_resends_exact_provider_native_output_items():
    native = [
        {
            "type": "reasoning",
            "id": "rs_fixture",
            "content": [],
            "encrypted_content": "opaque-encrypted-fixture",
            "summary": [],
        },
        {
            "type": "message",
            "id": "msg_fixture",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "TURN1_OK", "annotations": []}],
            "phase": "final_answer",
        },
    ]

    second_message = {
        "type": "message",
        "id": "msg_fixture_2",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "ORCHID", "annotations": []}],
        "phase": "final_answer",
    }

    resp = SimpleNamespace(
        id="resp_fixture_2",
        model="gpt-5.6-sol",
        status="completed",
        output_text="ORCHID",
        output=[
            SimpleNamespace(
                type="message",
                model_dump=lambda **kwargs: dict(second_message),
            )
        ],
        incomplete_details=None,
        error=None,
        usage={"output_tokens_details": {"reasoning_tokens": 0}},
        model_dump=lambda: {"id": "resp_fixture_2", "status": "completed"},
    )

    client = FakeOpenAIClient(resp)

    OpenAIResponsesAdapter(client).generate(
        model="gpt-5.6-sol",
        messages=[
            {"role": "user", "content": "synthetic turn one"},
            {"role": "assistant", "content": native},
            {"role": "user", "content": "synthetic turn two"},
        ],
        parameters={"reasoning": {"effort": "max"}, "max_output_tokens": 128000},
    )

    assert client.responses.calls[0]["input"] == [
        {"role": "user", "content": "synthetic turn one"},
        *native,
        {"role": "user", "content": "synthetic turn two"},
    ]


def test_openai_rejects_server_state_tools_and_missing_encrypted_reasoning():
    adapter = OpenAIResponsesAdapter(FakeOpenAIClient())

    with pytest.raises(AdministrationFailure):
        adapter.generate(
            model="gpt-5.6-sol",
            messages=[{"role": "user", "content": "x"}],
            parameters={"store": True},
        )

    with pytest.raises(AdministrationFailure):
        adapter.generate(
            model="gpt-5.6-sol",
            messages=[{"role": "user", "content": "x"}],
            parameters={"previous_response_id": "resp_forbidden"},
        )

    with pytest.raises(AdministrationFailure):
        adapter.generate(
            model="gpt-5.6-sol",
            messages=[{"role": "user", "content": "x"}],
            parameters={"tools": [{"type": "web_search"}]},
        )

    reasoning_without_encryption = SimpleNamespace(
        type="reasoning",
        model_dump=lambda **kwargs: {
            "type": "reasoning",
            "id": "rs_bad",
            "content": [],
            "summary": [],
        },
    )
    message = SimpleNamespace(
        type="message",
        model_dump=lambda **kwargs: {
            "type": "message",
            "id": "msg_bad",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "answer", "annotations": []}],
        },
    )
    resp = SimpleNamespace(
        id="resp_bad",
        model="gpt-5.6-sol",
        status="completed",
        output_text="answer",
        output=[reasoning_without_encryption, message],
        incomplete_details=None,
        error=None,
        usage=None,
        model_dump=lambda: {"id": "resp_bad", "status": "completed"},
    )

    with pytest.raises(AdministrationFailure):
        OpenAIResponsesAdapter(FakeOpenAIClient(resp)).generate(
            model="gpt-5.6-sol",
            messages=[{"role": "user", "content": "x"}],
            parameters={},
        )
