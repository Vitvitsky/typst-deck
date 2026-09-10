import json

import pytest

from tests.conftest import TEMPLATE_DIR, requires_typst
from tests.test_render import full_deck
from typst_deck.model import Deck
from typst_deck.render import CompileError, compile_deck

pytestmark = requires_typst


def test_compile_full_deck(deck_dir, png_bytes):
    (deck_dir / "assets" / "a000001.png").write_bytes(png_bytes)
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 6  # PDF теперь ленивый, см. test_compile_does_not_build_pdf
    assert r.warnings == []
    fields = {(p["slide"], p["field"]) for p in r.positions}
    assert ("s000001", "title") in fields and ("s000003", "bullets") in fields
    assert ("s000003", "image") in fields and ("s000006", "contact") in fields
    p = next(p for p in r.positions if p["slide"] == "s000003" and p["field"] == "title")
    assert p["page"] == 3 and p["w"] > 0 and p["h"] > 0
    assert json.loads((deck_dir / "build" / "positions.json").read_text()) == r.positions
    assert (deck_dir / "build" / "template").is_symlink()


def test_compile_missing_image_is_warning(deck_dir):
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 6 and r.warnings


def test_compile_replaces_previous_build(deck_dir):
    compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    r = compile_deck(Deck(slides=[{"type": "final"}]), deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 1
    assert not (deck_dir / "build" / "slide-2.svg").exists()
    assert not (deck_dir / "build.tmp").exists()


def test_compile_error_surfaces_stderr(deck_dir, tmp_path):
    bad_tpl = tmp_path / "tpl"
    bad_tpl.mkdir()
    (bad_tpl / "deck.typ").write_text("#let deck(title: none, body) = body\n")
    with pytest.raises(CompileError) as e:
        compile_deck(full_deck(), deck_dir, bad_tpl)
    assert "slide-title" in e.value.stderr


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_every_template_honours_contract(deck_dir, png_bytes, tid):
    """Каждый шаблон в templates/ собирает образец: 6 страниц и позиции полей."""
    from typst_deck.templates import SAMPLE_DECK
    (deck_dir / "assets" / "a000001.png").write_bytes(png_bytes)
    deck = SAMPLE_DECK.model_copy(deep=True)
    deck.slides[2].image = "a000001.png"
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 6
    fields = {(p["slide"], p["field"]) for p in r.positions}
    assert ("s000001", "title") in fields and ("s000003", "bullets") in fields and ("s000006", "title") in fields


def test_compile_reports_per_command_timings(deck_dir):
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert set(r.timings) == {"svg_ms", "query_ms", "ms"}
    assert all(isinstance(v, int) and v >= 0 for v in r.timings.values())
    assert r.timings["ms"] >= max(r.timings["svg_ms"], r.timings["query_ms"])


def test_compile_logs_render_done(deck_dir, caplog):
    caplog.set_level("INFO", logger="typst_deck.render")
    deck = full_deck()
    compile_deck(deck, deck_dir, TEMPLATE_DIR)
    rec = next(r for r in caplog.records if r.msg == "render.done")
    assert rec.fields["deck"] == deck.id
    assert rec.fields["slides"] == 6
    assert rec.fields["svg_kb"] > 0
    assert rec.fields["ms"] >= 0


def test_compile_hashes_each_page(deck_dir):
    import json as _json

    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert len(r.pages) == 6
    assert all(isinstance(h, str) and h for h in r.pages)
    assert len(set(r.pages)) == 6, "разные слайды — разные хеши"
    assert _json.loads((deck_dir / "build" / "pages.json").read_text()) == r.pages


def test_page_hash_changes_only_for_edited_slide(deck_dir):
    before = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR).pages
    deck = full_deck()
    deck.slides[2].title = "Совсем другой заголовок"
    after = compile_deck(deck, deck_dir, TEMPLATE_DIR).pages
    assert after[2] != before[2], "правленый слайд обязан сменить хеш"
    assert [after[i] for i in (0, 1, 3, 4, 5)] == [before[i] for i in (0, 1, 3, 4, 5)], \
        "остальные слайды должны остаться под теми же URL"


