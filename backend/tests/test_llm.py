import json

import httpx
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm.base import (
    Attachment,
    LLMError,
    LLMNotConfigured,
    LLMRequest,
    LLMResponse,
    LLMRetryableError,
    Usage,
)
from app.llm.factory import build_chain
from app.llm.providers import (
    FakeProvider,
    FallbackProvider,
    GeminiProvider,
    OpenAICompatibleProvider,
)
from app.llm.structured import cost_usd, extract_json, generate_structured

REQUEST = LLMRequest(system="Be brief.", prompt="Say hi as JSON.", json_output=True)


def _transport(status: int, body: dict, seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


async def test_gemini_request_and_response_shape():
    seen: list[httpx.Request] = []
    reply = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "thinking...", "thought": True}, {"text": '{"hi": 1}'}]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": 5,
            "thoughtsTokenCount": 20,
        },
    }
    provider = GeminiProvider("secret-key", "gemini-test", transport=_transport(200, reply, seen))

    request = LLMRequest(
        system="sys",
        prompt="Describe this figure.",
        attachments=(Attachment(b"\x89PNG", "image/png"),),
        json_output=True,
    )
    response = await provider.generate(request)

    sent = seen[0]
    assert sent.url.path.endswith("/models/gemini-test:generateContent")
    assert sent.headers["x-goog-api-key"] == "secret-key"
    body = json.loads(sent.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "sys"
    parts = body["contents"][0]["parts"]
    assert parts[0]["text"] == "Describe this figure."
    assert parts[1]["inlineData"]["mimeType"] == "image/png"  # multimodal input
    assert body["generationConfig"]["responseMimeType"] == "application/json"

    assert response.text == '{"hi": 1}'  # the hidden "thought" part is left out
    assert response.usage == Usage(input_tokens=12, output_tokens=25)  # thoughts billed as output
    assert (response.provider, response.model) == ("gemini", "gemini-test")


async def test_openai_compatible_request_and_response_shape():
    seen: list[httpx.Request] = []
    reply = {
        "choices": [{"message": {"content": '{"hi": 1}'}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    }
    provider = OpenAICompatibleProvider(
        "grok", "https://api.x.ai/v1/", "k", "grok-test", transport=_transport(200, reply, seen)
    )

    response = await provider.generate(REQUEST)

    sent = seen[0]
    assert str(sent.url) == "https://api.x.ai/v1/chat/completions"
    assert sent.headers["authorization"] == "Bearer k"
    body = json.loads(sent.content)
    assert body["model"] == "grok-test"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["response_format"] == {"type": "json_object"}
    assert response.usage == Usage(7, 3)


async def test_openai_compatible_rejects_pdf_attachments():
    provider = OpenAICompatibleProvider("groq", "https://x", "k", "m")
    request = LLMRequest(
        system="s", prompt="p", attachments=(Attachment(b"%PDF", "application/pdf"),)
    )
    with pytest.raises(LLMError, match="can't read application/pdf"):
        await provider.generate(request)


@pytest.mark.parametrize(
    ("status", "error"), [(429, LLMRetryableError), (503, LLMRetryableError), (400, LLMError)]
)
async def test_http_errors_map_to_retryable_or_not(status, error):
    provider = GeminiProvider("k", "m", transport=_transport(status, {"error": "nope"}, []))
    with pytest.raises(error) as caught:
        await provider.generate(REQUEST)
    if status == 400:
        assert not isinstance(caught.value, LLMRetryableError)


async def test_network_failure_is_retryable():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    provider = GeminiProvider("k", "m", transport=httpx.MockTransport(handler))
    with pytest.raises(LLMRetryableError, match="unreachable"):
        await provider.generate(REQUEST)


class _Failing:
    def __init__(self, name: str, error: Exception) -> None:
        self.name, self.model, self.error, self.calls = name, f"{name}-model", error, 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        raise self.error


async def test_fallback_moves_on_after_a_rate_limit():
    limited = _Failing("gemini", LLMRetryableError("429"))
    backup = FakeProvider(['{"ok": true}'], name="grok")

    response = await FallbackProvider([limited, backup]).generate(REQUEST)

    assert response.provider == "grok"
    assert limited.calls == 1


async def test_fallback_stops_on_a_configuration_error():
    broken = _Failing("gemini", LLMError("HTTP 400: API key not valid"))
    backup = FakeProvider(['{"ok": true}'], name="grok")

    with pytest.raises(LLMError, match="API key not valid"):
        await FallbackProvider([broken, backup]).generate(REQUEST)
    assert backup.requests == []


async def test_fallback_reports_every_failure_when_all_are_down():
    chain = FallbackProvider(
        [_Failing("gemini", LLMRetryableError("a")), _Failing("grok", LLMRetryableError("b"))]
    )
    with pytest.raises(LLMRetryableError, match="a | b"):
        await chain.generate(REQUEST)


def test_chain_skips_providers_without_keys():
    settings = Settings(gemini_api_key="", grok_api_key="", groq_api_key="g")
    chain = build_chain("gemini,grok,groq", settings)
    assert chain.name == "groq"

    with pytest.raises(LLMNotConfigured):
        build_chain("gemini,grok", settings)


def test_chain_keeps_the_configured_order():
    settings = Settings(gemini_api_key="a", grok_api_key="b", groq_api_key="")
    assert build_chain("grok,gemini", settings).name == "grok+gemini"


@pytest.mark.parametrize(
    "text",
    ['{"a": 1}', '```json\n{"a": 1}\n```', 'Sure! Here it is: {"a": 1} Hope that helps.'],
)
def test_extract_json_tolerates_fences_and_prose(text):
    assert extract_json(text) == {"a": 1}


class _Shape(BaseModel):
    a: int


async def test_structured_output_retries_once_with_the_error():
    fake = FakeProvider(['{"a": "not a number"}', '{"a": 2}'])

    result = await generate_structured(fake, REQUEST, _Shape)

    assert result.value.a == 2
    assert len(result.responses) == 2
    assert "could not be used" in fake.requests[1].prompt
    assert all(r.json_output for r in fake.requests)


async def test_structured_output_gives_up_after_max_attempts():
    with pytest.raises(LLMError, match="No valid JSON"):
        await generate_structured(FakeProvider(["nope", "still nope"]), REQUEST, _Shape)


def test_cost_uses_the_price_table_and_defaults_to_free(monkeypatch):
    response = LLMResponse("x", "grok", "paid-model", Usage(1_000_000, 500_000))
    assert cost_usd(response) == 0.0  # not in the table: free tier

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_prices_per_million", {"paid-model": (0.3, 0.5)})
    assert cost_usd(response) == pytest.approx(0.3 + 0.25)


def test_judge_never_falls_back_to_the_answer_model_when_a_judge_key_exists(monkeypatch):
    from app.config import get_settings
    from app.llm.factory import get_judge_llm

    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "g")
    monkeypatch.setattr(settings, "groq_api_key", "q")
    assert get_judge_llm().name == "groq"  # not "groq+gemini"

    monkeypatch.setattr(settings, "groq_api_key", "")
    assert get_judge_llm().name == "gemini"  # only key left: self-judging, but visible
