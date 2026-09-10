import pytest

from typst_deck.model import Deck
from typst_deck.slots import SCHEMA, apply_to_schema, check_deck, check_slide, clamp


def _props(schema: dict, stype: str) -> dict:
    ref = schema["discriminator"]["mapping"][stype].rsplit("/", 1)[1]
    return schema["$defs"][ref]["properties"]


def test_clamp_keeps_declared_limits():
    raw = {"title": {"title": {"max": 60, "lines": 2}, "subtitle": {"max": 90, "lines": 2}},
           "image": {"bullets": {"count": 5, "max": 90}}}
    assert clamp(raw) == raw


def test_clamp_narrows_to_global_ceiling(caplog):
    """Шаблон не может расширить глобальный предел: 300 при TITLE_MAX = 120 даёт 120."""
    with caplog.at_level("WARNING", logger="typst_deck.slots"):
        out = clamp({"title": {"title": {"max": 300}}, "image": {"bullets": {"count": 20, "max": 500}}}, "tight")
    assert out == {"title": {"title": {"max": 120}}, "image": {"bullets": {"count": 6, "max": 200}}}
    assert any("300" in r.getMessage() and "120" in r.getMessage() for r in caplog.records)


def test_clamp_drops_unknown_type_field_and_key(caplog):
    with caplog.at_level("WARNING", logger="typst_deck.slots"):
        out = clamp({"nope": {"title": {"max": 10}},
                     "title": {"bullets": {"max": 10}, "title": {"max": 0, "width": 5, "lines": 1}}}, "tight")
    assert out == {"title": {"title": {"lines": 1}}}
    assert len(caplog.records) == 4  # тип, поле, max=0, неизвестный ключ


def test_clamp_reports_malformed_field_value_not_unknown_field(caplog):
    """Валидное имя поля с испорченным значением — это не «поля нет», а «значение не объект»."""
    with caplog.at_level("WARNING", logger="typst_deck.slots"):
        out = clamp({"image": {"bullets": [1, 2]}}, "tight")
    assert out == {}
    messages = [r.getMessage() for r in caplog.records]
    assert any("image.bullets" in m and "не объект" in m for m in messages)
    assert not any("нет поля" in m for m in messages)


def test_clamp_reports_malformed_type_value_not_unknown_type(caplog):
    """Валидное имя типа слайда с испорченным значением — это не «типа нет», а «значение не объект»."""
    with caplog.at_level("WARNING", logger="typst_deck.slots"):
        out = clamp({"title": "oops"}, "tight")
    assert out == {}
    messages = [r.getMessage() for r in caplog.records]
    assert any(m == "шаблон tight: title — значение не объект, пропущено" for m in messages)
    assert not any("неизвестный тип слайда" in m for m in messages)


def test_clamp_of_nothing_is_empty():
    assert clamp(None) == {} and clamp("не объект") == {} and clamp({}) == {}


def test_lines_has_no_global_ceiling():
    """У числа строк глобального предела в model.py нет — объявление проходит как есть."""
    assert clamp({"title": {"subtitle": {"lines": 9}}}) == {"title": {"subtitle": {"lines": 9}}}


def test_schema_narrowed_by_declared_limits():
    declared = clamp({"title": {"title": {"max": 60}}, "image": {"bullets": {"count": 5, "max": 90}}})
    s = apply_to_schema(declared)
    assert _props(s, "title")["title"]["maxLength"] == 60
    assert _props(s, "image")["bullets"]["maxItems"] == 5
    assert _props(s, "image")["bullets"]["items"]["maxLength"] == 90
    # соседей не задело
    assert _props(s, "section")["title"]["maxLength"] == 120
    assert _props(s, "chart")["bullets"]["maxItems"] == 4


def test_schema_without_slots_is_the_model_schema():
    assert apply_to_schema({}) == SCHEMA


