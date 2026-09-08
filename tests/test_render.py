from pathlib import Path

from typst_deck.model import Deck
from typst_deck.render import render_typ, typ_str, typ_value

GOLDEN = Path(__file__).parent / "golden" / "full.typ"


def full_deck():
    return Deck(id="deck00000001", title="Полная", slides=[
        {"id": "s000001", "type": "title", "title": "Итоги", "subtitle": "Q3 2026"},
        {"id": "s000002", "type": "section", "title": "Финансы"},
        {"id": "s000003", "type": "image", "title": "Рост", "bullets": ["Первый", "Второй"],
         "image": "a000001.png", "image_size": "large", "caption": "Рис. 1"},
        {"id": "s000004", "type": "bar-chart", "title": "Регионы", "unit": "млн",
         "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": 17.5}]},
        {"id": "s000005", "type": "chart", "title": "Динамика", "labels": ["Q1", "Q2"],
         "series": [{"name": "Выручка", "values": [1, 2]}], "bullets": ["Рост"]},
        {"id": "s000006", "type": "final", "contact": "team@corp"},
    ])


def test_typ_str_escapes():
    assert typ_str('a"b\\c\nd') == '"a\\"b\\\\c\\nd"'
    assert typ_str("#not *markup* <x>") == '"#not *markup* <x>"'


def test_typ_value():
    assert typ_value(["a"]) == '("a",)'
    assert typ_value([1, 2.5]) == "(1, 2.5,)"
    assert typ_value({"label": "x", "value": 1}) == '(label: "x", value: 1)'
    assert typ_value(True) == "true"


def test_golden():
    typ, warnings = render_typ(full_deck(), assets={"a000001.png"})
    assert warnings == []
    if not GOLDEN.exists():
        GOLDEN.write_text(typ)
    assert typ == GOLDEN.read_text()


def test_missing_image_warns():
    typ, warnings = render_typ(full_deck(), assets=set())
    assert "image: none" in typ
    assert warnings == ["слайд 3: картинка a000001.png не найдена"]


def test_empty_fields_are_none():
    d = Deck(slides=[{"id": "s000001", "type": "title", "title": "Только заголовок"}])
    typ, _ = render_typ(d, assets=set())
    assert "subtitle: none" in typ
    assert 'field("s000001", "title", "Только заголовок")' in typ


def test_one_call_per_slide():
    typ, _ = render_typ(full_deck(), assets={"a000001.png"})
    assert typ.count("\n#slide-") == 6
