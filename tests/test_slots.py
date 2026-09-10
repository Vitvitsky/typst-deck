from typst_deck.slots import clamp


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
