"""Порождение deck.typ из модели и компиляция через typst."""
from __future__ import annotations

from .model import (
    BarChartSlide,
    ChartSlide,
    Deck,
    FinalSlide,
    ImageSlide,
    SectionSlide,
    TitleSlide,
)

HEADER = '#import "/template/deck.typ": *\n#import "/fields.typ": field\n'


def typ_str(s: str) -> str:
    """Строковый литерал Typst: содержимое не трактуется как разметка."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def typ_value(v) -> str:
    """Скаляры, списки и словари Python → литералы Typst."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return typ_str(v)
    if isinstance(v, (list, tuple)):
        return "(" + ", ".join(typ_value(x) for x in v) + ",)" if v else "()"
    if isinstance(v, dict):
        return "(" + ", ".join(f"{k}: {typ_value(x)}" for k, x in v.items()) + ")"
    raise TypeError(type(v))


def _text(slide_id: str, name: str, value: str) -> str:
    if not value:
        return "none"
    return f"field({typ_str(slide_id)}, {typ_str(name)}, {typ_str(value)})"


def _bullets(slide_id: str, items: list[str]) -> str:
    if not items:
        return "none"
    return f'field({typ_str(slide_id)}, "bullets", list({", ".join(typ_str(i) for i in items)}))'


def _opt(value: str) -> str:
    return typ_str(value) if value else "none"


def render_typ(deck: Deck, assets: set[str]) -> tuple[str, list[str]]:
    """Возвращает текст deck.typ и предупреждения (например, о пропавших картинках)."""
    out = [HEADER, f"#show: deck.with(title: {typ_str(deck.title)})\n"]
    warnings: list[str] = []
    for n, s in enumerate(deck.slides, 1):
        sid = s.id
        if isinstance(s, TitleSlide):
            out.append(
                f"#slide-title(title: {_text(sid, 'title', s.title)}, "
                f"subtitle: {_text(sid, 'subtitle', s.subtitle)})\n"
            )
        elif isinstance(s, SectionSlide):
            out.append(
                f"#slide-section(title: {_text(sid, 'title', s.title)}, "
                f"subtitle: {_text(sid, 'subtitle', s.subtitle)})\n"
            )
        elif isinstance(s, ImageSlide):
            img = "none"
            if s.image:
                if s.image in assets:
                    img = f'field({typ_str(sid)}, "image", image({typ_str("/assets/" + s.image)}))'
                else:
                    warnings.append(f"слайд {n}: картинка {s.image} не найдена")
            out.append(
                f"#slide-image(title: {_text(sid, 'title', s.title)}, "
                f"bullets: {_bullets(sid, s.bullets)}, image: {img}, "
                f"image-size: {typ_str(s.image_size)}, caption: {_text(sid, 'caption', s.caption)})\n"
            )
        elif isinstance(s, BarChartSlide):
            data = typ_value([i.model_dump() for i in s.data])
            out.append(
                f"#slide-bar-chart(title: {_text(sid, 'title', s.title)}, data: {data}, "
                f"unit: {_opt(s.unit)}, bullets: {_bullets(sid, s.bullets)})\n"
            )
        elif isinstance(s, ChartSlide):
            out.append(
                f"#slide-chart(title: {_text(sid, 'title', s.title)}, "
                f"labels: {typ_value(s.labels)}, "
                f"series: {typ_value([x.model_dump() for x in s.series])}, "
                f"unit: {_opt(s.unit)}, bullets: {_bullets(sid, s.bullets)})\n"
            )
        elif isinstance(s, FinalSlide):
            out.append(
                f"#slide-final(title: {_text(sid, 'title', s.title)}, "
                f"contact: {_text(sid, 'contact', s.contact)})\n"
            )
        else:  # pragma: no cover
            raise TypeError(type(s))
    return "".join(out), warnings
