"""Offline model-boundary regressions: no endpoint, model or private source."""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from novel_ai.output_policy import (
    OutputPolicy,
    OutputValidationError,
    completion_text,
    json_object_from_value,
    parse_json_object,
    strict_json_object,
    validate_output_text,
)
from novel_ai.provider import LiteLLMConfig, LiteLLMProvider, OpenAICompatibleProvider, ProviderConfig
from novel_ai.structured_output import (
    FallbackStructuredExtractor,
    GuidanceStructuredExtractor,
    InstructorStructuredExtractor,
    OutlinesStructuredExtractor,
    UnsupportedOutputBound,
)


MESSAGES = [{"role": "user", "content": "synthetic test"}]
FORMAT = {"type": "json_object"}


def response(content="complete", finish_reason="stop", **message_extra):
    return {"choices": [{"message": {"content": content, **message_extra}, "finish_reason": finish_reason}]}


def provider_with_transport(monkeypatch, handler, **config):
    original = httpx.Client

    def client(**kwargs):
        return original(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", client)
    return OpenAICompatibleProvider(ProviderConfig("https://example.invalid/v1", "test", **config))


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "100", None])
def test_output_policy_rejects_invalid_stage_and_byte_caps(value):
    for field in ("plan_tokens", "draft_tokens", "review_tokens", "repair_tokens", "style_tokens", "memory_tokens", "max_output_bytes"):
        with pytest.raises(ValueError, match="positive integer"):
            OutputPolicy(**{field: value})


def test_stage_caps_are_explicit_and_not_mutable():
    policy = OutputPolicy(plan_tokens=11, draft_tokens=12, review_tokens=13,
                          repair_tokens=14, style_tokens=15, memory_tokens=16)
    assert [policy.tokens_for(stage) for stage in ("plan", "draft", "review", "repair", "style", "memory")] == list(range(11, 17))
    with pytest.raises(ValueError):
        policy.tokens_for("unknown")
    with pytest.raises(AttributeError):
        policy.plan_tokens = 0


@pytest.mark.parametrize("text, expected", [
    ('{"a":{"b":[1,{"c":"escaped \\\" } { \\\""}]}}', {"a": {"b": [1, {"c": 'escaped " } { "'}]}}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('```\n{"a": 1}\n```', {"a": 1}),
    ('```JSON\r\n{"a": 1}\r\n```', {"a": 1}),
    ('前缀 {"a": {"b": 2}} 后缀', {"a": {"b": 2}}),
    ('Here is the JSON: {"a": "literal } and { braces"}', {"a": "literal } and { braces"}),
    (' {"a": "line\\ntext", "b": "\\u4e2d"} ', {"a": "line\ntext", "b": "中"}),
])
def test_complete_unambiguous_json_preserves_structure(text, expected):
    assert parse_json_object(text) == expected


@pytest.mark.parametrize("text", [
    '[{"a":1}]', 'prefix [{"a":1}] suffix', '[]', '"scalar"', 'null', 'true', '1',
    'true {"a":1}', '1 {"a":1}', '"quoted { not an object }"',
    '{"a":1}{"b":2}', 'prefix {"a":1} between {"b":2}',
    '{"a":1},', '{"a":1} []', '{"a":1} null', '{"a":1}; null',
    '{"a":1} trailing {', 'prefix } {"a":1}', '{"a":', '{"a": {"b":2}',
    '{"a":1,}', '{"a": "unterminated}', '```json\n{"a":1}',
    '```json\n{"a":1}\n``` trailing', '```json\n{"a":1}\n```\n```json\n{}\n```',
    '{"a":1,"a":2}', '{"a":{"x":1,"x":2}}', '{"a":1,"\\u0061":2}',
    '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":1e999}',
    '{"a":"\\ud800"}', '', ' \t\n', 'JSON: {"a":1} "extra string"',
])
def test_ambiguous_malformed_truncated_and_nonfinite_json_is_refused(text):
    with pytest.raises(OutputValidationError):
        parse_json_object(text)


def test_strict_envelope_parser_does_not_allow_prose_or_fences():
    for text in ('prefix {"a":1}', '```json\n{"a":1}\n```'):
        with pytest.raises(OutputValidationError):
            strict_json_object(text)


@pytest.mark.parametrize("value", [None, [], {}, 1, True, "", " \t\n", "\ud800"])
def test_text_validation_refuses_nontext_blank_and_invalid_unicode(value):
    with pytest.raises(OutputValidationError):
        validate_output_text(value)


def test_output_byte_caps_use_utf8_and_do_not_silently_clip():
    assert validate_output_text(" 中 ", max_bytes=5) == " 中 "
    with pytest.raises(OutputValidationError, match="byte allowance"):
        validate_output_text(" 中 ", max_bytes=4)
    with pytest.raises(OutputValidationError, match="byte allowance"):
        parse_json_object('{"x":"中"}', max_bytes=9)


@pytest.mark.parametrize("body", [
    {}, {"choices": []}, {"choices": [{"message": {"content": "synthetic private story"}}]},
    {"choices": [None]}, response(None), response([]), response(""), response(" \n"),
    response("partial", "length"), response("filtered", "content_filter"),
    response("unknown", "new_reason"), response("unknown", None),
    response("refused", refusal="synthetic refusal"),
    response("unsafe", tool_calls=[{}]),
    {"choices": [response()["choices"][0], response()["choices"][0]]},
])
def test_both_chat_providers_refuse_unconfirmed_or_invalid_completions(monkeypatch, body):
    provider = provider_with_transport(monkeypatch, lambda req: httpx.Response(200, json=body))
    lite = LiteLLMProvider(LiteLLMConfig(("model",)), completion_func=lambda **kw: body)
    for adapter in (provider, lite):
        with pytest.raises(OutputValidationError) as error:
            adapter.chat(MESSAGES)
        assert "synthetic private story" not in str(error.value)
        assert "synthetic refusal" not in str(error.value)


def test_litellm_attribute_response_and_explicit_cap():
    calls = []
    body = SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="完成", refusal=None))])
    lite = LiteLLMProvider(LiteLLMConfig(("model",)), completion_func=lambda **kw: calls.append(kw) or body)
    assert lite.chat(MESSAGES, max_tokens=34) == "完成"
    assert calls[0]["max_tokens"] == 34
    assert calls[0]["num_retries"] == 0


