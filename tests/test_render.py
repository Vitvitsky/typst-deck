from pathlib import Path

import pytest
from PIL import Image

from tests.conftest import TEMPLATE_DIR, requires_typst
from typst_deck.model import Deck
from typst_deck.render import CompileError, inside_template, render_typ, rasterize_svg, typ_str, typ_value

GOLDEN = Path(__file__).parent / "golden" / "full.typ"


def rich_deck():
    from typst_deck.model import Deck

    return Deck(id="d1", title="Т", slides=[
        {"id": "s1", "type": "agenda", "items": ["Раз", "Два", "Три"]},
        {"id": "s2", "type": "columns", "title": "Блоки",
         "blocks": [{"heading": "Первый", "text": "текст"}, {"text": "второй"}]},
        {"id": "s3", "type": "comparison", "title": "Было и стало",
         "left": {"heading": "Было", "bullets": ["раз"]}, "right": {"heading": "Стало", "bullets": ["два"]}},
        {"id": "s4", "type": "quote", "text": "Мысль", "author": "Автор"},
        {"id": "s5", "type": "metrics", "title": "Числа",
         "items": [{"value": "12,5 млн", "label": "выручка", "delta": "+12 %"},
                   {"value": "3", "label": "провалы", "delta": "-2 п. п."},
                   {"value": "7", "label": "ровно"}]},
        {"id": "s6", "type": "table", "title": "Таблица",
         "header": ["Регион", "Выручка"], "rows": [["Центр", "42"], ["Север", "17,5 %"]]},
        {"id": "s7", "type": "gallery", "title": "Галерея",
         "images": [{"image": "a1.png", "caption": "раз"}, {"image": "a2.png"}]},
        {"id": "s8", "type": "video", "title": "Ролик", "video": "a3.mp4", "poster": "a1.png"},
        {"id": "s9", "type": "video", "title": "Ссылка", "url": "https://v/1"},
        {"id": "s10", "type": "dual-chart", "title": "Два графика",
         "left": {"caption": "Прибыль", "kind": "line", "labels": ["Q1", "Q2"], "series": [{"name": "Выручка", "values": [10, 20]}]},
         "right": {"caption": "Затраты", "kind": "bar", "labels": ["Q1", "Q2"], "series": [{"name": "Расходы", "values": [5, 8]}]}},
    ])


def test_new_types_are_rendered_once_each():
    typ, _ = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    for name in ("agenda", "columns", "comparison", "quote", "metrics", "table", "gallery", "video", "dual-chart"):
        assert f"\n#slide-{name}(" in typ
    assert typ.count("\n#slide-") == 10


def test_composite_fields_are_marked_by_top_level_name():
    typ, _ = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    assert 'field("s2", "blocks", "Первый")' in typ and 'field("s2", "blocks", "текст")' in typ
    assert 'field("s3", "left", "Было")' in typ and 'field("s3", "right", "два")' in typ
    assert 'field("s5", "items", "12,5 млн")' in typ
    assert 'field("s6", "header", "Регион")' in typ and 'field("s6", "rows", "42")' in typ
    assert 'field("s4", "text", "Мысль")' in typ and 'field("s4", "author", "Автор")' in typ
    assert 'field("s10", "left", "Прибыль")' in typ and 'field("s10", "right", "Затраты")' in typ


def test_dual_chart_has_both_sides_with_kinds():
    """Двойной график содержит обе стороны с их видами и маркированными подписями."""
    typ, _ = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    assert "\n#slide-dual-chart(" in typ
    assert 'kind: "line"' in typ and 'kind: "bar"' in typ
    assert 'field("s10", "left", "Прибыль")' in typ and 'field("s10", "right", "Затраты")' in typ


def test_product_computes_trend_and_numeric():
    typ, _ = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    assert 'trend: "up"' in typ and 'trend: "down"' in typ and "trend: none" in typ
    assert "numeric: (false, true,)" in typ, "числовая колонка выравнивается вправо"


def test_numeric_detects_only_true_numbers_not_dates():
    """Числовая колонка не путается с датой: «2026-09-13» числом не считается."""
    from typst_deck.render import _numeric

    # Столбцы (текст, число): текстовой не должно быть числовыми, числовой - должно
    header = ["Регион", "Выручка"]

    # Текстовые значения: некоторые выглядят как цифры, но не числа
    text_rows = [["Центр", "Q1"], ["Север", "н/д"], ["Восток", "2026-09-13"]]
    assert _numeric(header, text_rows) == [False, False]

    # Числовые значения
    numeric_rows = [["Центр", "17,5 %"], ["Север", "-2"], ["Восток", "1 200"], ["Запад", "42 млн"]]
    assert _numeric(header, numeric_rows) == [False, True]


