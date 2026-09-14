import pytest
from pydantic import ValidationError

from typst_deck.model import Deck, SlideAdapter, slide_schema


def deck():
    return Deck(title="Тест", slides=[
        {"type": "title", "title": "Итоги", "subtitle": "Q3"},
        {"type": "text", "title": "Рост", "bullets": ["a", "b"]},
        {"type": "final"},
    ])


def test_ids_generated():
    d = deck()
    assert len(d.id) == 12 and d.id.isalnum() and d.id.islower()
    assert all(s.id.startswith("s") and len(s.id) == 7 for s in d.slides)
    assert len({s.id for s in d.slides}) == 3


def test_discriminator_and_defaults():
    s = SlideAdapter.validate_python({"type": "final"})
    assert s.title == "Спасибо" and s.contact == ""
    img = SlideAdapter.validate_python({"type": "image", "title": "x", "image": "a.png"})
    assert img.image == "a.png" and img.image_size == "medium" and img.bullets == []


@pytest.mark.parametrize("bad", [
    {"type": "chart", "title": "x", "labels": [], "series": [{"name": "s", "values": []}]},
    {"type": "image", "title": "x", "image": "a1.png", "bullets": ["y" * 201]},
    {"type": "image", "title": "x", "bullets": ["1", "2", "3", "4", "5", "6", "7"]},
    {"type": "image", "title": "x", "image_size": "huge"},
    {"type": "chart", "title": "x", "labels": ["a", "b"], "series": [{"name": "s", "values": [1]}]},
    {"type": "chart", "title": "x", "labels": ["a"], "series": [{"name": "s", "values": [1]}]},
    {"type": "unknown", "title": "x"},
    {"type": "title", "title": "x", "extra": 1},
])
def test_invalid(bad):
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python(bad)


def test_all_types_are_in_the_schema():
    from typst_deck.model import SLIDE_TYPES

    text = str(slide_schema())
    assert len(SLIDE_TYPES) == 15
    for t in SLIDE_TYPES:
        assert f"'{t}'" in text


def test_text_and_image_are_separate_types():
    """image без картинки больше не бывает: для тезисов есть text."""
    t = SlideAdapter.validate_python({"type": "text", "title": "Итоги", "bullets": ["раз"]})
    assert t.bullets == ["раз"]
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python({"type": "text", "title": "Итоги", "bullets": []})
    img = SlideAdapter.validate_python({"type": "image", "title": "Рост", "image": "a1.png"})
    assert img.image == "a1.png" and img.image_size == "medium"
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python({"type": "image", "title": "Рост"})


def test_chart_kinds_and_lengths():
    bar = SlideAdapter.validate_python({"type": "chart", "title": "Итоги", "kind": "bar",
                                        "labels": ["Центр"], "series": [{"name": "млн", "values": [42]}]})
    assert bar.kind == "bar"
    line = SlideAdapter.validate_python({"type": "chart", "title": "Итоги",
                                         "labels": ["Q1", "Q2"], "series": [{"name": "Ряд", "values": [1, 2]}]})
    assert line.kind == "line", "по умолчанию — линия"
    with pytest.raises(ValidationError):  # линии нужна вторая точка
        SlideAdapter.validate_python({"type": "chart", "title": "x", "kind": "line",
                                      "labels": ["Q1"], "series": [{"name": "Ряд", "values": [1]}]})
    with pytest.raises(ValidationError):  # значений столько же, сколько подписей
        SlideAdapter.validate_python({"type": "chart", "title": "x", "kind": "bar",
                                      "labels": ["a", "b"], "series": [{"name": "Ряд", "values": [1]}]})


def test_table_rows_match_the_header():
    ok = SlideAdapter.validate_python({"type": "table", "title": "Итоги",
                                       "header": ["Регион", "Выручка"], "rows": [["Центр", "42"]]})
    assert ok.rows == [["Центр", "42"]]
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python({"type": "table", "title": "x",
                                      "header": ["Регион", "Выручка"], "rows": [["Центр"]]})


def test_video_refuses_a_wrong_asset_and_a_wrong_link():
    """План C откроет загрузку видео и поле ссылки в интерфейсе; пределы ставим сейчас."""
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python({"type": "video", "title": "Р", "video": "photo.png"})
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python({"type": "video", "title": "Р", "video": "a1.mp4",
                                      "poster": "clip.mp4"})
    for bad in ("javascript:alert(1)", "ftp://h/1.mp4", "h" * 5000):
        with pytest.raises(ValidationError):
            SlideAdapter.validate_python({"type": "video", "title": "Р", "url": bad})
    ok = SlideAdapter.validate_python({"type": "video", "title": "Р", "url": "http://h/1.mp4",
                                       "poster": "a1.jpg"})
    assert ok.poster == "a1.jpg"


def test_chart_bullets_are_capped_at_the_measured_length():
    """Замер 2026-09-14: четыре вывода по 150 знаков уходят под обрез страницы,
    по 140 — последняя ступень лестницы кеглей; предел — 120 знаков."""
    base = {"type": "chart", "title": "Г", "labels": ["A", "B"],
            "series": [{"name": "р", "values": [1, 2]}]}
    assert len(SlideAdapter.validate_python(base | {"bullets": ["Э" * 120] * 4}).bullets) == 4
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python(base | {"bullets": ["Э" * 121]})