def test_compile_does_not_build_pdf(deck_dir):
    """PDF нужен раз в конце, а собирался на каждую правку — 161 мс из 341."""
    r = compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    assert not (deck_dir / "build" / "deck.pdf").exists()
    assert len(r.svgs) == 6
    assert (deck_dir / "build" / "deck.typ").exists(), "исходник нужен, чтобы собрать PDF потом"
    assert (deck_dir / "build" / "template").is_symlink()
    assert "pdf_ms" not in r.timings


def test_compile_pdf_builds_from_existing_build(deck_dir):
    from typst_deck.render import compile_pdf

    compile_deck(full_deck(), deck_dir, TEMPLATE_DIR)
    pdf = compile_pdf(deck_dir / "build")
    assert pdf.exists() and pdf.read_bytes()[:5] == b"%PDF-"


def test_compile_pdf_without_build_is_error(deck_dir):
    from typst_deck.render import CompileError, compile_pdf

    (deck_dir / "build").mkdir(parents=True)
    with pytest.raises(CompileError):
        compile_pdf(deck_dir / "build")


def _template_without_clip(tmp_path):
    """Шаблон без защитной обрезки: титульный слайд переливается на вторую страницу.
    Ровно так ведёт себя корпоративный адаптер Lemana Tech, у которого clip есть только на
    содержательных слайдах."""
    d = tmp_path / "leaky"
    d.mkdir()
    (d / "deck.typ").write_text("""
#let deck(title: none, body) = {
  set page(width: 16cm, height: 9cm, margin: 1cm)
  set text(size: 11pt, lang: "ru")
  body
}
#let slide-title(title: none, subtitle: none, author: none, department: none) = page[#title #linebreak() #subtitle]
#let slide-section(title: none, subtitle: none) = page[#title]
#let slide-image(title: none, bullets: none, image: none, image-size: none, caption: none) = page[#title]
#let slide-bar-chart(title: none, data: none, unit: none, bullets: none) = page[#title]
#let slide-chart(title: none, labels: none, series: none, unit: none, bullets: none) = page[#title]
#let slide-final(title: none, contact: none) = page[#title]
""", encoding="utf-8")
    return d


def test_overflow_names_the_slide_and_blames_content(deck_dir, tmp_path):
    from typst_deck.model import Deck

    tpl = _template_without_clip(tmp_path)
    deck = Deck(slides=[
        {"type": "title", "title": "Титул", "subtitle": "A" + "\n" * 40 + "B"},
        {"type": "section", "title": "Раздел"},
        {"type": "final"},
    ])
    with pytest.raises(CompileError) as e:
        compile_deck(deck, deck_dir, tpl)
    msg = str(e.value)
    assert "слайд 1" in msg, msg
    assert "не помещается" in msg or "не поместил" in msg, msg
    assert "нарушает контракт" not in msg, "шаблон тут ни при чём — виновато содержимое"


def test_overflow_message_falls_back_when_culprit_unknown(deck_dir, tmp_path):
    """Если виновника определить нельзя, остаёмся на прежней формулировке про контракт."""
    from typst_deck.render import overflowing_slide
    from typst_deck.model import Deck

    assert overflowing_slide(Deck(slides=[{"type": "final"}]), [], pages=2) is None


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_every_template_accepts_author_and_department(deck_dir, tid):
    """Контракт шаблона расширен: slide-title обязан принимать автора и департамент."""
    from typst_deck.model import Deck

    deck = Deck(slides=[{"type": "title", "title": "Итоги квартала", "subtitle": "Q3 2026",
                         "author": "Сергей Витвицкий", "department": "ПК Данные и аналитика"}])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 1


def test_default_template_accepts_author_and_department(deck_dir):
    from typst_deck.model import Deck

    deck = Deck(slides=[{"type": "title", "title": "Итоги квартала", "subtitle": "Q3 2026",
                         "author": "Сергей Витвицкий", "department": "ПК Данные и аналитика"}])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR)
    assert len(r.svgs) == 1