def test_video_link_and_poster():
    typ, warnings = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"}, base_url="http://t")
    assert 'url: "http://t/api/decks/d1/assets/a3.mp4"' in typ  # файл превращается в ссылку
    assert 'url: "https://v/1"' in typ
    assert 'field("s8", "poster", image("/assets/a1.png"' in typ
    assert warnings == []
    typ, warnings = render_typ(rich_deck(), assets={"a1.png", "a2.png", "a3.mp4"})
    assert "url: none" in typ, "без base_url ссылку собрать не из чего"
    assert warnings == [], "файл на месте — предупреждать не о чем"
    typ, warnings = render_typ(rich_deck(), assets={"a1.png", "a2.png"}, base_url="http://t")
    assert "url: none" in typ and any("a3.mp4" in w for w in warnings)


def test_gallery_skips_missing_pictures_with_a_warning():
    typ, warnings = render_typ(rich_deck(), assets={"a1.png", "a3.mp4"})
    assert typ.count('field("s7", "images"') >= 1
    assert any("a2.png" in w for w in warnings)


def full_deck():
    return Deck(id="deck00000001", title="Полная", slides=[
        {"id": "s000001", "type": "title", "title": "Итоги", "subtitle": "Q3 2026"},
        {"id": "s000002", "type": "section", "title": "Финансы"},
        {"id": "s000003", "type": "image", "title": "Рост", "bullets": ["Первый", "Второй"],
         "image": "a000001.png", "image_size": "large", "caption": "Рис. 1"},
        {"id": "s000004", "type": "chart", "title": "Динамика", "kind": "line", "labels": ["Q1", "Q2"],
         "series": [{"name": "Выручка", "values": [1, 2]}], "bullets": ["Рост"]},
        {"id": "s000005", "type": "final", "contact": "team@corp"},
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
    assert typ.count("\n#slide-") == 5


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


def _stub_run(monkeypatch):
    """Подменяет render._run: запоминает переданную команду и останавливает сборку до её выполнения."""
    import typst_deck.render as render

    class Stop(Exception):
        pass

    seen = []

    def fake_run(cmd, timeout):
        seen.append(cmd)
        raise Stop

    monkeypatch.setattr(render, "_run", fake_run)
    return seen, Stop


def test_compile_deck_takes_fonts_from_the_given_dir(deck_dir, tmp_path, monkeypatch):
    """Каталог шрифтов приходит из template.json шаблона, а не всегда <шаблон>/fonts."""
    import typst_deck.render as render

    seen, Stop = _stub_run(monkeypatch)
    fonts = tmp_path / "typst-deck" / "fonts"
    fonts.mkdir(parents=True)
    with pytest.raises(Stop):
        render.compile_deck(Deck(slides=[{"type": "final"}]), deck_dir, TEMPLATE_DIR, fonts_dir=fonts)
    assert seen[0][seen[0].index("--font-path") + 1] == str(fonts)


def test_compile_pdf_takes_fonts_from_the_given_dir(tmp_path, monkeypatch):
    import typst_deck.render as render

    seen, Stop = _stub_run(monkeypatch)
    build = tmp_path / "build"
    build.mkdir()
    (build / "deck.typ").write_text("")
    fonts = tmp_path / "f"
    fonts.mkdir()
    with pytest.raises(Stop):
        render.compile_pdf(build, fonts_dir=fonts)
    assert seen[0][seen[0].index("--font-path") + 1] == str(fonts)


def test_resolve_fonts(tmp_path):
    from typst_deck.render import resolve_fonts

    (tmp_path / "fonts").mkdir()
    (tmp_path / "typst-deck" / "fonts").mkdir(parents=True)
    assert resolve_fonts(tmp_path) == tmp_path / "fonts"
    assert resolve_fonts(tmp_path, "typst-deck/fonts") == tmp_path / "typst-deck" / "fonts"
    assert resolve_fonts(tmp_path, "nope") is None
    for bad in ("../outside", "/abs", "", 5):
        with pytest.raises(ValueError):
            resolve_fonts(tmp_path, bad)


def test_inside_template_keeps_paths_inside(tmp_path):
    assert inside_template(tmp_path, "typst-deck/pptx.json", "pptx") == tmp_path / "typst-deck/pptx.json"
    for bad in ("../x.json", "/etc/x.json", "", None, 5):
        with pytest.raises(ValueError, match=r"pptx=.*путь должен вести внутрь шаблона"):
            inside_template(tmp_path, bad, "pptx")


def test_resolve_fonts_message_is_unchanged(tmp_path):
    from typst_deck.render import resolve_fonts

    with pytest.raises(ValueError, match=r"^fonts='\.\./x': путь должен вести внутрь шаблона$"):
        resolve_fonts(tmp_path, "../x")


@requires_typst
def test_rasterize_svg_keeps_proportions(tmp_path):
    svg = tmp_path / "vec.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">'
                   '<rect width="300" height="100" fill="#00FFE0"/></svg>')
    out = rasterize_svg(svg, tmp_path / "vec.png")
    with Image.open(out) as im:
        assert im.format == "PNG" and abs(im.width / im.height - 3) < 0.05


@requires_typst
def test_rasterize_broken_svg_is_a_compile_error(tmp_path):
    svg = tmp_path / "bad.svg"
    svg.write_text("<svg")
    with pytest.raises(CompileError):
        rasterize_svg(svg, tmp_path / "bad.png")
