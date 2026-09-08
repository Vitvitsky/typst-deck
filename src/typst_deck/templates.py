"""Реестр Typst-шаблонов: template/ как «default» плюс templates/<id>/."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .model import Deck


@dataclass
class TemplateInfo:
    id: str
    name: str
    description: str
    path: Path

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description}


class TemplateNotFound(KeyError):
    pass


# Образец для превью: по одному слайду каждого типа.
SAMPLE_DECK = Deck(id="templatepreview", title="Образец шаблона", slides=[
    {"id": "s000001", "type": "title", "title": "Название презентации", "subtitle": "Подзаголовок и дата"},
    {"id": "s000002", "type": "section", "title": "Раздел", "subtitle": "Промежуточный слайд"},
    {"id": "s000003", "type": "image", "title": "Текст и картинка", "bullets": ["Первый тезис", "Второй тезис", "Третий тезис"], "caption": "Подпись"},
    {"id": "s000004", "type": "bar-chart", "title": "Диаграмма", "unit": "млн", "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": 17}, {"label": "Юг", "value": 28}]},
    {"id": "s000005", "type": "chart", "title": "График", "labels": ["Q1", "Q2", "Q3", "Q4"], "series": [{"name": "Выручка", "values": [10, 14, 13, 18]}, {"name": "Расходы", "values": [8, 9, 11, 12]}]},
    {"id": "s000006", "type": "final", "contact": "team@corp"},
])


class TemplateRegistry:
    def __init__(self, default_dir: Path, templates_dir: Path):
        self.default_dir = Path(default_dir)
        self.templates_dir = Path(templates_dir)

    def _info(self, tid: str, path: Path) -> TemplateInfo:
        meta: dict = {}
        mp = path / "template.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text())
            except ValueError:
                meta = {}
        name = meta.get("name") or ("Корпоративный" if tid == "default" else tid)
        return TemplateInfo(tid, name, meta.get("description", ""), path)

    def list(self) -> list[TemplateInfo]:
        out = []
        if (self.default_dir / "deck.typ").exists():
            out.append(self._info("default", self.default_dir))
        if self.templates_dir.is_dir():
            for d in sorted(self.templates_dir.iterdir()):
                if d.is_dir() and (d / "deck.typ").exists() and d.name != "default":
                    out.append(self._info(d.name, d))
        return out

    def get(self, tid: str) -> TemplateInfo:
        if tid == "default" and (self.default_dir / "deck.typ").exists():
            return self._info("default", self.default_dir)
        d = self.templates_dir / tid
        if "/" in tid or ".." in tid or not (d / "deck.typ").exists():
            raise TemplateNotFound(tid)
        return self._info(tid, d)

    def dir_for(self, tid: str) -> Path:
        return self.get(tid).path