def test_apply_to_schema_does_not_mutate_source():
    apply_to_schema(clamp({"title": {"title": {"max": 10}}}))
    assert _props(SCHEMA, "title")["title"]["maxLength"] == 120


def test_lines_reaches_the_model_as_description():
    """Число строк средствами JSON Schema не выразить — модель читает описание."""
    s = apply_to_schema(clamp({"title": {"subtitle": {"lines": 2}, "author": {"lines": 1}}}))
    assert "2 строк" in _props(s, "title")["subtitle"]["description"]
    assert "без переводов строки" in _props(s, "title")["author"]["description"]


def test_count_on_list_of_objects():
    """У data и series ограничивается только число элементов: их элементы не строки."""
    s = apply_to_schema(clamp({"bar-chart": {"data": {"count": 6, "max": 30}}}))
    assert _props(s, "bar-chart")["data"]["maxItems"] == 6
    assert "maxLength" not in _props(s, "bar-chart")["data"].get("items", {})


TIGHT = clamp({"title": {"title": {"max": 60}, "subtitle": {"lines": 2, "max": 90}},
               "image": {"bullets": {"count": 3, "max": 40}}})


def _slide(**kw):
    return Deck(slides=[kw]).slides[0]


def test_check_reports_chars_field_and_template():
    s = _slide(type="title", title="Э" * 80)
    msgs = check_slide(s, TIGHT, n=1, template_name="Тесный")
    assert msgs == ["слайд 1, поле «Заголовок»: 80 знаков при пределе 60 в шаблоне «Тесный»"]


def test_check_counts_explicit_line_breaks():
    """Порог 2026-09-09: три перевода собирались, четыре — нет."""
    ok = _slide(type="title", title="A", subtitle="а\nб")
    bad = _slide(type="title", title="A", subtitle="а\nб\nв\nг")
    assert check_slide(ok, TIGHT, n=1, template_name="Тесный") == []
    assert check_slide(bad, TIGHT, n=1, template_name="Тесный") == [
        "слайд 1, поле «Подзаголовок»: 4 строки при пределе 2 в шаблоне «Тесный»"
    ]


def test_check_counts_list_items_and_longest_item():
    s = _slide(type="image", title="A", bullets=["раз", "два", "три", "Э" * 50])
    msgs = check_slide(s, TIGHT, n=2, template_name="Тесный")
    assert msgs == [
        "слайд 2, поле «Тезисы»: 4 элемента при пределе 3 в шаблоне «Тесный»",
        "слайд 2, поле «Тезисы»: 50 знаков при пределе 40 в шаблоне «Тесный»",
    ]


def test_check_without_declaration_finds_nothing():
    assert check_slide(_slide(type="title", title="Э" * 119), {}, n=1, template_name="Простой") == []


def test_check_lets_through_an_edit_that_reduces_the_violation():
    """Иначе колода, созданная до появления пределов, стала бы нередактируемой."""
    was = _slide(type="title", title="Э" * 110)
    now = _slide(type="title", title="Э" * 100)
    assert check_slide(now, TIGHT, n=1, template_name="Тесный", before=was) == []
    worse = _slide(type="title", title="Э" * 111)
    assert check_slide(worse, TIGHT, n=1, template_name="Тесный", before=was) != []


def test_check_deck_numbers_slides_from_one():
    d = Deck(slides=[{"type": "final"}, {"type": "title", "title": "Э" * 80}])
    assert check_deck(d, TIGHT, "Тесный") == [
        "слайд 2, поле «Заголовок»: 80 знаков при пределе 60 в шаблоне «Тесный»"
    ]


