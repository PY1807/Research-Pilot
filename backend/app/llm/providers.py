"""Concrete LLM providers. Each one turns an `LLMRequest` into one HTTP call and the reply
back into an `LLMResponse`. Plain `httpx` instead of each company's SDK: the request and
response shapes are visible right here, and one HTTP client serves every provider.

- GeminiProvider: Google's native `generateContent` API (multimodal: images and PDFs).
- OpenAICompatibleProvider: the `/chat/completions` shape that xAI (Grok), Groq and many
  others copy from OpenAI. Only the base URL, key and model differ.
- FallbackProvider: tries providers in order, moving on when one is rate-limited or down.
- FakeProvider: scripted replies for tests. No network, no key.
"""

import base64
import time
from collections.abc import Callable, Sequence

import httpx

from app.llm.base import (
    LLMError,
    LLMNotConfigured,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMRetryableError,
    Usage,
)

# Rate limits and server-side trouble: worth trying another provider or trying later.
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _raise_for_status(provider: str, response: httpx.Response) -> None:
    if response.is_success:
        return
    # Keep the provider's message (it explains bad model names, quota, etc.) but cap its
    # length. Keys travel in headers, so they never appear in these bodies.
    detail = response.text[:300].replace("\n", " ")
    message = f"{provider} returned HTTP {response.status_code}: {detail}"
    if response.status_code in RETRYABLE_STATUS:
        raise LLMRetryableError(message)
    raise LLMError(message)


async def _post(
    provider: str,
    url: str,
    headers: dict,
    body: dict,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None,
) -> tuple[dict, float]:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, transport=transport) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.TransportError as exc:  # timeouts, DNS failures, dropped connections
        raise LLMRetryableError(f"{provider} unreachable: {type(exc).__name__}") from exc
    _raise_for_status(provider, response)
    return response.json(), (time.perf_counter() - started) * 1000


class GeminiProvider:
    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport  # tests pass httpx.MockTransport

    def _body(self, request: LLMRequest) -> dict:
        parts: list[dict] = [{"text": request.prompt}]
        for attachment in request.attachments:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": attachment.mime_type,
                        "data": base64.b64encode(attachment.data).decode(),
                    }
                }
            )
        config: dict = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_output_tokens,
        }
        if request.json_output:
            config["responseMimeType"] = "application/json"
        return {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": config,
        }

    async def generate(self, request: LLMRequest) -> LLMResponse:
        data, latency_ms = await _post(
            self.name,
            f"{self.BASE_URL}/models/{self.model}:generateContent",
            {"x-goog-api-key": self._api_key},
            self._body(request),
            self._timeout,
            self._transport,
        )
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise LLMError(f"gemini returned no answer ({reason})")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        # "Thinking" models may return their reasoning as separate parts marked thought=True.
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text:
            reason = candidates[0].get("finishReason", "empty")
            raise LLMError(f"gemini returned an empty answer ({reason})")
        meta = data.get("usageMetadata") or {}
        usage = Usage(
            input_tokens=meta.get("promptTokenCount", 0),
            # Hidden reasoning tokens are billed as output, so they count here too.
            output_tokens=meta.get("candidatesTokenCount", 0) + meta.get("thoughtsTokenCount", 0),
        )
        return LLMResponse(text, self.name, self.model, usage, round(latency_ms, 1))


class OpenAICompatibleProvider:
    """Any `/chat/completions` API. Used for xAI Grok and Groq; see `factory.PRESETS`."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    def _user_content(self, request: LLMRequest) -> str | list[dict]:
        if not request.attachments:
            return request.prompt
        content: list[dict] = [{"type": "text", "text": request.prompt}]
        for attachment in request.attachments:
            if not attachment.mime_type.startswith("image/"):
                raise LLMError(f"{self.name} can't read {attachment.mime_type} attachments")
            encoded = base64.b64encode(attachment.data).decode()
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{attachment.mime_type};base64,{encoded}"},
                }
            )
        return content

    async def generate(self, request: LLMRequest) -> LLMResponse:
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": self._user_content(request)},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        if request.json_output:
            body["response_format"] = {"type": "json_object"}
        data, latency_ms = await _post(
            self.name,
            f"{self._base_url}/chat/completions",
            {"Authorization": f"Bearer {self._api_key}"},
            body,
            self._timeout,
            self._transport,
        )
        choices = data.get("choices") or []
        text = (choices[0].get("message") or {}).get("content") if choices else None
        if not text:
            raise LLMError(f"{self.name} returned an empty answer")
        meta = data.get("usage") or {}
        usage = Usage(meta.get("prompt_tokens", 0), meta.get("completion_tokens", 0))
        return LLMResponse(text, self.name, self.model, usage, round(latency_ms, 1))


class FallbackProvider:
    """Try each provider in order. A rate limit or outage moves on to the next one; any
    other error (bad key, bad request) stops at once, so configuration mistakes surface
    instead of being hidden by a fallback."""

    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        if not providers:
            raise LLMNotConfigured("No LLM provider is configured.")
        self.providers = list(providers)
        self.name = "+".join(p.name for p in self.providers)
        self.model = self.providers[0].model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        failures: list[str] = []
        for provider in self.providers:
            try:
                return await provider.generate(request)
            except LLMRetryableError as exc:
                failures.append(str(exc))
        raise LLMRetryableError("All providers failed: " + " | ".join(failures))


class FakeProvider:
    """Test double. `replies` is a list of canned texts (used in order) or a function that
    builds a reply from the request. Every request is kept in `requests` for assertions."""

    def __init__(
        self,
        replies: Sequence[str] | Callable[[LLMRequest], str],
        name: str = "fake",
        model: str = "fake-model",
    ) -> None:
        self.name = name
        self.model = model
        self._replies = replies if callable(replies) else list(replies)
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if callable(self._replies):
            text = self._replies(request)
        else:
            if not self._replies:
                raise LLMError("FakeProvider ran out of scripted replies")
            text = self._replies.pop(0)
        usage = Usage(len(request.prompt) // 4, len(text) // 4)  # ~4 characters per token
        return LLMResponse(text, self.name, self.model, usage, 1.0)
