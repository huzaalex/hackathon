"""Minimal agent runtime: a manual tool-use loop with live events, schema-validated results and human pauses.

A manual loop (instead of the SDK tool runner) is used because a case must be able to pause for a human
operator, survive across HTTP requests, and resume with the operator's answer as the pending tool result.

Every tool carries two small formatters (describe / summarize) so the live trace reads as plain English
sentences; the raw input and output are still attached to each event for the "technical details" view.
"""

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import jsonschema

from . import llm
from .services import ServiceError
from .store import Case, emit

TERMINAL_TOOL = "submit_result"


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
    describe: Callable[[dict], str] | None = None  # "what the agent is doing", shown live
    summarize: Callable[[Any], str] | None = None  # "what came back", shown live
    quiet: bool = False  # don't emit a result event (e.g. delegations, which emit their own)

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
        return f"{kinds.count('image')} image(s) + text" if "image" in kinds else str(content)[:400]
    return content if len(content) <= 1200 else content[:1200] + " ..."


def _safe(fn: Callable | None, arg: Any, default: str) -> str:
    if fn is None:
        return default
    try:
        return fn(arg) or default
    except Exception:  # a formatting problem must never break a case
        return default


class Agent:
    def __init__(self, key: str, label: str, system: str, tools: list[Tool], effort: str,
                 result_schema: dict | None = None, terminal_tool: str = TERMINAL_TOOL, max_turns: int = 14,
                 describe_result: Callable[[dict], str] | None = None):
        self.key, self.label, self.system, self.effort, self.max_turns = key, label, system, effort, max_turns
        self.tools = {t.name: t for t in tools}
        self.result_schema = result_schema
        self.terminal_tool = terminal_tool
        self.describe_result = describe_result
        specs = [t.spec() for t in tools]
        if result_schema is not None:
            specs.append({"name": terminal_tool, "description": "Submit the final structured result. Call it exactly once, at the end.",
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
                raise AgentError(f"{self.label}: the model refused the request")
            if response.stop_reason == "max_tokens":
                raise AgentError(f"{self.label}: the response was truncated (max_tokens)")

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                nudges += 1
                if nudges > 2:
                    raise AgentError(f"{self.label} stopped without submitting a result")
                messages.append({"role": "user", "content": f"Continue. When you are done, call the {self.terminal_tool} tool."})
                continue

            results, final, pause = [], None, None
            for tu in tool_uses:
                if tu.name == self.terminal_tool:
                    try:
                        if self.result_schema is not None:
                            jsonschema.validate(tu.input, self.result_schema)
                        final = tu.input
                        results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "Result recorded."})
                    except jsonschema.ValidationError as e:
                        emit(case, self.label, "tool_result", tool=tu.name, ok=False,
                             text="The result did not match the expected format; the agent is correcting it.",
                             preview=e.message)
                        results.append({"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                        "content": f"The result does not match the schema: {e.message}. Fix it and submit again."})
                    continue
                if pause is not None:
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                    "content": "You can only ask the operator one question at a time."})
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
        raise AgentError(f"{self.label}: too many steps without a result")

    async def execute(self, case: Case, tu) -> tuple[Any, bool]:
        """Returns (content, is_error). Recoverable errors go back to the model instead of crashing the case."""
        tool = self.tools.get(tu.name)
        inp = tu.input or {}
        if tool is None:
            emit(case, self.label, "tool_result", tool=tu.name, ok=False, text=f"Tried to use an unknown tool ({tu.name}).")
            return f"Error: the tool {tu.name} does not exist.", True
        emit(case, self.label, "tool_call", tool=tu.name, input=inp, text=_safe(tool.describe, inp, f"Uses {tu.name}."))
        try:
            raw = await tool.handler(case, inp)
        except (ToolError, ServiceError) as e:
            emit(case, self.label, "tool_result", tool=tu.name, ok=False, text=f"Failed: {e}", preview=str(e))
            return f"Error: {e}", True
        content = _as_content(raw)
        if not tool.quiet:
            emit(case, self.label, "tool_result", tool=tu.name, ok=True, text=_safe(tool.summarize, raw, "Done."),
                 preview=_preview(content))
        return content, False
