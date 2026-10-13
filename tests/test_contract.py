import shutil
from pathlib import Path

import pytest

from tests.conftest import (FALLBACK_FONT, MISSING_FONT, NO_CLIP_FINAL, NO_CONTACT, ROOT, TEMPLATE_DIR, TWO_PAGES,
                            make_pptx_template, make_template, requires_typst)
from typst_deck.contract import check_template, filled_slide, missing_fonts
from typst_deck.model import Deck

DEJAVU = Path("/usr/share/fonts/truetype/dejavu")
needs_dejavu = pytest.mark.skipif(not (DEJAVU / "DejaVuSans.ttf").exists(), reason="нет файлов DejaVu")


@requires_typst
@pytest.mark.parametrize("tdir", [TEMPLATE_DIR, ROOT / "templates" / "dark"], ids=["default", "dark"])
def test_reference_templates_pass_the_full_contract(tdir, tmp_path):
    rep = check_template(tdir, "typst", tmp_path)
    assert rep.errors == [] and rep.warnings == []


@requires_typst
@pytest.mark.parametrize("tdir", [TEMPLATE_DIR, ROOT / "templates" / "dark"], ids=["default", "dark"])
def test_sample_covers_every_type(tdir, tmp_path):
    from typst_deck.contract import SAMPLE_DECK
    from typst_deck.model import SLIDE_TYPES

    assert [s.type for s in SAMPLE_DECK.slides] == list(SLIDE_TYPES)
    assert check_template(tdir, "typst", tmp_path / tdir.name).errors == []


def test_sample_assets_are_written_next_to_the_deck(tmp_path):
    from typst_deck.contract import SAMPLE_ASSETS, write_sample_assets

    write_sample_assets(tmp_path / "deck")
    for name in SAMPLE_ASSETS:
        assert (tmp_path / "deck" / "assets" / name).is_file()


@requires_typst
def test_oversized_rule_covers_new_fields(tmp_path):
    """Правило 3 перебирает цитату, блоки, метрики и ячейки таблицы."""
    d = make_template(tmp_path, "quote-overflow", deck_edit=(
        "#let slide-quote(text: none, author: none) = slide[",
        "#let slide-quote(text: none, author: none) = page[",
    ))
    errors = check_template(d, "typst", tmp_path / "w").errors
    assert any("переросший текст" in e for e in errors)


@requires_typst
def test_missing_template_json_is_an_error(tmp_path):
    d = make_template(tmp_path, "nojson")
    (d / "template.json").unlink()
    assert any("template.json" in e for e in check_template(d, "typst", tmp_path / "w").errors)


@requires_typst
def test_inapplicable_slots_key_is_an_error_in_full_mode_and_a_warning_at_start(tmp_path):
    d = make_template(tmp_path, "badslots", meta={"name": "Б", "slots": {"title": {"title": {"count": 3}}}})
    full = check_template(d, "typst", tmp_path / "w1")
    start = check_template(d, "typst", tmp_path / "w2", full=False)
    assert any(e.startswith("slots:") for e in full.errors)
    assert start.errors == [] and any(w.startswith("slots:") for w in start.warnings)


@requires_typst
def test_bad_fonts_value_is_an_error_in_full_mode_and_a_warning_at_start(tmp_path):
    """resolve_fonts бросает ValueError на путь наружу шаблона. Реестр в этом же случае
    не падает, а откатывается на fonts/ (templates.py _info) и сервис продолжает отдавать
    шаблон — стартовый режим не должен ломаться там, где сервис не ломается."""
    d = make_template(tmp_path, "badfonts", meta={"name": "Ф", "fonts": "../elsewhere"})
    full = check_template(d, "typst", tmp_path / "w1")
    start = check_template(d, "typst", tmp_path / "w2", full=False)
    assert any("fonts" in e for e in full.errors), full.errors
    assert start.errors == [] and any("fonts" in w for w in start.warnings), start.warnings


