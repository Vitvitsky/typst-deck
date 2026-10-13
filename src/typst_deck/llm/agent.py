"""Цикл агента: сообщение пользователя → вызовы инструментов → новая колода и ответ."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..logs import log_event
from ..model import Deck
from ..slots import apply_to_schema
from .client import LLM
from .tools import ToolExecutor, tool_specs

PROMPT = (Path(__file__).parent / "prompt.md").read_text()
log = logging.getLogger(__name__)


@dataclass
class Outcome:
    reply: str
    changed: bool
    ops: list[str]
    deck: Deck
    changes: list[dict] = field(default_factory=list)
    # один запрос пользователя — до max_iter вызовов модели, поэтому токены суммарные
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    iterations: int = 0
    llm_ms: int = 0


def _template_list(templates: list[dict] | None) -> str:
    if not templates:
        return "(шаблоны не переданы)"
    return "\n".join(f"- {t['id']} — {t['name']}" for t in templates)


def _asset_list(assets: list[str]) -> str:
    """Ассеты колоды — только картинки (видео — ссылкой, ADR 0022)."""
    return f"Картинки: {', '.join(assets) if assets else '(нет)'}"


def build_system_prompt(deck: Deck, assets: list[str], templates: list[dict] | None = None,
                        slots: dict | None = None) -> str:
    return (
        PROMPT
        .replace("{{SCHEMA}}", json.dumps(apply_to_schema(slots or {}), ensure_ascii=False))
        .replace("{{ASSETS}}", _asset_list(assets))
        .replace("{{TEMPLATES}}", _template_list(templates))
        .replace("{{DECK_JSON}}", deck.model_dump_json(include={"title", "template", "slides"}))
    )


def _history_message(m: dict) -> dict:
    """Роли "error" в API нет: неудачу прошлой правки передаём как реплику
    пользователя, иначе провайдер отвергнет запрос, а модель повторит ошибку."""
    if m["role"] == "error":
        return {"role": "user",
                "content": f"Предыдущая правка не применилась: {m['content']}. Учти это и предложи другое решение."}
    return {"role": m["role"], "content": m["content"]}


def _user_content(message: str, files: list[tuple[str, str]]) -> str:
    parts = [message.strip() or "Сделай презентацию по приложенным материалам."]
    for name, text in files:
        parts.append(f"Файл «{name}»:\n```\n{text}\n```")
    return "\n\n".join(parts)


async def run_agent(
    llm: LLM, deck: Deck, user_message: str, files: list[tuple[str, str]],
    history: list[dict], assets: list[str], templates: list[dict] | None = None,
    limits: dict[str, tuple[dict, str]] | None = None,
    aliases: dict[str, str] | None = None,
    max_iter: int = 12,
) -> Outcome:
    """limits — id шаблона → (объявленная ёмкость слотов, имя шаблона) по всем шаблонам.
    aliases — старый id шаблона → действующий: set_template тоже принимает старый."""
    template_ids = [t["id"] for t in templates] if templates else None
    ex = ToolExecutor(deck, template_ids, limits=limits, aliases=aliases)
    tools = tool_specs(template_ids)
    # Схема промпта — из шаблона колоды на старте: промпт уже отправлен и посреди
    # прогона не меняется. О пределах шаблона, выбранного через set_template,
    # модель узнаёт из ERROR — там шаблон назван по имени.
    declared = (limits or {}).get(deck.template, ({}, ""))[0]
    messages: list[dict] = [{"role": "system",
                             "content": build_system_prompt(deck, assets, templates, declared)}]
    messages += [_history_message(m) for m in history]
    messages.append({"role": "user", "content": _user_content(user_message, files)})

    reply = ""
    tokens_in = tokens_out = tokens_cached = iterations = 0
    llm_ns = 0
    for _ in range(max_iter):
        t0 = time.perf_counter_ns()
        c = await llm.complete(messages, tools)
        llm_ns += time.perf_counter_ns() - t0
        iterations += 1
        tokens_in += c.tokens_in
        tokens_out += c.tokens_out
        tokens_cached += c.tokens_cached
        log_event(log, "llm.done", iter=iterations, tok_in=c.tokens_in, tok_out=c.tokens_out,
                  cached=c.tokens_cached, calls=len(c.tool_calls))
        if not c.tool_calls:
            reply = c.text.strip()
            break
        messages.append({"role": "assistant", "content": c.text or None, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
            for tc in c.tool_calls
        ]})
        for tc in c.tool_calls:
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": ex.call(tc.name, tc.arguments)})
        if ex.finished:
            reply = ex.summary
            break
    else:
        reply = "Достигнут лимит шагов; применены правки: " + (", ".join(ex.ops) or "нет")
    if not reply:
        reply = "Готово." if ex.changed else "Модель не вернула ни правок, ни ответа. Попробуйте переформулировать запрос."
    return Outcome(reply=reply, changed=ex.changed, ops=ex.ops, deck=ex.deck, changes=ex.changes,
                   tokens_in=tokens_in, tokens_out=tokens_out, tokens_cached=tokens_cached,
                   iterations=iterations, llm_ms=llm_ns // 1_000_000)