@pytest.mark.parametrize("max_tokens", [0, -1, False, True, 1.5, "12"])
def test_invalid_token_caps_fail_before_any_provider_call(monkeypatch, max_tokens):
    calls = []
    provider = provider_with_transport(monkeypatch, lambda req: calls.append(req) or httpx.Response(200, json=response()))
    lite = LiteLLMProvider(LiteLLMConfig(("model",)), completion_func=lambda **kw: calls.append(kw) or response())
    for adapter in (provider, lite):
        with pytest.raises(ValueError, match="positive integer"):
            adapter.chat(MESSAGES, max_tokens=max_tokens)
    assert calls == []


def test_provider_default_caps_are_never_omitted(monkeypatch):
    calls = []
    provider = provider_with_transport(monkeypatch, lambda req: calls.append(json.loads(req.content)) or httpx.Response(200, json=response()), default_max_tokens=123)
    assert provider.chat(MESSAGES) == "complete"
    lite = LiteLLMProvider(LiteLLMConfig(("model",), default_max_tokens=456), completion_func=lambda **kw: calls.append(kw) or response())
    assert lite.chat(MESSAGES) == "complete"
    assert [call["max_tokens"] for call in calls] == [123, 456]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 429, 500, 503])
def test_unrelated_http_errors_are_not_retried(monkeypatch, status):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={"error": {"message": "synthetic private failure", "param": "model"}})
    provider = provider_with_transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError) as error:
        provider.chat(MESSAGES, response_format=FORMAT)
    assert error.value.response.status_code == status
    assert "synthetic private failure" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("error", [
    {"param": "response_format", "code": "invalid_json_schema", "message": "invalid schema"},
    {"param": "model", "code": "unsupported_parameter", "message": "response_format unsupported"},
    {"message": "Unknown parameter foo with response_format enabled"},
    {"message": "invalid request: response_format"},
    {"message": "Invalid JSON schema for response_format"},
])
def test_format_mention_without_specific_unsupported_evidence_does_not_retry(monkeypatch, error):
    calls = []
    provider = provider_with_transport(monkeypatch, lambda req: calls.append(req) or httpx.Response(400, json={"error": error}))
    with pytest.raises(httpx.HTTPStatusError):
        provider.chat(MESSAGES, response_format=FORMAT)
    assert len(calls) == 1