@requires_typst
def test_bad_fonts_value_at_start_does_not_stop_the_check(tmp_path):
    """Стартовый режим откатывается на fonts/ и проверяет дальше: правило 2 по-прежнему
    ловит двойную страницу, а не молчит из-за раннего возврата на плохом fonts."""
    d = make_template(tmp_path, "badfontstwopages", deck_edit=TWO_PAGES,
                      meta={"name": "Ф", "fonts": "../elsewhere"})
    start = check_template(d, "typst", tmp_path / "w", full=False)
    assert any("образец не собирается" in e for e in start.errors), start.errors


@requires_typst
def test_extra_page_per_slide_is_an_error(tmp_path):
    d = make_template(tmp_path, "twopages", deck_edit=TWO_PAGES)
    assert any("образец не собирается" in e for e in check_template(d, "typst", tmp_path / "w").errors)


@requires_typst
def test_overflow_on_oversized_or_declared_text_is_an_error(tmp_path):
    """Правила 3 и 5: финальный слайд без обрезки переливается на вторую страницу."""
    d = make_template(tmp_path, "overflow", deck_edit=NO_CLIP_FINAL,
                      meta={"name": "П", "slots": {"final": {"title": {"max": 120},
                                                            "contact": {"max": 120, "lines": 30}}}})
    errors = check_template(d, "typst", tmp_path / "w").errors
    assert any("переросший текст" in e for e in errors), errors
    assert any("по объявленным пределам" in e for e in errors), errors


@requires_typst
def test_unmarked_field_is_an_error(tmp_path):
    d = make_template(tmp_path, "nocontact", deck_edit=NO_CONTACT)
    errors = check_template(d, "typst", tmp_path / "w").errors
    assert any("contact" in e and "не размечено" in e for e in errors), errors


@requires_typst
@needs_dejavu
def test_unused_fonts_dir_is_an_error_in_full_mode_and_a_warning_at_start(tmp_path):
    """Каталог шрифтов есть, а шаблон называет другое семейство — случай «…Pro Trl»."""
    d = make_template(tmp_path, "unused", meta={"name": "Н", "fonts": "fonts"})
    (d / "fonts").mkdir()
    shutil.copy(DEJAVU / "DejaVuSansMono.ttf", d / "fonts")
    full = check_template(d, "typst", tmp_path / "w1")
    start = check_template(d, "typst", tmp_path / "w2", full=False)
    assert any("не используются" in e for e in full.errors), full.errors
    assert start.errors == [] and any("не используются" in w for w in start.warnings)


@requires_typst
@needs_dejavu
def test_used_fonts_dir_passes(tmp_path):
    d = make_template(tmp_path, "used", meta={"name": "И", "fonts": "fonts"})
    (d / "fonts").mkdir()
    shutil.copy(DEJAVU / "DejaVuSans.ttf", d / "fonts")
    assert check_template(d, "typst", tmp_path / "w").errors == []


@requires_typst
def test_fallback_family_is_silent_when_the_first_is_found(tmp_path):
    """typst предупреждает о каждом ненайденном запасном семействе, даже когда первое
    нашлось: такой шум топил в /api/health настоящую беду со шрифтом."""
    d = make_template(tmp_path, "fallback", deck_edit=FALLBACK_FONT)
    rep = check_template(d, "typst", tmp_path / "w")
    assert rep.errors == []
    assert not any("нет такого шрифта" in w.lower() for w in rep.warnings), rep.warnings


@requires_typst
def test_missing_first_family_is_only_a_warning(tmp_path):
    d = make_template(tmp_path, "missing", deck_edit=MISSING_FONT)
    rep = check_template(d, "typst", tmp_path / "w")
    assert rep.errors == []
    assert any("нет такого шрифта" in w.lower() for w in rep.warnings), rep.warnings


