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


def test_page_size_reads_viewbox(tmp_path):
    from typst_deck.render import page_size

    p = tmp_path / "slide-1.svg"
    p.write_text('<svg class="typst-doc" viewBox="0 0 1919.05511811 1080" width="1919" xmlns="http://www.w3.org/2000/svg">')
    assert page_size(p) == {"w": 1919.05511811, "h": 1080.0}


def test_page_size_defaults_when_file_missing(tmp_path):
    from typst_deck.render import DEFAULT_PAGE, page_size

    assert page_size(tmp_path / "нет.svg") == DEFAULT_PAGE


def test_page_size_defaults_when_viewbox_absent(tmp_path):
    from typst_deck.render import DEFAULT_PAGE, page_size

    p = tmp_path / "slide-1.svg"
    p.write_text('<svg width="100" xmlns="http://www.w3.org/2000/svg"></svg>')
    assert page_size(p) == DEFAULT_PAGE


def test_page_size_reads_only_head_of_large_file(tmp_path):
    """viewBox стоит в первых байтах: файл на 160 КБ читать целиком незачем."""
    from typst_deck.render import page_size

    p = tmp_path / "slide-1.svg"
    p.write_text('<svg viewBox="0 0 800 600" xmlns="http://www.w3.org/2000/svg">' + "<path/>" * 40000)
    assert page_size(p) == {"w": 800.0, "h": 600.0}


def _deck_of(n: int):
    from typst_deck.model import Deck

    return Deck(slides=[{"type": "section", "title": f"С{i}"} for i in range(1, n + 1)])


def test_overflowing_slide_finds_culprit_by_shift():
    """Переполнившийся слайд держит свои поля на своей странице, а съезжает всё после него."""
    from typst_deck.render import overflowing_slide

    deck = _deck_of(4)
    ids = [s.id for s in deck.slides]
    positions = [{"slide": ids[0], "page": 1}, {"slide": ids[1], "page": 3},
                 {"slide": ids[2], "page": 4}, {"slide": ids[3], "page": 5}]
    assert overflowing_slide(deck, positions) == 1


def test_overflowing_slide_in_the_middle():
    from typst_deck.render import overflowing_slide

    deck = _deck_of(4)
    ids = [s.id for s in deck.slides]
    positions = [{"slide": ids[0], "page": 1}, {"slide": ids[1], "page": 2},
                 {"slide": ids[2], "page": 4}, {"slide": ids[3], "page": 5}]
    assert overflowing_slide(deck, positions) == 2


def test_overflowing_slide_is_the_last_one():
    """Последний слайд переполнился: сдвигать некого, но страниц больше, чем слайдов."""
    from typst_deck.render import overflowing_slide

    deck = _deck_of(3)
    ids = [s.id for s in deck.slides]
    positions = [{"slide": ids[i], "page": i + 1} for i in range(3)]
    assert overflowing_slide(deck, positions, pages=4) == 3


def test_overflowing_slide_none_when_layout_is_sane():
    from typst_deck.render import overflowing_slide

    deck = _deck_of(3)
    ids = [s.id for s in deck.slides]
    positions = [{"slide": ids[i], "page": i + 1} for i in range(3)]
    assert overflowing_slide(deck, positions, pages=3) is None


def test_overflowing_slide_skips_slides_without_fields():
    """У слайда может не быть размеченных полей — судить по нему нельзя, но и падать незачем."""
    from typst_deck.render import overflowing_slide

    deck = _deck_of(3)
    ids = [s.id for s in deck.slides]
    positions = [{"slide": ids[0], "page": 1}, {"slide": ids[2], "page": 4}]
    assert overflowing_slide(deck, positions) == 1


def test_overflowing_slide_unattributable_returns_none():
    from typst_deck.render import overflowing_slide

    deck = _deck_of(2)
    assert overflowing_slide(deck, [], pages=3) is None


def test_render_typ_passes_author_and_department():
    from typst_deck.model import Deck
    from typst_deck.render import render_typ

    deck = Deck(slides=[{"type": "title", "title": "Итоги", "subtitle": "Q3",
                         "author": "Сергей Витвицкий", "department": "ПК Данные и аналитика"}])
    typ, _ = render_typ(deck, set())
    assert "author:" in typ and "department:" in typ
    assert "Сергей Витвицкий" in typ and "ПК Данные и аналитика" in typ


def test_render_typ_omits_empty_author():
    from typst_deck.model import Deck
    from typst_deck.render import render_typ

    typ, _ = render_typ(Deck(slides=[{"type": "title", "title": "Итоги"}]), set())
    assert "author: none" in typ and "department: none" in typ