@pytest.mark.parametrize("error", [
    {"param": "response_format", "code": "unsupported_parameter"},
    {"message": "Unsupported parameter: 'response_format'"},
    {"message": "response_format is not supported for this model"},
    {"message": "This model does not support response_format"},
])
def test_explicit_unsupported_format_retries_once_and_preserves_cap(monkeypatch, error):
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        assert req.headers["accept-encoding"] == "identity"
        return httpx.Response(400, json={"error": error}) if len(calls) == 1 else httpx.Response(200, json=response())
    provider = provider_with_transport(monkeypatch, handler)
    assert provider.chat(MESSAGES, max_tokens=73, temperature=0.3, response_format=FORMAT) == "complete"
    assert len(calls) == 2
    assert calls[0] == {**calls[1], "response_format": FORMAT}
    assert calls[1]["max_tokens"] == 73
    assert calls[1]["temperature"] == 0.3


def test_format_fallback_failure_does_not_retry_again(monkeypatch):
    calls = []
    provider = provider_with_transport(monkeypatch, lambda req: calls.append(req) or httpx.Response(400, json={"error": {"param": "response_format", "code": "unsupported_parameter"}}))
    with pytest.raises(httpx.HTTPStatusError):
        provider.chat(MESSAGES, response_format=FORMAT)
    assert len(calls) == 2


def test_transport_failure_has_no_retry_or_format_downgrade(monkeypatch):
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("synthetic timeout")
    provider = provider_with_transport(monkeypatch, handler)
    with pytest.raises(httpx.ReadTimeout):
        provider.chat(MESSAGES, response_format=FORMAT)
    assert len(calls) == 1


def test_declared_oversized_response_is_rejected_without_stream_read(monkeypatch):
    class NeverRead(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail("oversized response must not be read")
            yield b""
    provider = provider_with_transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-length": "1001"}, stream=NeverRead()), max_response_bytes=1000)
    with pytest.raises(OutputValidationError, match="byte allowance"):
        provider.chat(MESSAGES)


def test_chunked_response_is_stopped_and_closed_at_byte_limit(monkeypatch):
    seen = []
    class Chunks(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(10):
                seen.append(index)
                yield b"x" * 10
        def close(self):
            seen.append("closed")
    provider = provider_with_transport(monkeypatch, lambda req: httpx.Response(200, stream=Chunks()), max_response_bytes=25)
    with pytest.raises(OutputValidationError, match="byte allowance"):
        provider.chat(MESSAGES)
    assert seen == [0, 1, 2, "closed"]


def test_compressed_response_is_refused_before_inflation(monkeypatch):
    class NeverRead(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail("compressed response must not be read")
            yield b""
    provider = provider_with_transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-encoding": "gzip"}, stream=NeverRead()))
    with pytest.raises(OutputValidationError, match="compressed"):
        provider.chat(MESSAGES)


def test_success_content_must_fit_application_byte_cap(monkeypatch):
    provider = provider_with_transport(monkeypatch, lambda req: httpx.Response(200, json=response("中文")), max_output_bytes=5)
    lite = LiteLLMProvider(LiteLLMConfig(("model",), max_output_bytes=5), completion_func=lambda **kw: response("中文"))
    for adapter in (provider, lite):
        with pytest.raises(OutputValidationError, match="byte allowance"):
            adapter.chat(MESSAGES)


class Item(BaseModel):
    title: str


def fake_instructor(result):
    calls = []
    def create_with_completion(**kwargs):
        calls.append(kwargs)
        return result
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create_with_completion=create_with_completion)))
    return InstructorStructuredExtractor(client), calls


def extract(extractor, **kwargs):
    return extractor.extract(response_model=Item, messages=MESSAGES, temperature=0.2,
                             max_tokens=321, max_output_bytes=1000, **kwargs)


def test_instructor_requires_raw_evidence_and_forwards_cap_no_retries():
    adapter, calls = fake_instructor((Item(title="ok"), response('{"title":"ok"}')))
    assert extract(adapter) == Item(title="ok")
    assert calls[0]["max_tokens"] == 321
    assert calls[0]["max_retries"] == 0


def test_instructor_supports_one_complete_tool_call():
    body = response(None, "tool_calls", tool_calls=[{"function": {"arguments": '{"title":"ok"}'}}])
    adapter, _ = fake_instructor((Item(title="ok"), body))
    assert extract(adapter).title == "ok"


@pytest.mark.parametrize("body", [
    response('{"title":"ok"}', "length"),
    {"choices": [{"message": {"content": '{"title":"ok"}'}}]},
    response('{"title":"ok", "title":"bad"}'),
    response('{"title":"other"}'),
    response(None, "tool_calls", tool_calls=[{"function": {"arguments": '{"title":"ok"}'}}, {}]),
])
def test_instructor_rejects_unconfirmed_ambiguous_or_mismatched_raw_result(body):
    adapter, _ = fake_instructor((Item(title="ok"), body))
    with pytest.raises(OutputValidationError):
        extract(adapter)