STDERR = """warning: unknown font family: nope font
  ┌─ a.typ:1:16
  │
1 │   #set text(font: ("DejaVu Sans", "Nope Font",
  │ ╭─────────────────^
2 │ │   "Liberation Sans"))
  │ ╰────────────────────^

warning: unknown font family: liberation sans
  ┌─ a.typ:1:16
  │
1 │   #set text(font: ("DejaVu Sans", "Nope Font",
  │ ╭─────────────────^
2 │ │   "Liberation Sans"))
  │ ╰────────────────────^

warning: unknown font family: absent one
  ┌─ a.typ:4:12
  │
4 │ #text(font: "Absent One")[x]
  │             ^^^^^^^^^^^^

warning: unknown font family: tt interphases pro
  ┌─ deck.typ:3:16
  │
3 │ #set text(font: ("TT Interphases Pro", "Liberation Sans"))
  │                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

warning: unknown font family: liberation sans
  ┌─ deck.typ:3:16
  │
3 │ #set text(font: ("TT Interphases Pro", "Liberation Sans"))
  │                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""


def test_missing_fonts_drops_fallbacks_of_a_found_family():
    # DejaVu найден — его запасные молчат; во второй цепочке первого нет, и её
    # Liberation Sans — уже не шум: текст там уйдёт в шрифт по умолчанию
    assert missing_fonts(STDERR) == ["absent one", "liberation sans", "tt interphases pro"]


def test_missing_fonts_reads_chains_kept_in_variables():
    # у Lemana цепочка в переменной: под предупреждением typst видно лишь «font: body-font»
    stderr = "".join(f"""warning: unknown font family: {f}
    ┌─ template/slides_template.typ:127:18
    │
127 │             font: body-font
    │                   ^^^^^^^^^

""" for f in ("tt interphases pro trl", "liberation sans"))
    src = '#let body-font = ("TT Interphases Pro", "TT Interphases Pro Trl", "Liberation Sans")'
    assert missing_fonts(stderr, src) == []
    assert missing_fonts(stderr) == ["liberation sans", "tt interphases pro trl"]


def test_missing_fonts_judges_each_place_on_its_own():
    """Семейство — запасное в одной цепочке и единственное в другом месте: молчит
    только там, где за ним стоит найденное первое."""
    stderr = """warning: unknown font family: nope fallback
  ┌─ a.typ:1:16
  │
1 │ #set text(font: ("DejaVu Sans", "Nope Fallback"))
  │                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

warning: unknown font family: nope fallback
  ┌─ a.typ:3:12
  │
3 │ #text(font: "Nope Fallback")[World]
  │             ^^^^^^^^^^^^^^^
