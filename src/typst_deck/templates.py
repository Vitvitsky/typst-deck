"""Реестр Typst-шаблонов: template/ как «default» плюс <корень>/<id>/ по списку корней.

Корней может быть несколько (как PATH): репозиторный templates/ и, например,
закрытый каталог, примонтированный в контейнер. При совпадении id побеждает
первый корень. Шаблоном не считается каталог без deck.typ, а также каталог,
чей deck.typ импортирует то, чего нет на диске: так выглядит шаблон, канон
которого не подтянут скриптом синхронизации. И то и другое пишется в лог, а
не пропадает молча, и валит `check()` — иначе образ уедет без шаблона.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .model import Deck

log = logging.getLogger(__name__)

# Относительный импорт шаблона: "@preview/..." тянется из кэша пакетов, "/..." —
# из корня сборки (там лежит fields.typ), ни то ни другое рядом с шаблоном не ищется.
RELATIVE_IMPORT = re.compile(r'#(?:import|include)\s+"([^"@/][^"]*)"')


@dataclass
class TemplateInfo:
    id: str
    name: str
    description: str
    path: Path

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description}


class TemplateNotFound(KeyError):
    pass


# Образец для превью: по одному слайду каждого типа.
SAMPLE_DECK = Deck(id="templatepreview", title="Образец шаблона", slides=[
    {"id": "s000001", "type": "title", "title": "Название презентации", "subtitle": "Подзаголовок и дата"},
    {"id": "s000002", "type": "section", "title": "Раздел", "subtitle": "Промежуточный слайд"},
    {"id": "s000003", "type": "image", "title": "Текст и картинка", "bullets": ["Первый тезис", "Второй тезис", "Третий тезис"], "caption": "Подпись"},
    {"id": "s000004", "type": "bar-chart", "title": "Диаграмма", "unit": "млн", "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": 17}, {"label": "Юг", "value": 28}]},
    {"id": "s000005", "type": "chart", "title": "График", "labels": ["Q1", "Q2", "Q3", "Q4"], "series": [{"name": "Выручка", "values": [10, 14, 13, 18]}, {"name": "Расходы", "values": [8, 9, 11, 12]}]},
    {"id": "s000006", "type": "final", "contact": "team@corp"},
])


class TemplateRegistry:
    def __init__(self, default_dir: Path, templates_dirs: Path | str | Iterable[Path | str]):
        self.default_dir = Path(default_dir)
        roots = [templates_dirs] if isinstance(templates_dirs, (str, Path)) else list(templates_dirs)
        self.templates_dirs = [Path(r) for r in roots]
        self._warned: set[Path] = set()
        self.incomplete: dict[str, list[str]] = {}  # id → чего не хватает; наполняется в _scan
        self._scan()  # предупреждения о неполных каталогах — при старте, в лог

    def _warn(self, path: Path, msg: str) -> None:
        if path not in self._warned:
            self._warned.add(path)
            log.warning("шаблон %s: %s", path, msg)

    def _missing(self, d: Path) -> list[str]:
        """Относительные импорты deck.typ, которых нет рядом с ним.

        Проверка на один уровень: ловит ровно тот случай, ради которого написана —
        адаптер в git есть, канон рядом с ним не подтянут.
        """
        try:
            src = (d / "deck.typ").read_text()
        except OSError:
            return ["deck.typ"]
        return sorted({m for m in RELATIVE_IMPORT.findall(src) if not (d / m).exists()})

    def _scan(self) -> dict[str, Path]:
        """id → каталог по всем корням; первый корень побеждает."""
        found: dict[str, Path] = {}
        for root in self.templates_dirs:
            if not root.is_dir():
                self._warn(root, "корня шаблонов нет")
                continue
            for d in sorted(root.iterdir()):
                if not d.is_dir() or d.name.startswith((".", "_")) or d.name == "default":
                    continue
                if not (d / "deck.typ").exists():
                    self._warn(d, "нет deck.typ — каталог пропущен")
                    continue
                missing = self._missing(d)
                if missing:
                    self.incomplete[d.name] = missing
                    self._warn(d, f"deck.typ импортирует {', '.join(missing)}, а рядом их нет — "
                                  "каталог пропущен; шаблон синхронизирован не до конца")
                    continue
                self.incomplete.pop(d.name, None)
                found.setdefault(d.name, d)
        return found

    def _info(self, tid: str, path: Path) -> TemplateInfo:
        meta: dict = {}
        mp = path / "template.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text())
            except ValueError:
                meta = {}
        name = meta.get("name") or ("Корпоративный" if tid == "default" else tid)
        return TemplateInfo(tid, name, meta.get("description", ""), path)

    def list(self) -> list[TemplateInfo]:
        out = []
        if (self.default_dir / "deck.typ").exists():
            out.append(self._info("default", self.default_dir))
        out += [self._info(tid, d) for tid, d in self._scan().items()]
        return out

    def get(self, tid: str) -> TemplateInfo:
        if tid == "default" and (self.default_dir / "deck.typ").exists():
            return self._info("default", self.default_dir)
        if "/" in tid or ".." in tid or tid.startswith((".", "_")):
            raise TemplateNotFound(tid)
        d = self._scan().get(tid)
        if d is None:
            raise TemplateNotFound(tid)
        return self._info(tid, d)

    def dir_for(self, tid: str) -> Path:
        return self.get(tid).path


def check(registry: TemplateRegistry, typst_bin: str, work_dir: Path) -> list[str]:
    """Собирает образец каждым шаблоном реестра; возвращает список ошибок.

    Это проверка на уровне сборки образа: шаблон, у которого на месте deck.typ,
    но не хватает канона или шрифтов, ломается здесь, а не у пользователя.
    """
    from .render import CompileError, compile_deck

    errors = []
    for tid, missing in sorted(registry.incomplete.items()):
        errors.append(f"{tid}: нет {', '.join(missing)} — шаблон синхронизирован не до конца")
    for t in registry.list():
        deck_dir = work_dir / t.id
        try:
            compile_deck(SAMPLE_DECK, deck_dir, t.path, typst_bin)
        except CompileError as e:
            errors.append(f"{t.id}: {e}\n{e.stderr.strip()}")
    return errors


def main() -> int:
    """`python -m typst_deck.templates`: перечисляет шаблоны и собирает образец каждым."""
    import tempfile

    from .config import get_settings

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    s = get_settings()
    reg = TemplateRegistry(s.template_dir, s.templates_dirs)
    ids = [t.id for t in reg.list()]
    print("шаблоны:", ", ".join(ids) or "нет")
    with tempfile.TemporaryDirectory() as tmp:
        errors = check(reg, s.typst_bin, Path(tmp))
    for e in errors:
        print("ОШИБКА", e, file=sys.stderr)
    if not errors:
        print("каждый шаблон собирает образец")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
