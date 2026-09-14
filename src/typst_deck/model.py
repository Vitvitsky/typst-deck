"""Модель колоды — источник истины для рендера, LLM и правок."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
TITLE_MAX = 120
BULLET_MAX = 200
# Пределы, снятые замером вёрстки (2026-09-14, оба эталонных шаблона сошлись
# до сотой доли пункта): до них объявленная ёмкость обещала объём, который не
# помещается на страницу ни при каком читаемом кегле — правило потолка в
# tests/test_compile.py ловило переполнение у chart, table и image с крупной
# картинкой. Числа — не на глаз: рядом указано, где начинается обрез.
CHART_BULLET_MAX = 120   # колонка выводов 124×76.7 пт: 4×150 знаков вылезают на 3.80 пт
# Ячейка таблицы: запас меряется во входных данных, а не в ступенях кегля.
# Обрыв — 44 знака (8 строк × 6 ячеек): 43 ещё влезают (−4.05 пт), 44 вылезают
# (+15.52). 38 стоит примерно на 14 % ниже обрыва.
# Прежние 23 были платой за правило «пережить поднятие пола лестницы»: оно
# отменено, потому что стоило 42 % ёмкости («Выручка за IV квартал» — 21 знак),
# а вопрос «что если у шаблона шире гарнитура» честно решается сужением ячейки
# через slots и обмером корпоративного шаблона (план D), а не урезанием модели.
CELL_MAX = 38
LARGE_IMAGE_BULLETS = 900  # при image_size large: 6×200 знаков вылезают на 18.38 пт
# Единица измерения печатается в легенде графика. Предела у неё не было вовсе —
# проходила строка в 5000 знаков. Узкое место не сам график, а сторона
# dual-chart, где легенда вдвое уже: замер 2026-09-14 — 120 знаков влезают
# (−10.15 пт), 200 вылезают (+14.03); у одиночного графика запас больше
# (200 — −7.81, ломается на 500: +12.95). Берём меньшее из двух.
UNIT_MAX = 120
# Размен, о котором надо знать, ставя сюда большие числа: легенда графика живёт
# в коробке постоянной высоты (0.75 см у chart, 0.5 см у стороны dual-chart) —
# иначе её высота управляла бы бюджетом соседней колонки, и ёмкость шла бы
# зубцами. Что не уместилось в коробку, обрезается. Замер: у chart четыре имени
# по 120 знаков с единицей в 120 дают натуральные 36.49 пт при коробке 21.26 —
# видно два имени из четырёх, единицы нет вовсе; у стороны dual-chart три имени
# по 120 дают 67.06 пт при коробке 14.17 — не видно ни одного, включая первое.
# На правдоподобном содержимом (имена по 16 знаков) видно всё. То есть предел
# в 120 знаков модель пропустит, а легенда столько не покажет.
# Подпись категории под графиком. Была Title, то есть 120 знаков: одиночный
# график столько держит (24 подписи — −37.18 пт), но у стороны dual-chart
# колонка вдвое уже, и там замер 2026-09-14 даёт 60 знаков → +43.83,
# 40 → +28.23, 30 → −5.61. Предел общий на оба типа: подпись переносят из
# графика в двойной, не переписывая, и она обязана влезать там же.
CHART_LABEL_MAX = 30
# Подпись стороны dual-chart. Нельзя сузить общий Short (80) — он же у пункта
# повестки и подписи галереи. Замер 2026-09-14: обрыв на 78 знаках (78 даёт
# +9.63, 75 влезает с −1.65), и плато тянется от 40 до 75, так что 68 стоит
# примерно на 13 % ниже обрыва и далеко от его края.
# Число подписей и рядов не связывает НА ВЕРХНЕМ КРАЮ: 12 подписей и 3 ряда
# влезают, если подпись короче обрыва, а при подписи в 80 знаков не спасают
# и 2 подписи (+2.04). Поэтому резать их незачем — и они не урезаны.
# Но у нижнего края они связывают: ровно одна подпись при двух и более рядах,
# длинном заголовке и подписи стороны от 40 знаков давала +3.30. Ёмкость тут
# немонотонна, и это починено геометрией стороны, а не пределом (см. волну 6).
SIDE_CAPTION_MAX = 68
TEMPLATE_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,40}$"
URL_MAX = 500
ASSET_NAME_MAX = 120
VIDEO_EXT = (".mp4",)
POSTER_EXT = (".png", ".jpg", ".jpeg", ".svg")


def new_id(prefix: str = "", n: int = 6) -> str:
    return prefix + "".join(secrets.choice(ALPHABET) for _ in range(n))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


Title = Annotated[str, Field(max_length=TITLE_MAX)]
Bullet = Annotated[str, Field(min_length=1, max_length=BULLET_MAX)]
# вывод у графика живёт в колонке шириной в треть полосы, а не во всю ширину тела
ChartBullet = Annotated[str, Field(min_length=1, max_length=CHART_BULLET_MAX)]
Short = Annotated[str, Field(max_length=80)]        # пункт повестки, подпись галереи, подпись графика
Heading = Annotated[str, Field(max_length=60)]      # заголовок блока, колонки, метрики
Cell = Annotated[str, Field(max_length=CELL_MAX)]   # ячейка таблицы
Unit = Annotated[str, Field(max_length=UNIT_MAX)]   # единица измерения в легенде
ChartLabel = Annotated[str, Field(max_length=CHART_LABEL_MAX)]  # подпись категории
SideCaption = Annotated[str, Field(max_length=SIDE_CAPTION_MAX)]  # подпись стороны dual-chart
ImageSize = Literal["small", "medium", "large"]
ChartKind = Literal["bar", "line"]

SLIDE_TYPES = ("title", "agenda", "section", "text", "image", "columns", "comparison",
               "quote", "chart", "dual-chart", "metrics", "table", "gallery", "video", "final")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlideBase(_Strict):
    id: str = Field(default_factory=lambda: new_id("s"))
    notes: str = ""


class Series(_Strict):
    name: Title
    values: list[float]


def _same_length(labels: list, series: list[Series], kind: str) -> None:
    """Общая проверка графика: значений столько же, сколько подписей; линии нужны две точки."""
    for s in series:
        if len(s.values) != len(labels):
            raise ValueError(f"серия «{s.name}»: {len(s.values)} значений при {len(labels)} подписях")
    if kind == "line" and len(labels) < 2:
        raise ValueError("линейному графику нужно минимум две точки")


class Block(_Strict):
    heading: Heading = ""
    text: Annotated[str, Field(min_length=1, max_length=300)]


class Side(_Strict):
    heading: Heading = ""
    bullets: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(min_length=1, max_length=5)


class Metric(_Strict):
    value: Annotated[str, Field(min_length=1, max_length=16)]
    label: Heading = ""
    delta: Annotated[str, Field(max_length=12)] = ""


class Picture(_Strict):
    image: Annotated[str, Field(min_length=1)]
    caption: Short = ""


class ChartSide(_Strict):
    caption: SideCaption = ""
    kind: ChartKind = "line"
    labels: list[ChartLabel] = Field(min_length=1, max_length=12)
    series: list[Series] = Field(min_length=1, max_length=3)
    unit: Unit = ""

    @model_validator(mode="after")
    def _lengths(self):
        _same_length(self.labels, self.series, self.kind)
        return self


class TitleSlide(SlideBase):
    type: Literal["title"]
    title: Title
    subtitle: Title = ""
    # отдельные блоки, а не строки внутри подзаголовка: шаблоны размещают их сами
    author: Title = ""
    department: Title = ""


class AgendaSlide(SlideBase):
    type: Literal["agenda"]
    title: Title = "Повестка"
    items: list[Short] = Field(min_length=3, max_length=7)


class SectionSlide(SlideBase):
    type: Literal["section"]
    title: Title
    subtitle: Title = ""


class TextSlide(SlideBase):
    type: Literal["text"]
    title: Title
    bullets: list[Bullet] = Field(min_length=1, max_length=6)


class ImageSlide(SlideBase):
    type: Literal["image"]
    title: Title
    bullets: list[Bullet] = Field(default_factory=list, max_length=6)
    image: Annotated[str, Field(min_length=1)]  # без картинки бывает text, а не image
    image_size: ImageSize = "medium"
    caption: Title = ""

    @model_validator(mode="after")
    def _bullets_fit_beside_the_picture(self):
        """Крупная картинка забирает 55 % ширины, и колонке тезисов остаётся 159 пт
        вместо 209: тот же текст, что при medium помещается, при large уходит под
        обрез (замер: 6×200 знаков — на 18.38 пт ниже границы страницы, 6×150 —
        влезает). Предел здесь перекрёстный, а не в самом поле: резать bullets у
        всех размеров значило бы наказать medium и small, где всё помещается.
        """
        if self.image_size == "large":
            total = sum(len(b) for b in self.bullets)
            if total > LARGE_IMAGE_BULLETS:
                raise ValueError(
                    f"при крупной картинке (image_size «large») тезисам остаётся меньше места: "
                    f"суммарно не больше {LARGE_IMAGE_BULLETS} знаков, а их {total}. "
                    "Сократите тезисы или возьмите image_size «medium»")
        return self


class ColumnsSlide(SlideBase):
    type: Literal["columns"]
    title: Title
    blocks: list[Block] = Field(min_length=2, max_length=3)


class ComparisonSlide(SlideBase):
    type: Literal["comparison"]
    title: Title
    left: Side
    right: Side


class QuoteSlide(SlideBase):
    type: Literal["quote"]
    text: Annotated[str, Field(min_length=1, max_length=300)]
    author: Annotated[str, Field(max_length=120)] = ""


class ChartSlide(SlideBase):
    type: Literal["chart"]
    title: Title
    kind: ChartKind = "line"
    labels: list[ChartLabel] = Field(min_length=1, max_length=24)
    series: list[Series] = Field(min_length=1, max_length=4)
    unit: Unit = ""
    bullets: list[ChartBullet] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _lengths(self):
        _same_length(self.labels, self.series, self.kind)
        return self


class DualChartSlide(SlideBase):
    type: Literal["dual-chart"]
    title: Title
    left: ChartSide
    right: ChartSide


class MetricsSlide(SlideBase):
    type: Literal["metrics"]
    title: Title
    items: list[Metric] = Field(min_length=2, max_length=4)


class TableSlide(SlideBase):
    type: Literal["table"]
    title: Title
    header: list[Annotated[str, Field(max_length=40)]] = Field(min_length=2, max_length=6)
    rows: list[list[Cell]] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _rows(self):
        for i, row in enumerate(self.rows, 1):
            if len(row) != len(self.header):
                raise ValueError(f"строка {i}: {len(row)} ячеек при {len(self.header)} колонках шапки")
        return self


class GallerySlide(SlideBase):
    type: Literal["gallery"]
    title: Title
    images: list[Picture] = Field(min_length=2, max_length=4)


class VideoSlide(SlideBase):
    type: Literal["video"]
    title: Title
    video: Annotated[str, Field(max_length=ASSET_NAME_MAX)] = ""   # ассет .mp4 в колоде
    url: Annotated[str, Field(max_length=URL_MAX)] = ""            # внешняя ссылка
    poster: Annotated[str, Field(max_length=ASSET_NAME_MAX)] = ""  # ассет-картинка обложки
    caption: Annotated[str, Field(max_length=120)] = ""

    @model_validator(mode="after")
    def _source(self):
        """Ровно один источник — и он должен быть тем, чем назвался.

        Значение уходит в PDF живой ссылкой, поэтому схема и длина проверяются
        здесь, пока это одна строка кода: сегодня поле пишет только агентское API,
        а план C открывает загрузку ролика и поле ссылки в интерфейсе.
        """
        if bool(self.video) == bool(self.url):
            raise ValueError("у видео должно быть ровно одно: файл video или ссылка url")
        if self.video and not self.video.lower().endswith(VIDEO_EXT):
            raise ValueError(f"video: нужен ассет .mp4, а не «{self.video}»")
        if self.poster and not self.poster.lower().endswith(POSTER_EXT):
            raise ValueError(f"poster: нужна картинка ({', '.join(POSTER_EXT)}), а не «{self.poster}»")
        if self.url and not self.url.lower().startswith(("http://", "https://")):
            raise ValueError("url: ссылка должна начинаться с http:// или https://")
        return self


class FinalSlide(SlideBase):
    type: Literal["final"]
    title: Title = "Спасибо"
    contact: Title = ""


Slide = Annotated[
    Union[TitleSlide, AgendaSlide, SectionSlide, TextSlide, ImageSlide, ColumnsSlide,
          ComparisonSlide, QuoteSlide, ChartSlide, DualChartSlide, MetricsSlide,
          TableSlide, GallerySlide, VideoSlide, FinalSlide],
    Field(discriminator="type"),
]
SlideAdapter: TypeAdapter = TypeAdapter(Slide)


def slide_schema() -> dict:
    return SlideAdapter.json_schema()


class Deck(_Strict):
    id: str = Field(default_factory=lambda: new_id("", 12))
    title: Title = "Презентация"
    template: str = Field(default="default", pattern=TEMPLATE_PATTERN)
    slides: list[Slide] = Field(default_factory=list)
    version: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def index_of(self, slide_id: str) -> int:
        for i, s in enumerate(self.slides):
            if s.id == slide_id:
                return i
        raise KeyError(slide_id)

    def find(self, slide_id: str):
        return self.slides[self.index_of(slide_id)]

    def apply_patch(self, slide_id: str, patch: dict):
        """Меняет отдельные поля слайда; тип и id неизменяемы."""
        i = self.index_of(slide_id)
        old = self.slides[i]
        if "type" in patch and patch["type"] != old.type:
            raise ValueError("тип слайда нельзя менять патчем; удалите слайд и добавьте новый")
        if "id" in patch and patch["id"] != old.id:
            raise ValueError("id слайда нельзя менять")
        new = SlideAdapter.validate_python(old.model_dump() | patch)
        self.slides[i] = new
        return new

    def add_slide(self, data: dict, after: str | None = None):
        slide = SlideAdapter.validate_python(data)
        pos = len(self.slides) if after is None else self.index_of(after) + 1
        self.slides.insert(pos, slide)
        return slide

    def remove_slide(self, slide_id: str) -> None:
        del self.slides[self.index_of(slide_id)]

    def move_slide(self, slide_id: str, to_index: int) -> None:
        s = self.slides.pop(self.index_of(slide_id))
        self.slides.insert(max(0, min(to_index, len(self.slides))), s)