def test_check_deck_grandfathers_slides_matched_by_id_with_before():
    """set_deck переписывает колоду целиком, но не должен лишать её снисходительности
    к старым слайдам, которой пользуется update_slide (спека §8)."""
    was = Deck(slides=[{"type": "title", "title": "Э" * 100}])
    sid = was.slides[0].id
    now_same = Deck(slides=[{"id": sid, "type": "title", "title": "Э" * 100}])
    assert check_deck(now_same, TIGHT, "Тесный", before=was) == []
    now_worse = Deck(slides=[{"id": sid, "type": "title", "title": "Э" * 101}])
    assert check_deck(now_worse, TIGHT, "Тесный", before=was) == [
        "слайд 1, поле «Заголовок»: 101 знак при пределе 60 в шаблоне «Тесный»"
    ]


def test_check_deck_does_not_grandfather_slide_with_new_id():
    was = Deck(slides=[{"type": "title", "title": "Э" * 100}])
    now = Deck(slides=[{"type": "title", "title": "Э" * 100}])  # другой id — не тот же слайд
    assert check_deck(now, TIGHT, "Тесный", before=was) == [
        "слайд 1, поле «Заголовок»: 100 знаков при пределе 60 в шаблоне «Тесный»"
    ]


@pytest.mark.parametrize("n,word", [(1, "знак"), (2, "знака"), (5, "знаков"), (11, "знаков"), (21, "знак")])
def test_plural_of_measures(n, word):
    from typst_deck.slots import _phrase

    assert _phrase("max", n) == f"{n} {word}"


def test_lmru_declaration_rejects_the_2026_09_09_incident():
    """Четыре перевода строки в подзаголовке титульного слайда — отказ до рендера.

    Это ровно инцидент 2026-09-09: модель вписала переносы строк в subtitle
    титульного слайда, и слайд переполнился. Замер (scripts/measure_slots.py)
    показывает, что зона подзаголовка lmru-hr (30mm при size-h2) вмещает только
    одну строку, поэтому «здоровый» пример ниже — без переноса строки вовсе,
    а не с одним переносом: единственный перенос там уже вышел бы за предел
    ровно потому, что вправду не помещается в слот, а не по прихоти теста.
    """
    import json
    from pathlib import Path

    from typst_deck.slots import check_slide, clamp

    root = Path(__file__).resolve().parents[1] / "templates" / "lmru-hr" / "template.json"
    declared = clamp(json.loads(root.read_text()).get("slots"), "lmru-hr")
    assert declared, "у lmru-hr должен быть объявлен раздел slots"
    bad = Deck(slides=[{"type": "title", "title": "Итоги квартала",
                        "subtitle": "«Лемана ПРО»" + "\n" * 4 + "хвост"}]).slides[0]
    assert check_slide(bad, declared, n=1, template_name="Lemana Tech")
    ok = Deck(slides=[{"type": "title", "title": "Итоги квартала",
                       "subtitle": "«Лемана ПРО» Q3 2026"}]).slides[0]
    assert check_slide(ok, declared, n=1, template_name="Lemana Tech") == []


def _lmru_declared() -> dict:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "templates" / "lmru-hr" / "template.json"
    return clamp(json.loads(root.read_text()).get("slots"), "lmru-hr")


def test_lmru_bar_chart_bullets_over_capacity_are_rejected():
    """bar-chart и chart делят chart-layout (колонка тезисов 38% в body-box с clip):
    четыре тезиса по 200 знаков на bar-chart замерены в 267.3mm при зоне 250mm —
    последний молча обрезался. Тот же текст обязан отвергаться, как на chart."""
    declared = _lmru_declared()
    assert "bar-chart" in declared, "у lmru-hr bar-chart должен быть объявлен, как chart"
    bullets = [("Итоги квартала по направлению данных и аналитики " * 5)[:200]] * 4
    s = Deck(slides=[{"type": "bar-chart", "title": "Итоги", "data": [{"label": "Центр", "value": 42}],
                      "bullets": bullets}]).slides[0]
    msgs = check_slide(s, declared, n=1, template_name="Lemana Tech")
    assert any("«Тезисы»" in m and "200 знаков" in m for m in msgs), msgs
