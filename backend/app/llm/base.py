"""The LLM interface the rest of the app talks to. Nothing outside `app/llm/` knows which
company's model answered: services build an `LLMRequest`, get back an `LLMResponse`.

Requests can carry attachments (page images, PDFs) for multimodal models. Providers that
can't read an attachment type raise `LLMError` instead of silently ignoring it.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Attachment:
    data: bytes
    mime_type: str  # e.g. "image/png", "application/pdf"


@dataclass(frozen=True)
class LLMRequest:
    system: str
    prompt: str
    attachments: tuple[Attachment, ...] = ()
    # Ask the provider for a JSON object. The shape is described in the prompt and checked
    # with Pydantic afterwards (see structured.py), which works the same on every provider.
    json_output: bool = False
    # 0 = as repeatable as the provider allows. Answers and judgments should not be creative.
    temperature: float = 0.0
    # Generous because "thinking" models spend part of this budget on hidden reasoning.
    max_output_tokens: int = 4096


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0


class LLMError(Exception):
    """A provider call failed in a way retrying elsewhere won't fix (bad key, bad request)."""


class LLMRetryableError(LLMError):
    """The provider is rate-limited, overloaded, or unreachable. Another provider (or the
    same one later) may succeed, so the fallback chain moves on."""


class LLMNotConfigured(LLMError):
    """No provider has an API key set."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(self, request: LLMRequest) -> LLMResponse: ...
