"""Колоды на диске: deck.json, версии, ассеты, загрузки, чат."""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

from .model import Deck, new_id, utcnow

ASSET_EXT = {".png", ".jpg", ".jpeg", ".svg"}
SAFE_NAME = re.compile(r"[^\w.\- ]", re.UNICODE)


class DeckNotFound(KeyError):
    pass


def write_atomic(path: Path, data: str | bytes) -> None:
    """Пишет во временный файл рядом и подменяет через os.replace."""
    mode = "wb" if isinstance(data, bytes) else "w"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, mode) as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def safe_name(name: str) -> str:
    return SAFE_NAME.sub("_", Path(name).name) or "file"


class DeckStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._locks: dict[str, asyncio.Lock] = {}

    # --- пути и блокировки
    def deck_dir(self, deck_id: str) -> Path:
        return self.data_dir / "decks" / deck_id

    def exists(self, deck_id: str) -> bool:
        return (self.deck_dir(deck_id) / "deck.json").exists()

    def lock(self, deck_id: str) -> asyncio.Lock:
        return self._locks.setdefault(deck_id, asyncio.Lock())

    # --- колода и версии
    def create(self, deck: Deck) -> Deck:
        d = self.deck_dir(deck.id)
        for sub in ("versions", "assets", "uploads"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        return self.save(deck)

    def list_decks(self) -> list[Deck]:
        """Все колоды, свежие сверху; битые deck.json пропускаются."""
        root = self.data_dir / "decks"
        decks = []
        for p in root.glob("*/deck.json") if root.is_dir() else []:
            try:
                decks.append(Deck.model_validate_json(p.read_text()))
            except ValueError:
                continue
        return sorted(decks, key=lambda d: d.updated_at, reverse=True)

    def load(self, deck_id: str) -> Deck:
        p = self.deck_dir(deck_id) / "deck.json"
        if not p.exists():
            raise DeckNotFound(deck_id)
        return Deck.model_validate_json(p.read_text())

    def save(self, deck: Deck) -> Deck:
        """Поднимает версию, пишет снимок в versions/ и текущий deck.json."""
        deck.version += 1
        deck.updated_at = utcnow()
        data = deck.model_dump_json(indent=2)
        d = self.deck_dir(deck.id)
        write_atomic(d / "versions" / f"{deck.version:06d}.json", data)
        write_atomic(d / "deck.json", data)
        return deck

    def delete(self, deck_id: str) -> Path:
        """Переносит каталог колоды в data/trash/<id>-<время>; ничего не стирает."""
        src = self.deck_dir(deck_id)
        if not (src / "deck.json").exists():
            raise DeckNotFound(deck_id)
        trash = self.data_dir / "trash"
        trash.mkdir(parents=True, exist_ok=True)
        dst = trash / f"{deck_id}-{utcnow().strftime('%Y%m%dT%H%M%S')}"
        os.rename(src, dst)
        return dst

    def list_versions(self, deck_id: str) -> list[int]:
        return sorted(int(p.stem) for p in (self.deck_dir(deck_id) / "versions").glob("*.json"))

    def load_version(self, deck_id: str, version: int) -> Deck:
        p = self.deck_dir(deck_id) / "versions" / f"{version:06d}.json"
        if not p.exists():
            raise DeckNotFound(f"{deck_id}@{version}")
        return Deck.model_validate_json(p.read_text())

    def revert(self, deck_id: str, version: int) -> Deck:
        """Полный откат на версию, включая шаблон: используется при провале рендера,
        а несобираемым может оказаться именно оформление. Пользовательский откат
        (POST /revert) шаблон намеренно сохраняет и делает это своим кодом.
        """
        old = self.load_version(deck_id, version)
        cur = self.load(deck_id)
        cur.title, cur.slides, cur.template = old.title, old.slides, old.template
        return self.save(cur)

    # --- ассеты
    def add_asset(self, deck_id: str, filename: str, data: bytes) -> str:
        ext = Path(filename).suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"
        if ext not in ASSET_EXT:
            raise ValueError(f"недопустимое расширение картинки: {ext or '(нет)'}")
        aid = new_id("a") + ext
        write_atomic(self.deck_dir(deck_id) / "assets" / aid, data)
        return aid

    def asset_path(self, deck_id: str, asset_id: str) -> Path:
        return self.deck_dir(deck_id) / "assets" / asset_id

    def assets(self, deck_id: str) -> list[str]:
        d = self.deck_dir(deck_id) / "assets"
        return sorted(p.name for p in d.iterdir() if p.is_file()) if d.is_dir() else []

    # --- загрузки
    def add_upload(self, deck_id: str, name: str, data: bytes, text: str | None) -> Path:
        p = self.deck_dir(deck_id) / "uploads" / safe_name(name)
        write_atomic(p, data)
        if text is not None:
            write_atomic(p.with_name(p.name + ".extracted"), text)
        return p

    def list_uploads(self, deck_id: str) -> list[tuple[str, str]]:
        d = self.deck_dir(deck_id) / "uploads"
        return [(p.name[: -len(".extracted")], p.read_text()) for p in sorted(d.glob("*.extracted"))]

    def stage_upload(self, name: str, data: bytes, text: str | None) -> str:
        """Загрузка до создания колоды: лежит в data/uploads/<id>/."""
        uid = new_id("u", 10)
        d = self.data_dir / "uploads" / uid
        d.mkdir(parents=True)
        write_atomic(d / "meta.json", json.dumps({"name": name}))
        write_atomic(d / "data", data)
        if text is not None:
            write_atomic(d / "text.txt", text)
        return uid

    def take_upload(self, upload_id: str) -> tuple[str, bytes, str | None]:
        d = self.data_dir / "uploads" / upload_id
        if not d.is_dir():
            raise KeyError(upload_id)
        name = json.loads((d / "meta.json").read_text())["name"]
        text = (d / "text.txt").read_text() if (d / "text.txt").exists() else None
        return name, (d / "data").read_bytes(), text

    # --- чат
    def append_chat(self, deck_id: str, entry: dict) -> None:
        with open(self.deck_dir(deck_id) / "chat.jsonl", "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_chat(self, deck_id: str) -> list[dict]:
        p = self.deck_dir(deck_id) / "chat.jsonl"
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
