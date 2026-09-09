import pytest
from pydantic import ValidationError

from typst_deck.model import Deck, SlideAdapter, slide_schema


def deck():
    return Deck(title="Тест", slides=[
        {"type": "title", "title": "Итоги", "subtitle": "Q3"},
        {"type": "image", "title": "Рост", "bullets": ["a", "b"]},
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
    img = SlideAdapter.validate_python({"type": "image", "title": "x"})
    assert img.image is None and img.image_size == "medium" and img.bullets == []


@pytest.mark.parametrize("bad", [
    {"type": "image", "title": "x" * 121},
    {"type": "image", "title": "x", "bullets": ["y" * 201]},
    {"type": "image", "title": "x", "bullets": ["1", "2", "3", "4", "5", "6", "7"]},
    {"type": "image", "title": "x", "image_size": "huge"},
    {"type": "bar-chart", "title": "x", "data": []},
    {"type": "chart", "title": "x", "labels": ["a", "b"], "series": [{"name": "s", "values": [1]}]},
    {"type": "chart", "title": "x", "labels": ["a"], "series": [{"name": "s", "values": [1]}]},
    {"type": "unknown", "title": "x"},
    {"type": "title", "title": "x", "extra": 1},
])
def test_invalid(bad):
    with pytest.raises(ValidationError):
        SlideAdapter.validate_python(bad)


def test_apply_patch():
    d = deck()
    sid = d.slides[1].id
    s = d.apply_patch(sid, {"title": "Новый", "image_size": "large"})
    assert s.title == "Новый" and s.image_size == "large" and s.bullets == ["a", "b"]
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
        d.apply_patch(sid, {"title": "x" * 500})
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


def test_schema_has_all_types():
    text = str(slide_schema())
    for t in ["title", "section", "image", "bar-chart", "chart", "final"]:
        assert f"'{t}'" in text


def test_roundtrip_json():
    d = deck()
    assert Deck.model_validate_json(d.model_dump_json()) == d


def test_title_slide_has_author_and_department():
    """Канон lmru-hr верстает автора и департамент отдельными блоками —
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
