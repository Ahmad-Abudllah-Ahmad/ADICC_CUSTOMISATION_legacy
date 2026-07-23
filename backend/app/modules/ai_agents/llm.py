# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""LLM bridge - adapt the single-call ``ai`` module client to the agent loop.

The existing ``ai.ai_client.call_ai`` only returns free text. We layer two
strategies on top:

1. Encode the tool catalogue in the system prompt so the LLM knows what
   it can ask for.
2. Parse the response. If it contains a ``<tool_call>{"name":..,"args":..}</tool_call>``
   block we treat it as a tool-call request; otherwise the whole text is a
   final answer.

This is deliberately deterministic & lightweight - no provider-specific
tool-use protocol (Anthropic/OpenAI both work the same way). Tests use
:class:`ScriptedLLM` instead.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.modules.ai_agents.base import LLMBridge, LLMItem, Tool

logger = logging.getLogger(__name__)


_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)


def _format_tools_for_prompt(tools: Iterable[Tool]) -> str:
    """Render the tool catalogue as a short bullet list."""
    lines: list[str] = []
    for t in tools:
        schema = json.dumps(t.input_schema, ensure_ascii=False)
        lines.append(f"- {t.name}: {t.description}\n  input_schema: {schema}")
    return "\n".join(lines)


def _format_history(messages: list[dict[str, Any]]) -> str:
    """Stringify the message log for providers without native tool-use."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        if role == "tool":
            tool_name = m.get("name", "?")
            parts.append(f"[tool:{tool_name}]\n{content}")
        else:
            parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


def parse_llm_response(raw: str) -> LLMItem:
    """Convert raw LLM text into a normalised :data:`LLMItem` dict.

    Recognises ``<tool_call>{...}</tool_call>`` blocks for the
    text-protocol fallback. Anything else becomes ``{"type": "final"}``.
    Exposed at module scope so tests can hit it directly.
    """
    if not raw:
        return {"type": "final", "text": ""}

    match = _TOOL_CALL_RE.search(raw)
    if match:
        body = match.group(1)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            logger.debug("tool_call JSON parse failed: %s", exc)
            return {"type": "final", "text": raw.strip()}
        if not isinstance(payload, dict):
            return {"type": "final", "text": raw.strip()}
        name = str(payload.get("name", "")).strip()
        args = payload.get("args", {})
        if not isinstance(args, dict):
            args = {}
        # Surface any prose before the tool_call as a "thought" channel.
        prose_before = raw[: match.start()].strip()
        item: LLMItem = {"type": "tool_call", "name": name, "args": args}
        if prose_before:
            item["thought"] = prose_before
        return item

    return {"type": "final", "text": raw.strip()}


# ── Concrete bridge: production ──────────────────────────────────────────


@dataclass
class CallAILLM(LLMBridge):
    """Production bridge - talks to the existing ``ai.ai_client.call_ai``."""

    provider: str
    api_key: str
    model: str | None = None
    max_tokens: int = 1500

    async def next_step(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[Tool],
    ) -> tuple[LLMItem, int]:
        """Render the conversation + tool catalogue and ask the LLM what's next."""
        from app.modules.ai.ai_client import call_ai

        tool_block = _format_tools_for_prompt(tools)
        full_system = (
            f"{system_prompt}\n\n"
            f"## Available tools\n{tool_block or '(none)'}\n\n"
            f"## Response protocol\n"
            f"When you need a tool, reply with EXACTLY one block of the form:\n"
            f'<tool_call>{{"name": "<tool_name>", "args": {{...}}}}</tool_call>\n'
            f"You may include short reasoning text BEFORE the block. The runner\n"
            f"will execute the tool and append its result to the conversation.\n"
            f"When you are done, reply with the final answer as plain prose and\n"
            f"NO <tool_call> block. The user reviews the final answer manually."
        )

        prompt = _format_history(messages)
        text, tokens = await call_ai(
            provider=self.provider,
            api_key=self.api_key,
            system=full_system,
            prompt=prompt,
            max_tokens=self.max_tokens,
            model=self.model,
        )
        return parse_llm_response(text), int(tokens or 0)


# ── Scripted bridge: tests ───────────────────────────────────────────────


class ScriptedLLM(LLMBridge):
    """Mock LLM that replays a fixed list of :data:`LLMItem`\\s in order.

    The runner can call :meth:`next_step` more times than the script
    provides; once exhausted, the script's last item is repeated. This
    behaviour is what makes
    ``test_max_iterations_hits_cap`` straightforward - pass a single
    tool_call and the runner keeps re-issuing it until the cap triggers.
    """

    def __init__(self, script: list[LLMItem], *, tokens_per_call: int = 0) -> None:
        if not script:
            msg = "ScriptedLLM requires at least one scripted item"
            raise ValueError(msg)
        self.script = list(script)
        self.tokens_per_call = tokens_per_call
        self.calls = 0

    async def next_step(
        self,
        *,
        system_prompt: str,  # noqa: ARG002 - kept to match the protocol
        messages: list[dict[str, Any]],  # noqa: ARG002
        tools: list[Tool],  # noqa: ARG002
    ) -> tuple[LLMItem, int]:
        idx = min(self.calls, len(self.script) - 1)
        item = self.script[idx]
        self.calls += 1
        return item, self.tokens_per_call
