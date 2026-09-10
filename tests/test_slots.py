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


def test_clamp_drops_keys_that_do_not_apply_to_the_field(caplog):
    """Таблица §3: lines — только строковым полям, count — только спискам, max —
    строковым полям и спискам строк. image — str | None (anyOf), это не строковое поле."""
    with caplog.at_level("WARNING", logger="typst_deck.slots"):
        out = clamp({"image": {"bullets": {"lines": 1, "max": 90}, "image": {"max": 5},
                               "title": {"count": 2, "max": 70}},
                     "bar-chart": {"data": {"max": 30, "count": 6}}}, "tight")
    assert out == {"image": {"bullets": {"max": 90}, "title": {"max": 70}},
                   "bar-chart": {"data": {"count": 6}}}
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 4
    assert all("не применим" in m for m in messages), messages
    assert any("image.bullets.lines" in m and "строковым полям" in m for m in messages)
    assert any("image.title.count" in m and "спискам" in m for m in messages)


# Минимальный правильный слайд каждого типа; в списках по два элемента, чтобы
# count: 1 нарушался уже ими, а подписи chart держали длину рядов.
BASE = {
    "title": {"type": "title", "title": "А"},
    "section": {"type": "section", "title": "А"},
    "image": {"type": "image", "title": "А"},
    "bar-chart": {"type": "bar-chart", "title": "А",
                  "data": [{"label": "а", "value": 1}, {"label": "б", "value": 2}]},
    "chart": {"type": "chart", "title": "А", "labels": ["а", "б"],
              "series": [{"name": "р", "values": [1, 2]}, {"name": "с", "values": [3, 4]}]},
    "final": {"type": "final"},
}


def _violating(prop: dict, key: str, base: object) -> object:
    """Значение поля, нарушающее предел 1 по этому ключу."""
    if key == "lines":
        return "а\nб"
    if key == "count":
        return base if isinstance(base, list) and len(base) >= 2 else ["а", "б"]
    if prop.get("type") == "array":  # max у списка строк — длина элемента
        return ["аб"] * max(len(base or []), 1)
    return "аб"


def test_every_key_clamp_keeps_reaches_the_schema_and_is_enforced():
    """Схема и проверка согласованы не на примерах, а по всем сочетаниям:
    каждый ключ, переживший clamp, модель видит в схеме и check_slide проверяет."""
    from typst_deck.slots import DEFS, FIELD_RU, KEYS

    raw = {t: {f: {k: 1 for k in KEYS} for f in d["properties"]} for t, d in DEFS.items()}
    declared = clamp(raw, "все сочетания")
    combos = [(t, f, k) for t, fields in declared.items() for f, lim in fields.items() for k in lim]
    # сверка с таблицей §3 на известных полях, чтобы тест не прошёл на пустом объявлении
    assert ("image", "bullets", "max") in combos and ("image", "bullets", "count") in combos
    assert ("title", "subtitle", "lines") in combos and ("chart", "series", "count") in combos
    for gone in [("image", "bullets", "lines"), ("image", "image", "max"),
                 ("image", "title", "count"), ("bar-chart", "data", "max")]:
        assert gone not in combos, gone

    schema_props = {t: _props(apply_to_schema(declared), t) for t in DEFS}
    for stype, field, key in combos:
        prop = schema_props[stype][field]
        if key == "max":
            target = prop["items"] if prop.get("type") == "array" else prop
            assert target.get("maxLength") == 1, (stype, field, key)
        elif key == "count":
            assert prop.get("maxItems") == 1, (stype, field, key)
        else:
            assert "одна строка" in prop.get("description", ""), (stype, field, key)

        value = _violating(DEFS[stype]["properties"][field], key, BASE[stype].get(field))
        slide = Deck(slides=[BASE[stype] | {field: value}]).slides[0]
        msgs = check_slide(slide, {stype: {field: {key: 1}}}, n=1, template_name="Т")
        assert len(msgs) == 1 and f"«{FIELD_RU.get(field, field)}»" in msgs[0], (stype, field, key, msgs)


def test_list_max_lets_an_untouched_old_long_bullet_through():
    """Старый длинный тезис, которого правка не касалась, не мешает править слайд."""
    was = _slide(type="image", title="A", bullets=["Э" * 100])
    now = _slide(type="image", title="Б", bullets=["Э" * 100, "короткий"])
    assert check_slide(now, TIGHT, n=1, template_name="Тесный", before=was) == []


def test_list_max_rejects_a_new_long_bullet_next_to_an_old_one():
    """Самый длинный элемент не вырос, но поле стало хуже: длинных тезисов стало два."""
    was = _slide(type="image", title="A", bullets=["Э" * 100])
    now = _slide(type="image", title="A", bullets=["Э" * 100, "Ю" * 90])
    assert check_slide(now, TIGHT, n=1, template_name="Тесный", before=was) == [
        "слайд 1, поле «Тезисы»: 90 знаков при пределе 40 в шаблоне «Тесный»"
    ]


def test_list_max_lets_a_shortened_old_bullet_through():
    """Спека §8: правка, уменьшающая нарушение, проходит и у элемента списка —
    старый тезис в 100 знаков, сокращённый до 60 при пределе 40, не отвергается."""
    was = _slide(type="image", title="A", bullets=["Э" * 100])
    now = _slide(type="image", title="A", bullets=["Э" * 60])
    assert check_slide(now, TIGHT, n=1, template_name="Тесный", before=was) == []


def test_list_max_rejects_shortening_one_bullet_to_make_room_for_another():
    """Сокращённый старый тезис не даёт права добавить рядом ещё один длинный."""
    was = _slide(type="image", title="A", bullets=["Э" * 100])
    now = _slide(type="image", title="A", bullets=["Э" * 60, "Ю" * 50])
    assert check_slide(now, TIGHT, n=1, template_name="Тесный", before=was) == [
        "слайд 1, поле «Тезисы»: 50 знаков при пределе 40 в шаблоне «Тесный»"
    ]


def test_first_few_keeps_five_and_counts_the_rest():
    from typst_deck.slots import first_few

    assert first_few([]) == []
    assert first_few(list("абвгд")) == list("абвгд")
    assert first_few(list("абвгдеж")) == list("абвгд") + ["и ещё 2"]


def test_field_names_match_the_interface():
    """Имена полей в сообщениях — те же, что в интерфейсе (static/api.js): иначе
    человек видит в плашке «image», а в панели свойств — «Картинка»."""
    import re
    from pathlib import Path

    from typst_deck.slots import FIELD_RU

    js = (Path(__file__).resolve().parents[1] / "src" / "typst_deck" / "static" / "api.js").read_text()
    block = js.split("export const FIELD_RU = {", 1)[1].split("};", 1)[0]
    assert FIELD_RU == dict(re.findall(r'(\w+): "([^"]+)"', block))