def test_instructor_rejects_legacy_api_without_completion_evidence():
    with pytest.raises(UnsupportedOutputBound):
        InstructorStructuredExtractor(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: Item(title="bad")))))


@pytest.mark.parametrize("parameter", ["max_tokens", "max_new_tokens"])
def test_outlines_cap_keyword_must_be_selected_and_is_forwarded(parameter):
    calls = []
    def model(prompt, output_type, **kwargs):
        calls.append(kwargs)
        return '{"title":"ok"}'
    assert extract(OutlinesStructuredExtractor(model, token_limit_parameter=parameter)).title == "ok"
    assert calls == [{"temperature": 0.2, parameter: 321}]


def test_outlines_unknown_or_unsupported_cap_fails_before_call():
    calls = []
    def model(prompt, schema, temperature):
        calls.append(prompt)
        return '{"title":"ok"}'
    for option in (None, "max_tokens"):
        with pytest.raises(UnsupportedOutputBound):
            extract(OutlinesStructuredExtractor(model, token_limit_parameter=option))
    assert calls == []


def test_outlines_internal_typeerror_never_retries_without_bound():
    calls = []
    def model(*args, **kwargs):
        calls.append(kwargs)
        raise TypeError("synthetic private content")
    with pytest.raises(RuntimeError) as error:
        extract(OutlinesStructuredExtractor(model, token_limit_parameter="max_tokens"))
    assert "synthetic private content" not in str(error.value)
    assert len(calls) == 1


def guidance_adapter(output, calls):
    class Model:
        def __iadd__(self, other):
            return self
        def __getitem__(self, key):
            return output
    def factory(**kwargs):
        calls.append(kwargs)
        return "synthetic grammar"
    return GuidanceStructuredExtractor(Model(), json_factory=factory)


def test_guidance_cap_is_forwarded_and_capture_is_validated():
    calls = []
    assert extract(guidance_adapter('{"title":"ok"}', calls)).title == "ok"
    assert calls[0]["max_tokens"] == 321


@pytest.mark.parametrize("value", ['{"title":"ok","title":"bad"}', '{"title":"unfinished', '{"title":NaN}', '{"title":1e999}', [], Item.model_construct(title=None)])
def test_every_structured_adapter_revalidates_and_never_repairs_output(value):
    adapters = [
        OutlinesStructuredExtractor(lambda *a, **kw: value, token_limit_parameter="max_tokens"),
        guidance_adapter(value, []),
    ]
    for adapter in adapters:
        with pytest.raises(OutputValidationError):
            extract(adapter)


def test_fallback_chain_preserves_allowances_and_revalidates_models():
    calls = []
    class Candidate:
        def __init__(self, value):
            self.value = value
        def extract(self, **kwargs):
            calls.append(kwargs)
            return self.value
    chain = FallbackStructuredExtractor([Candidate(Item.model_construct(title=None)), Candidate(Item(title="ok"))])
    assert extract(chain).title == "ok"
    assert len(calls) == 2
    assert all(call["max_tokens"] == 321 and call["max_output_bytes"] == 1000 for call in calls)


def test_fallback_does_not_call_backend_with_no_bound_parameters():
    calls = []
    class Legacy:
        def extract(self, *, response_model, messages, temperature):
            calls.append(messages)
            return Item(title="bad")
    with pytest.raises(RuntimeError, match="UnsupportedOutputBound"):
        extract(FallbackStructuredExtractor([Legacy()]))
    assert calls == []


def test_native_structured_values_refuse_nonfinite_and_invalid_unicode():
    for value in ({"title": float("inf")}, {"title": "\ud800"}):
        with pytest.raises(OutputValidationError):
            json_object_from_value(value)


@pytest.mark.parametrize("code", [[], {}, None, 42])
def test_malformed_error_code_preserves_original_http_failure(monkeypatch, code):
    calls = []
    provider = provider_with_transport(monkeypatch, lambda req: calls.append(req) or httpx.Response(400, json={"error": {"param": "response_format", "code": code}}))
    with pytest.raises(httpx.HTTPStatusError):
        provider.chat(MESSAGES, response_format=FORMAT)
    assert len(calls) == 1


