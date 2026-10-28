"""Minimal agent runtime: a manual tool-use loop with live events, schema-validated results and human pauses.

A manual loop (instead of the SDK tool runner) is used because a case must be able to pause for a human
operator, survive across HTTP requests, and resume with the operator's answer as the pending tool result.
"""

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import jsonschema

from . import llm
from .services import ServiceError
from .store import Case, emit

TERMINAL_TOOL = "trimite_rezultat"


class ToolError(Exception):
    """Expected, recoverable failure: returned to the model as an error tool_result so it can adapt."""


class AgentError(Exception):
    """Unrecoverable failure of an agent loop."""


class PauseForHuman(Exception):
    def __init__(self, question: str, options: list[str], context: str):
        super().__init__(question)
        self.question, self.options, self.context = question, options, context
        self.tool_use_id: str | None = None


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[Case, dict], Awaitable[Any]]

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def _as_content(result: Any):
    """Handlers may return str, JSON-serialisable data, or a list of content blocks (e.g. images)."""
    if isinstance(result, str):
        return result
    if isinstance(result, list) and result and isinstance(result[0], dict) and "type" in result[0]:
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


def _preview(content) -> str:
    if isinstance(content, list):
        kinds = [b.get("type") for b in content]
        return f"{kinds.count('image')} imagini + text" if "image" in kinds else str(content)[:400]
    return content if len(content) <= 1200 else content[:1200] + " …"


class Agent:
    def __init__(self, key: str, label: str, system: str, tools: list[Tool], effort: str,
                 result_schema: dict | None = None, terminal_tool: str = TERMINAL_TOOL, max_turns: int = 14):
        self.key, self.label, self.system, self.effort, self.max_turns = key, label, system, effort, max_turns
        self.tools = {t.name: t for t in tools}
        self.result_schema = result_schema
        self.terminal_tool = terminal_tool
        specs = [t.spec() for t in tools]
        if result_schema is not None:
            specs.append({"name": terminal_tool, "description": "Trimite rezultatul final structurat. Apeleaz-o o singură dată, la final.",
                          "input_schema": result_schema})
        self.tool_specs = specs

    async def run(self, case: Case, task: str) -> dict:
        """Fresh conversation (used for sub-agents)."""
        return await self.loop(case, [{"role": "user", "content": task}])

    async def loop(self, case: Case, messages: list) -> dict:
        nudges = 0
        for _ in range(self.max_turns):
            response = await llm.create_message(system=self.system, messages=messages, tools=self.tool_specs, effort=self.effort)
            case.usage["llm_calls"] += 1
            u = response.usage  # input_tokens excludes cached prefix tokens, so add them for the real total
            case.usage["input_tokens"] += u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
            case.usage["output_tokens"] += response.usage.output_tokens
            for block in response.content:
                if block.type == "thinking" and block.thinking:
                    emit(case, self.label, "thinking", text=block.thinking)
                elif block.type == "text" and block.text.strip():
                    emit(case, self.label, "text", text=block.text)
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                raise AgentError(f"{self.label}: modelul a refuzat cererea")
            if response.stop_reason == "max_tokens":
                raise AgentError(f"{self.label}: răspuns trunchiat (max_tokens)")

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                nudges += 1
                if nudges > 2:
                    raise AgentError(f"{self.label} s-a oprit fără să trimită rezultatul")
                messages.append({"role": "user", "content": f"Continuă lucrul. La final apelează unealta {self.terminal_tool}."})
                continue

            results, final, pause = [], None, None
            for tu in tool_uses:
                if tu.name == self.terminal_tool:
                    try:
                        if self.result_schema is not None:
                            jsonschema.validate(tu.input, self.result_schema)
                        final = tu.input
                        results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "Rezultat înregistrat."})
                    except jsonschema.ValidationError as e:
                        emit(case, self.label, "tool_result", tool=tu.name, ok=False, preview=f"Rezultat invalid: {e.message}")
                        results.append({"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                        "content": f"Rezultatul nu respectă schema: {e.message}. Corectează și retrimite."})
                    continue
                if pause is not None:
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                    "content": "Poți pune o singură întrebare operatorului odată."})
                    continue
                try:
                    content, is_error = await self.execute(case, tu)
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content,
                                    **({"is_error": True} if is_error else {})})
                except PauseForHuman as p:
                    p.tool_use_id = tu.id
                    pause = p

            if pause is not None:
                case.pending_tool_results = results  # sent together with the human answer on resume
                raise pause
            messages.append({"role": "user", "content": results})
            if final is not None:
                return final
        raise AgentError(f"{self.label}: prea mulți pași fără rezultat")

    async def execute(self, case: Case, tu) -> tuple[Any, bool]:
        """Returns (content, is_error). Recoverable errors go back to the model instead of crashing the case."""
        tool = self.tools.get(tu.name)
        emit(case, self.label, "tool_call", tool=tu.name, input=tu.input)
        if tool is None:
            emit(case, self.label, "tool_result", tool=tu.name, ok=False, preview="Unealtă inexistentă")
            return f"Eroare: unealta {tu.name} nu există.", True
        try:
            content = _as_content(await tool.handler(case, tu.input or {}))
        except (ToolError, ServiceError) as e:
            emit(case, self.label, "tool_result", tool=tu.name, ok=False, preview=str(e))
            return f"Eroare: {e}", True
        emit(case, self.label, "tool_result", tool=tu.name, ok=True, preview=_preview(content))
        return content, False
