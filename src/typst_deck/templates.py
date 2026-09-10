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
from dataclasses import dataclass, field
from pathlib import Path

from .contract import SAMPLE_DECK, check_template
from .render import resolve_fonts
from .slots import clamp

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
    # объявленная ёмкость слотов; пусто — действуют глобальные пределы model.py
    slots: dict = field(default_factory=dict)
    # каталог шрифтов шаблона (поле fonts в template.json) или None
    fonts: Path | None = None

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description}


class TemplateNotFound(KeyError):
    pass


class TemplateBroken(TemplateNotFound):
    """Шаблон на месте, но работать не может; причина — в reason."""

    def __init__(self, tid: str, reason: str):
        super().__init__(tid)
        self.reason = reason


class TemplateRegistry:
    def __init__(self, default_dir: Path, templates_dirs: Path | str | Iterable[Path | str],
                 aliases: dict[str, str] | None = None):
        self.default_dir = Path(default_dir)
        roots = [templates_dirs] if isinstance(templates_dirs, (str, Path)) else list(templates_dirs)
        self.templates_dirs = [Path(r) for r in roots]
        self._warned: set[Path] = set()
        self.incomplete: dict[str, list[str]] = {}  # id → чего не хватает; наполняется в _scan
        # старый id → действующий: колоды и внешние вызовы могли запомнить прежний
        self.aliases = dict(aliases or {})
        self.broken: dict[str, str] = {}          # id → причина; заполняет check_all
        self.warnings: dict[str, list[str]] = {}  # id → предупреждения стартовой проверки
        self.checked = False
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
        try:
            fonts = resolve_fonts(path, meta.get("fonts", "fonts"))
        except ValueError as e:
            self._warn(mp, f"{e} — взят каталог fonts/")
            fonts = resolve_fonts(path)
        name = meta.get("name") or ("Корпоративный" if tid == "default" else tid)
        return TemplateInfo(tid, name, meta.get("description", ""), path,
                            clamp(meta.get("slots"), tid), fonts)

    def all(self) -> list[TemplateInfo]:
        """Все шаблоны, включая сломанные: их проверяет check_all."""
        out = []
        if (self.default_dir / "deck.typ").exists():
            out.append(self._info("default", self.default_dir))
        out += [self._info(tid, d) for tid, d in self._scan().items()]
        return out

    def list(self) -> list[TemplateInfo]:
        """Шаблоны, которыми можно пользоваться: сломанные скрыты."""
        return [t for t in self.all() if t.id not in self.broken]

    def resolve(self, tid: str) -> str:
        """Старый id шаблона → действующий; неизвестный id возвращается как есть."""
        return self.aliases.get(tid, tid)

    def get(self, tid: str) -> TemplateInfo:
        tid = self.resolve(tid)
        if tid in self.broken:
            raise TemplateBroken(tid, self.broken[tid])
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

    def check_all(self, typst_bin: str, work_dir: Path) -> None:
        """Стартовая проверка: сломанные шаблоны прячутся, предупреждения запоминаются.
        Корпоративные шаблоны монтируются при запуске, и сборка образа их не видела.

        Список шаблонов и снимок self.incomplete берутся одним моментом, до
        медленного цикла компиляции: запросы в других потоках зовут list()/get(),
        те дергают _scan() и переписывают self.incomplete конкурентно, и обход
        живого словаря после цикла падал бы RuntimeError на изменении размера.
        """
        templates = self.all()
        incomplete = dict(self.incomplete)
        broken: dict[str, str] = {}
        warnings: dict[str, list[str]] = {}
        for t in templates:
            rep = check_template(t.path, typst_bin, work_dir / t.id, full=False)
            if rep.errors:
                broken[t.id] = "; ".join(rep.errors)
            if rep.warnings:
                warnings[t.id] = rep.warnings
        for tid, missing in incomplete.items():
            broken[tid] = f"нет {', '.join(missing)}"
        self.broken, self.warnings, self.checked = broken, warnings, True


def check(registry: TemplateRegistry, typst_bin: str, work_dir: Path, full: bool = True) -> list[str]:
    """Контракт для каждого шаблона реестра; возвращает список ошибок.

    Проверка на уровне сборки образа: встроенный шаблон, нарушающий контракт,
    ломается здесь, а не у пользователя. Корпоративные монтируются при запуске
    и проверяются сервисом при старте.
    """
    errors = [f"{tid}: нет {', '.join(missing)} — шаблон неполон"
              for tid, missing in sorted(registry.incomplete.items())]
    for t in registry.list():
        rep = check_template(t.path, typst_bin, work_dir / t.id, full=full)
        errors += [f"{t.id}: {e}" for e in rep.errors]
    return errors


def main(argv: list[str] | None = None) -> int:
    """`python -m typst_deck.templates [каталог]`: без аргумента — все шаблоны реестра,
    с аргументом — один каталог шаблона по полному контракту (docs/template-contract.md)."""
    import tempfile

    from .config import get_settings

    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    s = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        if argv:
            path = Path(argv[0]).expanduser().resolve()
            rep = check_template(path, s.typst_bin, Path(tmp))
            for w in rep.warnings:
                print("ПРЕДУПРЕЖДЕНИЕ", w, file=sys.stderr)
            for e in rep.errors:
                print("ОШИБКА", e, file=sys.stderr)
            if rep.ok:
                print(f"{path.name}: контракт соблюдён")
            return 0 if rep.ok else 1
        reg = TemplateRegistry(s.template_dir, s.templates_dirs, s.template_alias_map)
        print("шаблоны:", ", ".join(t.id for t in reg.list()) or "нет")
        errors = check(reg, s.typst_bin, Path(tmp))
    for e in errors:
        print("ОШИБКА", e, file=sys.stderr)
    if not errors:
        print("каждый шаблон соблюдает контракт")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
