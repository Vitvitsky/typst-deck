"""Клиент к OpenAI-совместимому chat completions API и заглушка для тестов."""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx


class LLMError(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Completion:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0  # сколько промпта попало в кеш провайдера


class LLM(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict]) -> Completion: ...


class FakeLLM:
    """Отдаёт заранее заготовленные ответы по очереди и запоминает входящие сообщения."""

    def __init__(self, completions: list[Completion]):
        self._queue = list(completions)
        self.calls: list[list[dict]] = []

    async def complete(self, messages: list[dict], tools: list[dict]) -> Completion:
        self.calls.append(copy.deepcopy(messages))  # агент дописывает тот же список
        if not self._queue:
            raise LLMError("FakeLLM: ответы закончились")
        return self._queue.pop(0)


JSON_MODE_HINT = (
    "Инструменты недоступны напрямую. Отвечай ТОЛЬКО одним JSON-объектом без пояснений: "
    '{"tool": "<имя>", "args": {...}} чтобы вызвать инструмент, '
    'или {"reply": "<текст>"} чтобы ответить. '
    "Доступные инструменты (JSON Schema):\n"
)


def _with_usage(c: Completion, usage: dict) -> Completion:
    """Токены из ответа провайдера; поля кеша есть не у всех — тогда 0."""
    c.tokens_in = usage.get("prompt_tokens") or 0
    c.tokens_out = usage.get("completion_tokens") or 0
    c.tokens_cached = usage.get("prompt_cache_hit_tokens") or 0
    return c


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMError(f"аргументы инструмента не JSON: {raw[:200]}") from e


class OpenAICompatLLM:
    """tool_mode="tools" — родной tool calling; "json" — инструменты описаны в промпте."""

    def __init__(self, base_url: str, api_key: str, model: str, max_tokens: int = 4096,
                 tool_mode: str = "tools", timeout: float = 120,
                 client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.tool_mode = tool_mode
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def complete(self, messages: list[dict], tools: list[dict]) -> Completion:
        body: dict = {"model": self.model, "max_tokens": self.max_tokens}
        if self.tool_mode == "json":
            body["messages"] = self._rewrite_for_json(messages, tools)
        else:
            body["messages"] = messages
            if tools:
                body["tools"] = tools
        try:
            r = await self._client.post(
                f"{self.base_url}/chat/completions", json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except httpx.HTTPError as e:
            raise LLMError(f"LLM недоступна: {e}") from e
        if r.status_code != 200:
            raise LLMError(f"LLM вернула {r.status_code}: {r.text[:500]}")
        try:
            body_out = r.json()
            choice = body_out["choices"][0]
            msg = choice["message"]
        except (ValueError, KeyError, IndexError) as e:
            raise LLMError(f"неожиданный ответ LLM: {r.text[:500]}") from e
        usage = body_out.get("usage") or {}
        if choice.get("finish_reason") == "length":
            raise LLMError(
                f"ответ модели обрезан по лимиту max_tokens={self.max_tokens}; "
                "увеличьте TYPST_DECK_LLM_MAX_TOKENS (рассуждающие модели тратят лимит на рассуждение)"
            )
        if self.tool_mode == "json":
            return _with_usage(self._parse_json_mode(msg.get("content") or ""), usage)
        calls = [
            ToolCall(tc["id"], tc["function"]["name"], _args(tc["function"].get("arguments")))
            for tc in msg.get("tool_calls") or []
        ]
        return _with_usage(Completion(msg.get("content") or "", calls), usage)

    @staticmethod
    def _rewrite_for_json(messages: list[dict], tools: list[dict]) -> list[dict]:
        out: list[dict] = []
        names: dict[str, str] = {}
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                parts = []
                for tc in m["tool_calls"]:
                    names[tc["id"]] = tc["function"]["name"]
                    parts.append(json.dumps(
                        {"tool": tc["function"]["name"], "args": _args(tc["function"].get("arguments"))},
                        ensure_ascii=False,
                    ))
                out.append({"role": "assistant", "content": "\n".join(parts)})
            elif m["role"] == "tool":
                name = names.get(m.get("tool_call_id", ""), "?")
                out.append({"role": "user", "content": f"Результат {name}: {m['content']}"})
            else:
                out.append(m)
        hint = {"role": "system", "content": JSON_MODE_HINT + json.dumps(tools, ensure_ascii=False)}
        out.insert(1 if out and out[0]["role"] == "system" else 0, hint)
        return out

    @staticmethod
    def _parse_json_mode(text: str) -> Completion:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return Completion(text.strip(), [])
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return Completion(text.strip(), [])
        if isinstance(obj, dict) and "tool" in obj:
            return Completion("", [ToolCall("json-1", str(obj["tool"]), obj.get("args") or {})])
        if isinstance(obj, dict):
            return Completion(str(obj.get("reply", "")), [])
        return Completion(text.strip(), [])
