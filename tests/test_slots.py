from typst_deck.slots import SCHEMA, apply_to_schema, clamp


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
