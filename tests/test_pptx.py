"""Экспорт в PPTX: сопоставление шаблона и сборка файла на синтетическом мастере."""
import io
import re

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.chart import XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Mm

from tests.conftest import make_pptx_template, requires_typst
from typst_deck.contract import SAMPLE_DECK, filled_slide
from typst_deck.model import Deck
from typst_deck.pptx import SLIDE_TYPES, MappingError, export_pptx, load_mapping, open_master

MM = 36000
ZONE = (20, 80, 600, 260)  # body синтетического сопоставления, мм


# --- экспорт

@pytest.fixture
def tdir(tmp_path):
    return make_pptx_template(tmp_path)


def export(tdir, deck, assets=None, warnings=None):
    data = export_pptx(deck, tdir, "pptx.json", assets or tdir / "no-assets", "typst", warnings)
    return Presentation(io.BytesIO(data))


def by_idx(slide) -> dict[int, list[str]]:
    return {sh.placeholder_format.idx: [p.text for p in sh.text_frame.paragraphs] for sh in slide.placeholders}


def pictures(slide):
    return [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE]


def boxes(slide):
    return [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.TEXT_BOX]


def chart_of(slide):
    return next(sh.chart for sh in slide.shapes if sh.has_chart)


def colors(chart, path: str) -> list[str]:
    return [e.get("val") for e in chart._chartSpace.xpath(path)]


def inside(sh, zone=ZONE) -> bool:
    x, y, w, h = (int(v * MM) for v in zone)
    return (sh.left >= x - 1 and sh.top >= y - 1
            and sh.left + sh.width <= x + w + 1 and sh.top + sh.height <= y + h + 1)


def png(path, w=400, h=200):
    Image.new("RGB", (w, h), (255, 222, 0)).save(path)


def image_deck(size="medium", **kw) -> Deck:
    return Deck(slides=[{"type": "image", "title": "Рост", "bullets": ["Тезис"], "image": "pic.png",
                         "image_size": size, "caption": "Подпись", **kw}])


def test_every_type_lands_on_its_layout_at_the_masters_size(tdir):
    prs = export(tdir, SAMPLE_DECK)
    assert [s.slide_layout.name for s in prs.slides] == [
        "Title Slide", "Section Header", "Title and Content", "Title Only", "Title Only", "Title Slide"]
    assert (prs.slide_width, prs.slide_height) == (Mm(677), Mm(381))
    # слайд-образец мастера не пережил экспорт: первый слайд — титул колоды
    assert by_idx(prs.slides[0])[0] == ["Название презентации"]


def test_fields_fill_placeholders_and_share_one_in_model_order(tdir):
    title = by_idx(export(tdir, SAMPLE_DECK).slides[0])
    assert title[1] == ["Подзаголовок и дата"]
    assert title[21] == ["Имя Фамилия", "Подразделение"]


def test_empty_and_unmapped_placeholders_are_removed(tdir):
    deck = Deck(slides=[{"type": "title", "title": "Итоги"}, {"type": "image", "title": "Рост"}])
    prs = export(tdir, deck)
    # ни подзаголовка, ни подписи, ни idx 1 «Title and Content»; дату и колонтитул python-pptx не переносит
    assert set(by_idx(prs.slides[0])) == {0, 12}
    assert set(by_idx(prs.slides[1])) == {0, 12}


def test_slide_number_is_a_field(tdir):
    for n, slide in enumerate(export(tdir, SAMPLE_DECK).slides, 1):
        num = next(sh for sh in slide.placeholders if sh.placeholder_format.idx == 12)
        assert num._element.xpath(".//a:fld[@type='slidenum']"), n
        assert num.text_frame.text == str(n)


def test_titles_shrink_on_edit(tdir):
    for slide in export(tdir, SAMPLE_DECK).slides:
        assert slide.shapes.title._element.xpath(".//a:bodyPr/a:normAutofit")


