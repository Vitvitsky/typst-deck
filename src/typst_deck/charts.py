"""Ориентация столбцов: вертикально, пока подписи категорий помещаются под столбцами,
иначе горизонтально (подписи — строками слева от столбцов).

Правило — свойство шаблона: раздел charts.columns в template.json. Его читают оба
рендера — адаптер Typst шаблона (сам, функцией json) и экспорт PPTX (здесь), — поэтому
решение одинаково в PDF и в PowerPoint по построению. Порог зависит от ширины графика,
и она разная у трёх раскладок: full — график во всё тело, bullets — рядом с выводами,
dual — половина двойного графика. Числа шаблон подбирает замером (docs/template-contract.md,
раздел «Ориентация столбцов»):

    "charts": {"columns": {"full": [[4, 18], [8, 11], [30, 7]], "bullets": [...], "dual": [...]}}

Пара [L, N]: подписи не длиннее L знаков помещаются вертикально при N категориях и
меньше. Столбцы вертикальны, если подходит хотя бы одна пара. Раздела нет — столбцы
всегда вертикальны, как до появления правила. Длина подписи — в графемах: так же её
считает Typst (str.clusters()).
"""
from __future__ import annotations

import json
from pathlib import Path

LAYOUTS = ("full", "bullets", "dual")


def parse_rule(meta: dict) -> dict[str, list[tuple[int, int]]] | None:
    """Раздел charts.columns из template.json; None — раздела нет. ValueError — сломан."""
    charts = meta.get("charts")
    if charts is None:
        return None
    if not isinstance(charts, dict) or set(charts) - {"columns"}:
        raise ValueError("charts: ожидается объект с ключом columns")
    cols = charts.get("columns")
    if not isinstance(cols, dict) or set(cols) - set(LAYOUTS):
        raise ValueError(f"charts.columns: ожидается объект с ключами из {', '.join(LAYOUTS)}")
    rule = {}
    for layout, pairs in cols.items():
        if not isinstance(pairs, list) or not all(
                isinstance(p, list) and len(p) == 2 and all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in p)
                for p in pairs):
            raise ValueError(f"charts.columns.{layout}: ожидается список пар [длина, число] из целых > 0")
        rule[layout] = [tuple(p) for p in pairs]
    return rule


def load_rule(template_dir: Path) -> dict[str, list[tuple[int, int]]] | None:
    """Правило шаблона с диска; template.json нет или он не JSON — правила нет."""
    p = Path(template_dir) / "template.json"
    try:
        meta = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    return parse_rule(meta) if isinstance(meta, dict) else None


def _clusters(s: str) -> int:
    # графемы без внешней библиотеки: комбинирующие знаки не считаются отдельно
    import unicodedata
    return sum(1 for ch in s if not unicodedata.combining(ch))


def horizontal(labels: list[str], layout: str, rule: dict | None) -> bool:
    """Столбцы горизонтально: правило есть, и ни одна его пара для раскладки не подходит.
    Раскладки нет в правиле — вертикально (шаблон её не обмерял)."""
    if not rule or layout not in rule:
        return False
    n = len(labels)
    longest = max((_clusters(lb) for lb in labels), default=0)
    return not any(longest <= length and n <= count for length, count in rule[layout])
