"""Connectivity check for the LLM: docker compose run --rm orchestrator python -m app.check_llm"""

import asyncio

from . import llm
from .config import settings


async def main():
    print(f"Endpoint: {settings.llm_base_url}\nModel:    {settings.llm_model}")
    tools = [{"name": "ping", "description": "Answers a ping.", "input_schema": {"type": "object", "properties": {}}}]
    r = await llm.create_message(system="You are a connectivity test.", tools=tools, effort="low",
                                 messages=[{"role": "user", "content": "Reply with just: OK"}])
    text = next((b.text for b in r.content if b.type == "text"), "")
    print(f"Reply:    {text!r} (stop_reason={r.stop_reason}, tokens in/out={r.usage.input_tokens}/{r.usage.output_tokens})")


if __name__ == "__main__":
    asyncio.run(main())