def test_image_keeps_proportions_inside_the_zone(tdir, tmp_path):
    (tmp_path / "assets").mkdir()
    png(tmp_path / "assets" / "pic.png")
    widths = []
    for size in ("small", "medium", "large"):
        slide = export(tdir, image_deck(size), assets=tmp_path / "assets").slides[0]
        [pic] = pictures(slide)
        text, caption = boxes(slide)
        assert inside(pic) and inside(text) and inside(caption)
        assert abs(pic.width / pic.height - 2) < 0.01
        assert text.left + text.width <= pic.left  # тезисы слева от картинки
        assert caption.top >= pic.top + pic.height and caption.text_frame.text == "Подпись"
        widths.append(pic.width)
    assert widths == sorted(widths) and len(set(widths)) == 3


def test_missing_image_leaves_bullets_the_whole_zone(tdir, tmp_path):
    warnings: list[str] = []
    slide = export(tdir, image_deck(), assets=tmp_path, warnings=warnings).slides[0]
    assert pictures(slide) == [] and "pic.png не найдена" in warnings[0]
    [text] = boxes(slide)
    assert (text.left, text.width) == (int(ZONE[0] * MM), int(ZONE[2] * MM))


@requires_typst
def test_svg_goes_in_as_png(tdir, tmp_path):
    (tmp_path / "vec.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">'
                                      '<rect width="300" height="100" fill="#00FFE0"/></svg>')
    slide = export(tdir, image_deck(image="vec.svg"), assets=tmp_path).slides[0]
    [pic] = pictures(slide)
    assert pic.image.content_type == "image/png" and abs(pic.width / pic.height - 3) < 0.05


def test_bar_colors_follow_the_sign(tdir):
    deck = Deck(slides=[{"type": "bar-chart", "title": "Итоги", "unit": "млн",
                         "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": -17},
                                  {"label": "Юг", "value": 28}]}])
    chart = chart_of(export(tdir, deck).slides[0])
    assert colors(chart, ".//c:dPt//a:srgbClr") == ["FFDE00", "FF2E00", "FFDE00"]
    assert chart._chartSpace.xpath(".//c:invertIfNegative[@val='0']")
    assert chart.plots[0].data_labels.number_format == 'General" млн"'
    assert not chart.has_legend


def test_line_series_cycle_the_palette(tdir):
    deck = Deck(slides=[{"type": "chart", "title": "Итоги", "unit": "млн", "labels": ["Q1", "Q2"],
                         "series": [{"name": f"Ряд {j}", "values": [j, j + 1]} for j in range(4)]}])
    chart = chart_of(export(tdir, deck).slides[0])
    assert colors(chart, ".//c:ser/c:spPr/a:ln//a:srgbClr") == ["FFDE00", "1E1E1E", "00FFE0", "FFDE00"]
    assert chart.legend.position == XL_LEGEND_POSITION.TOP
    assert chart.value_axis.axis_title.text_frame.text == "млн"


def test_chart_takes_the_zone_or_shares_it_with_bullets(tdir):
    base = {"type": "bar-chart", "title": "Итоги", "data": [{"label": "A", "value": 1}]}
    alone, shared = export(tdir, Deck(slides=[base, base | {"bullets": ["Рост"]}])).slides
    frame = next(sh for sh in alone.shapes if sh.has_chart)
    assert (frame.left, frame.top, frame.width, frame.height) == tuple(int(v * MM) for v in ZONE)
    [text] = boxes(shared)
    frame = next(sh for sh in shared.shapes if sh.has_chart)
    assert text.left == int(ZONE[0] * MM) and text.width == int(ZONE[2] * MM * 38 / 100)
    assert frame.left == text.left + text.width + 12 * MM
    heading, bullet = text.text_frame.paragraphs
    assert heading.text == "Выводы" and not heading._p.xpath("./a:pPr/a:buChar")
    assert bullet._p.xpath("./a:pPr/a:buChar[@char='•']")


def test_notes_go_to_speaker_notes(tdir):
    deck = Deck(slides=[{"type": "final", "notes": "Сказать спасибо"}])
    assert export(tdir, deck).slides[0].notes_slide.notes_text_frame.text == "Сказать спасибо"


