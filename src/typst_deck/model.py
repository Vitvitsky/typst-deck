"""Модель колоды — источник истины для рендера, LLM и правок."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
TITLE_MAX = 120
BULLET_MAX = 200


def new_id(prefix: str = "", n: int = 6) -> str:
    return prefix + "".join(secrets.choice(ALPHABET) for _ in range(n))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


Title = Annotated[str, Field(max_length=TITLE_MAX)]
Bullet = Annotated[str, Field(min_length=1, max_length=BULLET_MAX)]
ImageSize = Literal["small", "medium", "large"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SlideBase(_Strict):
    id: str = Field(default_factory=lambda: new_id("s"))
    notes: str = ""


class TitleSlide(SlideBase):
    type: Literal["title"]
    title: Title
    subtitle: Title = ""


class SectionSlide(SlideBase):
    type: Literal["section"]
    title: Title
    subtitle: Title = ""


class ImageSlide(SlideBase):
    type: Literal["image"]
    title: Title
    bullets: list[Bullet] = Field(default_factory=list, max_length=6)
    image: str | None = None
    image_size: ImageSize = "medium"
    caption: Title = ""


class BarItem(_Strict):
    label: Title
    value: float


class BarChartSlide(SlideBase):
    type: Literal["bar-chart"]
    title: Title
    data: list[BarItem] = Field(min_length=1, max_length=12)
    unit: str = ""
    bullets: list[Bullet] = Field(default_factory=list, max_length=4)


class Series(_Strict):
    name: Title
    values: list[float]


class ChartSlide(SlideBase):
    type: Literal["chart"]
    title: Title
    labels: list[Title] = Field(min_length=2, max_length=24)
    series: list[Series] = Field(min_length=1, max_length=4)
    unit: str = ""
    bullets: list[Bullet] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _lengths(self):
        for s in self.series:
            if len(s.values) != len(self.labels):
                raise ValueError(
                    f"серия «{s.name}»: {len(s.values)} значений при {len(self.labels)} подписях"
                )
        return self


class FinalSlide(SlideBase):
    type: Literal["final"]
    title: Title = "Спасибо"
    contact: Title = ""


Slide = Annotated[
    Union[TitleSlide, SectionSlide, ImageSlide, BarChartSlide, ChartSlide, FinalSlide],
    Field(discriminator="type"),
]
SlideAdapter: TypeAdapter = TypeAdapter(Slide)


def slide_schema() -> dict:
    return SlideAdapter.json_schema()


class Deck(_Strict):
    id: str = Field(default_factory=lambda: new_id("", 12))
    title: Title = "Презентация"
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