OVERSIZED = "Очень длинный текст, который заведомо не помещается в отведённое место " * 6


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_template_survives_oversized_title_slide(deck_dir, tid):
    """Контракт «одна функция — одна страница» обязан держаться при любом входе:
    переполнение обрезается, а не переливается на вторую страницу."""
    from typst_deck.model import Deck

    deck = Deck(slides=[{"type": "title", "title": OVERSIZED[:120], "subtitle": OVERSIZED[:120],
                         "author": OVERSIZED[:120], "department": OVERSIZED[:120]}])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 1


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_template_survives_oversized_section_slide(deck_dir, tid):
    from typst_deck.model import Deck

    deck = Deck(slides=[{"type": "section", "title": OVERSIZED[:120], "subtitle": OVERSIZED[:120]}])
    r = compile_deck(deck, deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert len(r.svgs) == 1


def _title_deck():
    from typst_deck.model import Deck

    return Deck(slides=[{"type": "title", "title": "Итоги квартала", "subtitle": "Q3 2026",
                         "author": "Сергей Витвицкий", "department": "ПК Данные и аналитика"}])


def _y_of(positions, field):
    return next(p["y"] for p in positions if p["field"] == field)


@pytest.mark.parametrize("tid", sorted(p.name for p in (TEMPLATE_DIR.parent / "templates").iterdir() if (p / "deck.typ").exists()))
def test_author_is_printed_above_department(deck_dir, tid):
    """Порядок подписи: сначала человек, потом подразделение."""
    r = compile_deck(_title_deck(), deck_dir, TEMPLATE_DIR.parent / "templates" / tid)
    assert _y_of(r.positions, "author") < _y_of(r.positions, "department")


def test_author_above_department_in_default_template(deck_dir):
    r = compile_deck(_title_deck(), deck_dir, TEMPLATE_DIR)
    assert _y_of(r.positions, "author") < _y_of(r.positions, "department")


MM = 2.83465  # мм в пунктах: зоны в шаблонах заданы в мм, positions отдаёт пункты
LONG_TITLE = ("Итоги квартала по направлению данных и аналитики и планы полугодия " * 2)[:120]


def _field(positions, name):
    return next(p for p in positions if p["field"] == name)


def test_long_title_shrinks_into_its_zone(deck_dir):
    """Автокегль: длинный заголовок укладывается в зону, а не растёт пропорционально длине.

    Замер 2026-09-10 на этом шаблоне: короткий заголовок 21.3 pt, длинный
    без автокегля — 258.1 pt при зоне 68.0 pt. Лесенка из трёх размеров
    (28/22/17pt) из плана не укладывала его в зону даже на последней ступени
    (84.8 pt) — добавлена четвёртая, 14pt, с которой автокегль даёт 50.1 pt.
    """
    short = compile_deck(Deck(slides=[{"type": "title", "title": "Итоги"}]), deck_dir, TEMPLATE_DIR)
    one_line = _field(short.positions, "title")["h"]
    long_ = compile_deck(Deck(slides=[{"type": "title", "title": LONG_TITLE}]), deck_dir, TEMPLATE_DIR)
    h = _field(long_.positions, "title")["h"]
    assert h > one_line        # длиннее одной строки — иначе тест ничего не проверяет
    assert h <= 24 * MM        # но в зону 2.4cm укладывается
    assert len([p for p in long_.positions if p["field"] == "title"]) == 1  # measure не задвоил маркер


@pytest.mark.parametrize("tdir", [TEMPLATE_DIR, TEMPLATE_DIR.parent / "templates" / "dark"], ids=["default", "dark"])
def test_long_section_title_shrinks_into_its_zone(deck_dir, tdir):
    """Автокегль разделительного слайда: длинный заголовок укладывается в зону 2.4cm.

    Замер 2026-09-10, default и dark одинаково: короткий заголовок 19.8 pt,
    длинный без автокегля — 239.7 pt при зоне 68.0 pt. Лесенка 26/20/16pt не
    укладывала его и на последней ступени (79.8 pt) — добавлена 14pt, как у
    титульного слайда, с ней 50.1 pt.
    """
    short = compile_deck(Deck(slides=[{"type": "section", "title": "Итоги"}]), deck_dir, tdir)
    one_line = _field(short.positions, "title")["h"]
    long_ = compile_deck(Deck(slides=[{"type": "section", "title": LONG_TITLE, "subtitle": LONG_TITLE}]),
                         deck_dir, tdir)
    h = _field(long_.positions, "title")["h"]
    assert h > one_line        # длиннее одной строки — иначе тест ничего не проверяет
    assert h <= 24 * MM        # но в зону 2.4cm укладывается
    assert len([p for p in long_.positions if p["field"] == "title"]) == 1  # measure не задвоил маркер
    assert len(long_.svgs) == 1