def test_control_characters_dropped_and_newline_breaks_the_line(tdir):
    deck = Deck(slides=[{"type": "title", "title": "\x0bИтоги\x1f", "subtitle": "первая\nвторая"},
                        {"type": "image", "title": "T", "bullets": ["тезис\nпродолжение"]}])
    prs = export(tdir, deck)
    assert by_idx(prs.slides[0])[0] == ["Итоги"]
    sub = next(sh for sh in prs.slides[0].placeholders if sh.placeholder_format.idx == 1)
    assert len(sub.text_frame.paragraphs) == 1 and sub._element.xpath(".//a:br")
    [text] = boxes(prs.slides[1])
    assert len(text.text_frame.paragraphs) == 1 and text._element.xpath(".//a:br")


def test_text_at_global_limits_exports(tdir):
    title = {"title": {"max": 120, "lines": 2}}
    bullets = {"image": 6, "bar-chart": 4, "chart": 4}
    deck = Deck(slides=[filled_slide(t, title | ({"bullets": {"count": bullets[t], "max": 200}}
                                                 if t in bullets else {})) for t in SLIDE_TYPES])
    assert len(export(tdir, deck).slides) == len(SLIDE_TYPES)


# --- сопоставление

def check(tdir):
    open_master(tdir, load_mapping(tdir, "pptx.json"))


def test_good_mapping_passes(tmp_path):
    check(make_pptx_template(tmp_path))


BROKEN = {
    "master-outside": (lambda m: m.update(master="../master.pptx"), "внутрь шаблона"),
    "master-missing": (lambda m: m.update(master="nope.pptx"), "нет файла nope.pptx"),
    "unknown-key": (lambda m: m.update(colour="FFFFFF"), "colour"),
    "missing-type": (lambda m: m["slides"].pop("final"), "нет типа final"),
    "missing-ph-field": (lambda m: m["slides"]["title"]["ph"].pop("department"), "нет поля department"),
    "extra-ph-field": (lambda m: m["slides"]["image"]["ph"].update(caption=1), "caption не кладётся"),
    "no-body": (lambda m: m["slides"]["image"].pop("body"), "нет body"),
    "body-on-title": (lambda m: m["slides"]["title"].update(body=[0, 0, 10, 10]), "body у этого типа не бывает"),
    "bad-color": (lambda m: m["chart"].update(negative="red"), "chart.negative"),
    "no-layout": (lambda m: m["slides"]["section"].update(layout="Нет такого"), "нет макета «Нет такого»"),
    "no-idx": (lambda m: m["slides"]["title"]["ph"].update(author=42), "нет заполнителя idx 42"),
    "zone-outside": (lambda m: m["slides"]["chart"].update(body=[600, 80, 200, 260]), "выходит за слайд"),
}


@pytest.mark.parametrize("case", BROKEN)
def test_broken_mapping_is_named(case, tmp_path):
    edit, text = BROKEN[case]
    d = make_pptx_template(tmp_path, mapping_edit=edit)
    with pytest.raises(MappingError, match=re.escape(text)):
        check(d)


def test_unreadable_mapping_is_named(tmp_path):
    d = make_pptx_template(tmp_path)
    (d / "pptx.json").write_text("{")
    with pytest.raises(MappingError, match="не читается"):
        load_mapping(d, "pptx.json")


def test_mapping_path_stays_inside_the_template(tmp_path):
    d = make_pptx_template(tmp_path)
    with pytest.raises(MappingError, match="внутрь шаблона"):
        load_mapping(d, "../pptx.json")
    with pytest.raises(MappingError, match="нет файла missing.json"):
        load_mapping(d, "missing.json")


def test_broken_master_file_is_named(tmp_path):
    d = make_pptx_template(tmp_path)
    (d / "master.pptx").write_bytes(b"not a zip")
    with pytest.raises(MappingError, match="не открывается"):
        check(d)
