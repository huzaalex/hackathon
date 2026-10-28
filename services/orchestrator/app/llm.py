"""Thin wrapper around the Anthropic SDK pointed at Claude in Amazon Bedrock."""

import anthropic

from .config import settings

_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.bedrock_api_key:
            raise RuntimeError("BEDROCK_API_KEY is missing from .env")
        _client = anthropic.AsyncAnthropic(base_url=settings.llm_base_url, api_key=settings.bedrock_api_key,
                                           max_retries=3, timeout=180.0)
    return _client


async def create_message(*, system: str, messages: list, tools: list[dict], effort: str):
    params = dict(
        max_tokens=16000,
        system=system,
        messages=messages,
        tools=tools,
        thinking={"type": "adaptive", "display": "summarized"},  # summaries are streamed to the dashboard
        output_config={"effort": effort},
        cache_control={"type": "ephemeral"},  # system + tools are stable across the agent loop
    )
    response = await client().messages.create(model=settings.llm_model, **params)
    # Server-side fallback isn't available on Bedrock: retry once on a fallback model if the request was refused
    if response.stop_reason == "refusal" and settings.llm_fallback_model:
        response = await client().messages.create(model=settings.llm_fallback_model, **params)
    return response
