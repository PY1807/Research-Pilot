"""Get JSON out of an LLM and check it against a Pydantic model.

Providers differ in how strictly they enforce JSON schemas, so we rely on the one thing all
of them do: "reply with a JSON object". The expected shape goes in the prompt, Pydantic
checks the reply, and if it doesn't fit we ask once more, quoting the validation error.
"""

import json
import re
from dataclasses import dataclass, replace

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def extract_json(text: str) -> object:
    """Parse a JSON object from a reply, tolerating ```json fences and stray prose."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    value: T
    responses: list[LLMResponse]  # every call made, including failed attempts


async def generate_structured[T: BaseModel](
    llm: LLMProvider, request: LLMRequest, schema: type[T], max_attempts: int = 2
) -> StructuredResult[T]:
    request = replace(request, json_output=True)
    responses: list[LLMResponse] = []
    prompt = request.prompt
    for _ in range(max_attempts):
        response = await llm.generate(replace(request, prompt=prompt))
        responses.append(response)
        try:
            return StructuredResult(schema.model_validate(extract_json(response.text)), responses)
        except (json.JSONDecodeError, ValidationError) as exc:
            error = str(exc).splitlines()[0][:300]
            prompt = (
                f"{request.prompt}\n\nYour previous reply could not be used ({error}). "
                "Reply again with only the JSON object in the required shape."
            )
    raise LLMError(f"No valid JSON after {max_attempts} attempts")


def cost_usd(response: LLMResponse) -> float:
    """Estimated cost from the price table in settings. Models not in the table (free
    tiers) cost 0, but their tokens are still counted, so switching to a paid tier later
    gives an honest estimate from the same logs."""
    prices = get_settings().llm_prices_per_million.get(response.model)
    if not prices:
        return 0.0
    input_price, output_price = prices
    usage = response.usage
    return round((usage.input_tokens * input_price + usage.output_tokens * output_price) / 1e6, 6)