"""
    assert missing_fonts(stderr) == ["nope fallback"]


def test_missing_fonts_keeps_a_warning_without_a_readable_chain():
    assert missing_fonts("warning: unknown font family: x\n") == ["x"]


@requires_typst
def test_cli_checks_one_template_directory(tmp_path, capsys):
    from typst_deck.templates import main

    assert main([str(TEMPLATE_DIR)]) == 0
    assert "контракт соблюдён" in capsys.readouterr().out
    broken = make_template(tmp_path, "twopages", deck_edit=TWO_PAGES)
    assert main([str(broken)]) == 1


def test_filled_slide_respects_limits():
    s = filled_slide("title", {"title": {"max": 70, "lines": 2}, "subtitle": {"max": 65, "lines": 1}})
    assert len(s["title"]) == 70 and s["title"].count("\n") == 1
    assert len(s["subtitle"]) == 65 and "\n" not in s["subtitle"]
    c = filled_slide("chart", {"bullets": {"count": 4, "max": 120}, "labels": {"count": 5}})
    assert len(c["bullets"]) == 4 and all(len(b) == 120 for b in c["bullets"])
    assert all(len(sr["values"]) == len(c["labels"]) == 5 for sr in c["series"])
    t = filled_slide("table", {"header": {"count": 4}, "rows": {"count": 3}})
    assert len(t["header"]) == 4 and len(t["rows"]) == 3 and all(len(row) == 4 for row in t["rows"])
    Deck(slides=[s, c, t, filled_slide("final", {})])


def test_filled_slide_puts_a_dotted_limit_into_the_nested_field():
    """Пределы по пути через точку (спека §6) ложатся во вложенное поле, а не в поле
    с точкой в имени: у модели extra="forbid", и слайд с ключом «blocks.text» не собрать."""
    s = filled_slide("columns", {"blocks": {"count": 3}, "blocks.text": {"max": 180}})
    assert "blocks.text" not in s
    assert len(s["blocks"]) == 3 and all(len(b["text"]) == 180 for b in s["blocks"])
    c = filled_slide("comparison", {"left.bullets": {"count": 2, "max": 100}})
    assert len(c["left"]["bullets"]) == 2 and all(len(b) == 100 for b in c["left"]["bullets"])
    Deck(slides=[s, c])


def test_filled_slide_takes_the_declared_volume_not_the_global_one():
    """Шаблон, честно сузивший blocks.text до 180, проверяется на 180, а не на 300:
    иначе правило 5 валит его за содержимое, которого он не обещал."""
    narrow = filled_slide("columns", {"blocks.text": {"max": 180}})
    assert all(len(b["text"]) == 180 for b in narrow["blocks"])
    assert all(len(b["text"]) == 300 for b in filled_slide("columns", {})["blocks"])
    side = filled_slide("comparison", {"right.bullets": {"max": 60}})
    assert all(len(b) == 60 for b in side["right"]["bullets"])
    assert all(len(b) == 120 for b in filled_slide("comparison", {})["left"]["bullets"])


@requires_typst
def test_rule_five_understands_nested_slot_limits(tmp_path):
    """Воспроизведение из ревью: пример slots дословно из спеки §6 не собирался вовсе."""
    d = make_template(tmp_path, "nested", meta={"name": "В", "slots": {
        "columns": {"blocks": {"count": 3}, "blocks.text": {"max": 180}},
        "comparison": {"left.bullets": {"count": 3, "max": 100}}}})
    rep = check_template(d, "typst", tmp_path / "w")
    assert rep.errors == [], rep.errors


def test_gallery_at_four_pictures_goes_round_the_sample_images():
    """Галерея допускает четыре картинки, а образец даёт три: самый тугой случай
    правило 5 обязано проверять, а не срезать до трёх."""
    from typst_deck.contract import SAMPLE_IMAGES

    s = filled_slide("gallery", {"images": {"count": 4}})
    assert len(s["images"]) == 4
    assert all(p["image"] in SAMPLE_IMAGES for p in s["images"])
    Deck(slides=[s])


def test_filled_slide_is_valid_for_every_type_at_its_declared_limits():
    """Правило 5 собирает Deck() из filled_slide на каждом объявленном типе — она обязана
    быть валидной колодой и без объявления (короткие значения по умолчанию), и с ним.

    Ловит два бага: agenda.items без выделенной ветки превращался в строку (STRING_LISTS
    не знал про items), а gallery.images.count >= 3 выбирал sample.mp4 картинкой (список
    ассетов образца шёл по порядку вставки, ролик — последним)."""
    from typst_deck.model import SLIDE_TYPES

    declared = {"agenda": {"items": {"count": 7, "max": 60}}, "gallery": {"images": {"count": 3}}}
    Deck(slides=[filled_slide(t, declared.get(t, {})) for t in SLIDE_TYPES])


@requires_typst
def test_good_pptx_mapping_passes_the_full_contract(tmp_path):
    rep = check_template(make_pptx_template(tmp_path), "typst", tmp_path / "w")
    assert rep.errors == [] and rep.pptx == []


@requires_typst
def test_broken_pptx_is_an_error_in_full_mode_and_a_warning_at_start(tmp_path):
    d = make_pptx_template(tmp_path, mapping_edit=lambda m: m["slides"]["title"]["ph"].update(author=42))
    full = check_template(d, "typst", tmp_path / "w1")
    start = check_template(d, "typst", tmp_path / "w2", full=False)
    assert any(e.startswith("pptx:") and "idx 42" in e for e in full.errors)
    assert start.errors == [] and start.pptx and any("idx 42" in w for w in start.warnings)


@requires_typst
def test_template_without_pptx_has_no_rule_7_findings(tmp_path):
    assert check_template(TEMPLATE_DIR, "typst", tmp_path).pptx == []
