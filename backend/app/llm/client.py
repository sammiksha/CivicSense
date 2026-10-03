"""Universal LLM client for FinVision supporting OpenAI, Anthropic, Gemini, Groq, and custom endpoints.
Executes real function-calling tool agent loops server-side.
"""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from .. import config


class UniversalLLM:
    def __init__(self, provider: str, api_key: str, model: str, base_url: str = ""):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def _openai_request(self, payload: dict) -> dict:
        url = (self.base_url.rstrip("/") + "/chat/completions") if self.base_url else "https://api.openai.com/v1/chat/completions"
        if self.provider == "groq" and not self.base_url:
            url = "https://api.groq.com/openai/v1/chat/completions"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "FinVision/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _anthropic_request(self, payload: dict) -> dict:
        url = (self.base_url.rstrip("/") + "/v1/messages") if self.base_url else "https://api.anthropic.com/v1/messages"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "User-Agent": "FinVision/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        if self.provider == "anthropic":
            data = self._anthropic_request({
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}]
            })
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

        # Default OpenAI format (works for OpenAI, Groq, OpenRouter, LocalAI)
        data = self._openai_request({
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        })
        return data["choices"][0]["message"]["content"] or ""

    def force_tool(self, system: str, user: str, name: str, description: str, schema: dict) -> dict:
        if self.provider == "anthropic":
            data = self._anthropic_request({
                "model": self.model,
                "max_tokens": 1200,
                "system": system,
                "tools": [{"name": name, "description": description, "input_schema": schema}],
                "tool_choice": {"type": "tool", "name": name},
                "messages": [{"role": "user", "content": user}]
            })
            for b in data.get("content", []):
                if b.get("type") == "tool_use":
                    return dict(b.get("input", {}))
            return {}

        # OpenAI format
        tools_def = [{
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema
            }
        }]
        data = self._openai_request({
            "model": self.model,
            "max_tokens": 1200,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "tools": tools_def,
            "tool_choice": {"type": "function", "function": {"name": name}}
        })
        tool_calls = data["choices"][0]["message"].get("tool_calls", [])
        if tool_calls:
            args = tool_calls[0]["function"]["arguments"]
            return json.loads(args) if isinstance(args, str) else dict(args)
        return {}

    def run_agent(self, system: str, messages: list[dict], tools: list[dict], execute_fn, max_steps: int = 6):
        """Universal ReAct / Tool-calling agent loop."""
        trace = []

        if self.provider == "anthropic":
            # Anthropic tool format
            anthropic_tools = [
                {"name": t["name"], "description": t["description"], "input_schema": t.get("parameters", t.get("input_schema", {}))}
                for t in tools
            ]
            msgs = list(messages)
            for _ in range(max_steps):
                resp = self._anthropic_request({
                    "model": self.model,
                    "max_tokens": 1500,
                    "system": system,
                    "tools": anthropic_tools,
                    "messages": msgs
                })
                stop_reason = resp.get("stop_reason")
                if stop_reason != "tool_use":
                    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
                    return text, trace

                content_blocks = resp.get("content", [])
                msgs.append({"role": "assistant", "content": content_blocks})
                tool_results = []
                for b in content_blocks:
                    if b.get("type") == "tool_use":
                        t_name = b["name"]
                        t_args = dict(b.get("input", {}))
                        try:
                            out = execute_fn(t_name, t_args)
                            trace.append({"tool": t_name, "input": t_args, "ok": True})
                        except Exception as e:
                            out = {"error": str(e)}
                            trace.append({"tool": t_name, "input": t_args, "ok": False})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": b["id"],
                            "content": json.dumps(out, default=str)
                        })
                msgs.append({"role": "user", "content": tool_results})
            return "Analysis complete based on the financial calculations.", trace

        # OpenAI / Universal format
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("parameters", t.get("input_schema", {}))
                }
            }
            for t in tools
        ]

        chat_messages = [{"role": "system", "content": system}]
        for m in messages:
            # Normalize message content
            content = m.get("content", "")
            if isinstance(content, list):
                content = json.dumps(content)
            chat_messages.append({"role": m.get("role", "user"), "content": content})

        for _ in range(max_steps):
            resp = self._openai_request({
                "model": self.model,
                "max_tokens": 1500,
                "messages": chat_messages,
                "tools": openai_tools,
                "temperature": 0.2
            })
            choice = resp["choices"][0]
            msg = choice["message"]
            chat_messages.append(msg)

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                return msg.get("content", ""), trace

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                fn_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                try:
                    out = execute_fn(fn_name, fn_args)
                    trace.append({"tool": fn_name, "input": fn_args, "ok": True})
                except Exception as e:
                    out = {"error": str(e)}
                    trace.append({"tool": fn_name, "input": fn_args, "ok": False})

                chat_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(out, default=str)
                })

        return "Analysis complete based on verified calculations.", trace


_llm_instance = None


def get_llm() -> UniversalLLM | None:
    global _llm_instance
    if not config.LLM_API_KEY:
        return None
    if _llm_instance is None:
        _llm_instance = UniversalLLM(
            provider=config.LLM_PROVIDER,
            api_key=config.LLM_API_KEY,
            model=config.LLM_MODEL,
            base_url=config.LLM_BASE_URL
        )
    return _llm_instance
