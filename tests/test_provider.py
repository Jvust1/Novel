from novel_ai.provider import (
    LiteLLMConfig,
    LiteLLMProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    is_loopback_url,
    sglang_provider_config,
)


def test_loopback_detection_covers_common_local_forms():
    assert is_loopback_url("http://127.0.0.1:11434/v1")
    assert is_loopback_url("http://localhost:8000")
    assert is_loopback_url("http://[::1]:9000/v1")
    assert not is_loopback_url("http://10.0.0.5:11434/v1")
    assert not is_loopback_url("https://api.example.com/v1")
    assert not is_loopback_url("")


def test_provider_bypasses_env_proxy_for_loopback(monkeypatch):
    """A loopback endpoint must never be routed through a proxy.

    Simulates the Windows system-proxy situation: httpx with trust_env=True
    would send loopback traffic to the proxy, which answers 503. The provider
    must disable trust_env for loopback endpoints.
    """
    import httpx

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:59999")
    monkeypatch.setenv("HTTPX_PROXY", "http://127.0.0.1:59999")

    provider = OpenAICompatibleProvider(ProviderConfig(base_url="http://127.0.0.1:59998/v1", model="m"))

    captured: dict[str, bool] = {}

    class ProbeTransport(httpx.HTTPTransport):
        def handle_request(self, request):
            captured["proxied"] = request.url.host not in ("127.0.0.1", "localhost")
            raise httpx.ConnectError("probe-stop")

    original_client = httpx.Client

    def client_spy(*args, **kwargs):
        kwargs["transport"] = ProbeTransport()
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_spy)
    try:
        provider.chat([{"role": "user", "content": "hi"}])
    except httpx.ConnectError:
        pass
    assert captured == {"proxied": False}


def test_provider_keeps_env_proxy_for_remote(monkeypatch):
    import httpx

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:59999")
    provider = OpenAICompatibleProvider(ProviderConfig(base_url="https://api.example.com/v1", model="m"))

    seen: dict[str, object] = {}
    original_client = httpx.Client

    def client_spy(*args, **kwargs):
        seen["trust_env"] = kwargs.get("trust_env", True)
        raise RuntimeError("stop-before-connect")

    monkeypatch.setattr(httpx, "Client", client_spy)
    try:
        provider.chat([{"role": "user", "content": "hi"}])
    except RuntimeError:
        pass
    assert seen["trust_env"] is not False



def test_litellm_provider_passes_primary_and_fallback_models():
    seen = {}

    def completion(**kwargs):
        seen.update(kwargs)
        return {"choices": [{"message": {"content": "完成"}, "finish_reason": "stop"}]}

    provider = LiteLLMProvider(
        LiteLLMConfig(
            models=("openai/model-a", "anthropic/model-b"),
            api_key="secret",
            api_base="https://gateway.example/v1",
            timeout=30,
        ),
        completion_func=completion,
    )
    text = provider.chat(
        [{"role": "user", "content": "写作"}],
        temperature=0.4,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    assert text == "完成"
    assert seen["model"] == "openai/model-a"
    assert seen["fallbacks"] == ["anthropic/model-b"]
    assert seen["api_key"] == "secret"
    assert seen["api_base"] == "https://gateway.example/v1"
    assert seen["timeout"] == 30


def test_sglang_provider_config_normalizes_openai_v1_endpoint():
    config = sglang_provider_config(
        "http://127.0.0.1:30000",
        "Qwen/test",
        timeout=90,
    )
    assert config.base_url == "http://127.0.0.1:30000/v1"
    assert config.model == "Qwen/test"
    assert config.timeout == 90
