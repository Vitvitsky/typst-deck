"""Цикл агента: сообщение пользователя → вызовы инструментов → новая колода и ответ."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..model import Deck, slide_schema
from .client import LLM
from .tools import ToolExecutor, tool_specs

PROMPT = (Path(__file__).parent / "prompt.md").read_text()


@dataclass
class Outcome:
    reply: str
    changed: bool
    ops: list[str]
    deck: Deck
    changes: list[dict] = field(default_factory=list)


def _template_list(templates: list[dict] | None) -> str:
    if not templates:
        return "(шаблоны не переданы)"
    return "\n".join(f"- {t['id']} — {t['name']}" for t in templates)


def build_system_prompt(deck: Deck, assets: list[str], templates: list[dict] | None = None) -> str:
    return (
        PROMPT
        .replace("{{SCHEMA}}", json.dumps(slide_schema(), ensure_ascii=False))
        .replace("{{ASSETS}}", ", ".join(assets) if assets else "(нет)")
        .replace("{{TEMPLATES}}", _template_list(templates))
        .replace("{{DECK_JSON}}", deck.model_dump_json(include={"title", "template", "slides"}))
    )


def _user_content(message: str, files: list[tuple[str, str]]) -> str:
    parts = [message.strip() or "Сделай презентацию по приложенным материалам."]
    for name, text in files:
        parts.append(f"Файл «{name}»:\n```\n{text}\n```")
    return "\n\n".join(parts)


async def run_agent(
    llm: LLM, deck: Deck, user_message: str, files: list[tuple[str, str]],
    history: list[dict], assets: list[str], templates: list[dict] | None = None,
    max_iter: int = 12,
) -> Outcome:
    template_ids = [t["id"] for t in templates] if templates else None
    ex = ToolExecutor(deck, template_ids)
    tools = tool_specs(template_ids)
    messages: list[dict] = [{"role": "system", "content": build_system_prompt(deck, assets, templates)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": _user_content(user_message, files)})

    reply = ""
    for _ in range(max_iter):
        c = await llm.complete(messages, tools)
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
    return Outcome(reply=reply, changed=ex.changed, ops=ex.ops, deck=ex.deck, changes=ex.changes)
