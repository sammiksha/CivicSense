"""Thin wrapper around the Anthropic SDK: plain completion, forced-tool JSON, and a tool-calling agent loop."""
from __future__ import annotations
import json
from .. import config


class ClaudeLLM:
    def __init__(self, api_key: str, model: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        r = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                        messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in r.content if b.type == "text")

    def force_tool(self, system: str, user: str, name: str, description: str, schema: dict) -> dict:
        """Structured output via a forced tool call (JSON-schema constrained)."""
        r = self.client.messages.create(
            model=self.model, max_tokens=1200, system=system,
            tools=[{"name": name, "description": description, "input_schema": schema}],
            tool_choice={"type": "tool", "name": name},
            messages=[{"role": "user", "content": user}])
        for b in r.content:
            if b.type == "tool_use":
                return dict(b.input)
        return {}

    def run_agent(self, system: str, messages: list[dict], tools: list[dict], execute, max_steps: int = 8):
        """ReAct-style loop: model decides which tool to call, we execute deterministic tools, feed results back."""
        msgs, trace = list(messages), []
        for _ in range(max_steps):
            r = self.client.messages.create(model=self.model, max_tokens=1500, system=system, tools=tools, messages=msgs)
            if r.stop_reason != "tool_use":
                return "".join(b.text for b in r.content if b.type == "text"), trace
            msgs.append({"role": "assistant", "content": r.content})
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    try:
                        out = execute(b.name, dict(b.input))
                    except Exception as e:  # surface tool errors to the model instead of crashing
                        out = {"error": str(e)}
                    trace.append({"tool": b.name, "input": dict(b.input), "ok": "error" not in out})
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, default=str)})
            msgs.append({"role": "user", "content": results})
        return "I could not finish within the step limit; please ask a narrower question.", trace


_llm = None


def get_llm() -> ClaudeLLM | None:
    """None => offline deterministic mode (no API key)."""
    global _llm
    if not config.ANTHROPIC_API_KEY:
        return None
    if _llm is None:
        _llm = ClaudeLLM(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL)
    return _llm
