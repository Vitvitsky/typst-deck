"""Знак значения на графиках: свой цвет у падения — контракт всех шаблонов.

Столбец ниже нуля и столбец роста должны читаться по-разному, иначе −7 %
выглядит как «около нуля» (ровно то, что было до правки).
"""
import pytest

from tests.conftest import ROOT, TEMPLATE_DIR, requires_typst
from typst_deck.model import Deck
from typst_deck.render import compile_deck

pytestmark = requires_typst

# id шаблона → (каталог, цвет роста, цвет падения)
TEMPLATES = {
    "default": (TEMPLATE_DIR, "#3b6ea5", "#c0392b"),
    "dark": (ROOT / "templates" / "dark", "#d97a2b", "#e5534b"),
}


def signed_deck() -> Deck:
    return Deck(id="signed000001", slides=[
        {"id": "s000001", "type": "chart", "kind": "bar", "title": "Прирост", "unit": "%",
         "labels": ["Отделка", "Стройматериалы"],
         "series": [{"name": "Прирост", "values": [12, -7]}]},
        {"id": "s000002", "type": "chart", "title": "Динамика", "labels": ["Q1", "Q2", "Q3"],
         "series": [{"name": "Прирост", "values": [12, 5, -7]}]},
    ])


def compile_in(tid, deck_dir):
    path, pos, neg = TEMPLATES[tid]
    return compile_deck(signed_deck(), deck_dir, path), pos, neg


@pytest.mark.parametrize("tid", list(TEMPLATES))
def test_negative_bar_gets_its_own_colour(tid, deck_dir):
    r, pos, neg = compile_in(tid, deck_dir)
    svg = r.svgs[0].read_text()
    assert pos in svg, f"{tid}: столбец роста не покрашен цветом роста"
    assert neg in svg, f"{tid}: столбец падения не отличается по цвету от роста"


@pytest.mark.parametrize("tid", list(TEMPLATES))
def test_signed_charts_keep_one_page_per_slide(tid, deck_dir):
    r, _, _ = compile_in(tid, deck_dir)
    assert len(r.svgs) == 2