def test_table_cell_is_capped_at_the_measured_length():
    """Восемь строк по шесть ячеек: обрыв на 43 знаках, предел стоит на ~12 %
    ниже него. Запас меряется во входных данных, а не в ступенях кегля."""
    base = {"type": "table", "title": "Т", "header": ["а", "б"]}
    SlideAdapter.validate_python(base | {"rows": [["Э" * 38, "б"]]})
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python(base | {"rows": [["Э" * 39, "б"]]})


def test_large_picture_leaves_less_room_for_bullets():
    """Ёмкость зависит от оформления, которое выбирает тот же пользователь: при
    «large» картинка берёт 55 % ширины. Резать тезисы у всех размеров нельзя —
    при medium и small тот же текст помещается."""
    base = {"type": "image", "title": "К", "image": "a1.png"}
    SlideAdapter.validate_python(base | {"bullets": ["Э" * 200] * 6, "image_size": "medium"})
    SlideAdapter.validate_python(base | {"bullets": ["Э" * 150] * 6, "image_size": "large"})
    with pytest.raises(ValidationError) as e:
        SlideAdapter.validate_python(base | {"bullets": ["Э" * 200] * 6, "image_size": "large"})
    assert "large" in str(e.value)


def test_video_takes_exactly_one_source():
    f = SlideAdapter.validate_python({"type": "video", "title": "Ролик", "video": "a1.mp4"})
    assert f.video == "a1.mp4" and f.url == ""
    u = SlideAdapter.validate_python({"type": "video", "title": "Ролик", "url": "https://v/1"})
    assert u.url == "https://v/1"
    for bad in ({}, {"video": "a1.mp4", "url": "https://v/1"}):
        with pytest.raises(ValidationError):
            SlideAdapter.validate_python({"type": "video", "title": "Ролик", **bad})


@pytest.mark.parametrize("bad", [
    {"type": "agenda", "title": "x", "items": ["раз", "два"]},                      # меньше трёх
    {"type": "agenda", "title": "x", "items": ["п"] * 8},                            # больше семи
    {"type": "columns", "title": "x", "blocks": [{"text": "один"}]},                 # меньше двух
    {"type": "columns", "title": "x", "blocks": [{"text": "т" * 301}, {"text": "б"}]},
    {"type": "comparison", "title": "x", "left": {"bullets": []}, "right": {"bullets": ["б"]}},
    {"type": "quote", "text": "ц" * 301},
    {"type": "metrics", "title": "x", "items": [{"value": "1", "label": "a"}]},      # меньше двух
    {"type": "metrics", "title": "x", "items": [{"value": "1" * 17, "label": "a"}, {"value": "2", "label": "b"}]},
    {"type": "table", "title": "x", "header": ["одна"], "rows": [["a"]]},            # меньше двух колонок
    {"type": "gallery", "title": "x", "images": [{"image": "a1.png"}]},              # меньше двух
    {"type": "dual-chart", "title": "x",
     "left": {"labels": ["a", "b"], "series": [{"name": "s", "values": [1, 2]}]},
     "right": {"labels": ["a", "b"], "series": [{"name": "s", "values": [1]}]}},     # длины не совпали
])
def test_invalid_new_types(bad):
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python(bad)


def test_apply_patch():
    d = deck()
    sid = d.slides[1].id
    s = d.apply_patch(sid, {"title": "Новый"})
    assert s.title == "Новый" and s.bullets == ["a", "b"]
    assert d.slides[1] is s and s.id == sid


def test_patch_cannot_change_type_or_id():
    d = deck()
    with pytest.raises(ValueError):
        d.apply_patch(d.slides[1].id, {"type": "final"})
    with pytest.raises(ValueError):
        d.apply_patch(d.slides[1].id, {"id": "s000000"})


def test_patch_invalid_keeps_slide():
    d = deck()
    sid = d.slides[1].id
    with pytest.raises(ValidationError):
        d.apply_patch(sid, {"title": "x" * 121})
    assert d.find(sid).title == "Рост"


def test_add_remove_move():
    d = deck()
    s = d.add_slide({"type": "section", "title": "Раздел"}, after=d.slides[0].id)
    assert d.index_of(s.id) == 1
    s2 = d.add_slide({"type": "section", "title": "В конец"}, after=None)
    assert d.index_of(s2.id) == 4
    d.move_slide(s2.id, 0)
    assert d.slides[0] is s2
    d.remove_slide(s2.id)
    assert len(d.slides) == 4
    with pytest.raises(KeyError):
        d.find("s_nope")


def test_roundtrip_json():
    d = deck()
    assert Deck.model_validate_json(d.model_dump_json()) == d


def test_title_slide_has_author_and_department():
    """Канон Lemana Tech верстает автора и департамент отдельными блоками —
    без этих полей их приходилось запихивать в подзаголовок переносами строк."""
    from typst_deck.model import TitleSlide

    s = TitleSlide(type="title", title="Итоги")
    assert s.author == "" and s.department == ""
    s = TitleSlide(type="title", title="Итоги", author="Сергей Витвицкий",
                   department="ПК Данные и аналитика")
    assert s.author == "Сергей Витвицкий"
    assert s.department == "ПК Данные и аналитика"


def test_title_slide_author_is_length_limited():
    import pytest
    from pydantic import ValidationError

    from typst_deck.model import TitleSlide

    with pytest.raises(ValidationError):
        TitleSlide(type="title", title="Итоги", author="я" * 200)


def test_slide_schema_exposes_author_to_model():
    import json

    from typst_deck.model import slide_schema

    assert "author" in json.dumps(slide_schema(), ensure_ascii=False)
    assert "department" in json.dumps(slide_schema(), ensure_ascii=False)