@pytest.mark.parametrize("used", [True, -1, 1001, 2.5, "20"])
def test_reported_usage_cannot_contradict_token_allowance(monkeypatch, used):
    body = {**response(), "usage": {"completion_tokens": used}}
    provider = provider_with_transport(monkeypatch, lambda req: httpx.Response(200, json=body))
    lite = LiteLLMProvider(LiteLLMConfig(("model",)), completion_func=lambda **kw: body)
    for adapter in (provider, lite):
        with pytest.raises(OutputValidationError, match="token allowance"):
            adapter.chat(MESSAGES, max_tokens=1000)


@pytest.mark.parametrize("body", [b'not json', b'null', b'{"choices":[],"choices":[]}', b'{"choices":', b'\xff'])
def test_malformed_http_json_never_retries_or_exposes_response(monkeypatch, body):
    calls = []
    provider = provider_with_transport(monkeypatch, lambda req: calls.append(req) or httpx.Response(200, content=body))
    with pytest.raises(OutputValidationError):
        provider.chat(MESSAGES, response_format=FORMAT)
    assert len(calls) == 1


def test_guidance_no_bound_api_fails_before_prompt_or_generation():
    calls = []
    class Model:
        def __iadd__(self, value):
            calls.append(value)
            return self
    def factory(*, name, schema, temperature):
        calls.append(name)
    with pytest.raises(UnsupportedOutputBound):
        extract(GuidanceStructuredExtractor(Model(), json_factory=factory))
    assert calls == []


@pytest.mark.parametrize("bad", [False, 0, -1, 1.5])
def test_all_structured_adapters_reject_invalid_caps_without_running(bad):
    calls = []
    adapter, instructor_calls = fake_instructor((Item(title="ok"), response('{"title":"ok"}')))
    adapters = [adapter,
                OutlinesStructuredExtractor(lambda *a, **kw: calls.append(kw), token_limit_parameter="max_tokens"),
                guidance_adapter('{"title":"ok"}', calls)]
    for adapter in adapters:
        with pytest.raises(ValueError, match="positive integer"):
            adapter.extract(response_model=Item, messages=MESSAGES, temperature=0.2, max_tokens=bad)
    assert instructor_calls == calls == []


def test_structured_adapters_enforce_capture_bytes_without_truncating():
    raw = '{"title":"中文"}'
    instructor, _ = fake_instructor((Item(title="中文"), response(raw)))
    adapters = [instructor,
                OutlinesStructuredExtractor(lambda *a, **kw: raw, token_limit_parameter="max_tokens"),
                guidance_adapter(raw, [])]
    for adapter in adapters:
        with pytest.raises(OutputValidationError, match="byte allowance"):
            adapter.extract(response_model=Item, messages=MESSAGES, temperature=0.2, max_tokens=100, max_output_bytes=10)


def test_litellm_errors_hide_private_response_and_api_key():
    calls = []
    def completion(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("synthetic private story with key synthetic-secret")
    provider = LiteLLMProvider(LiteLLMConfig(("model",), api_key="synthetic-secret"), completion_func=completion)
    with pytest.raises(RuntimeError) as error:
        provider.chat(MESSAGES, response_format=FORMAT)
    assert "synthetic-secret" not in str(error.value)
    assert "synthetic private story" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_are_not_followed_or_treated_as_success(monkeypatch, status):
    calls = []
    provider = provider_with_transport(monkeypatch, lambda req: calls.append(req) or httpx.Response(status, json=response(), headers={"location": "https://other.invalid/v1"}))
    with pytest.raises(httpx.HTTPStatusError):
        provider.chat(MESSAGES, response_format=FORMAT)
    assert len(calls) == 1


@pytest.mark.parametrize("factory, field", [
    (lambda **kw: ProviderConfig("https://example.invalid/v1", "model", **kw), "default_max_tokens"),
    (lambda **kw: ProviderConfig("https://example.invalid/v1", "model", **kw), "max_response_bytes"),
    (lambda **kw: ProviderConfig("https://example.invalid/v1", "model", **kw), "max_output_bytes"),
    (lambda **kw: LiteLLMConfig(("model",), **kw), "default_max_tokens"),
    (lambda **kw: LiteLLMConfig(("model",), **kw), "max_output_bytes"),
])
def test_provider_configuration_rejects_invalid_allowances(factory, field):
    for value in (True, False, 0, -1, 1.5, "100", None):
        with pytest.raises(ValueError, match="positive integer"):
            factory(**{field: value})


def test_untrusted_oversized_content_length_is_refused_without_integer_overflow(monkeypatch):
    provider = provider_with_transport(monkeypatch, lambda req: httpx.Response(200, content=b"", headers={"content-length": "9" * 5000}))
    with pytest.raises(OutputValidationError, match="byte allowance"):
        provider.chat(MESSAGES)
