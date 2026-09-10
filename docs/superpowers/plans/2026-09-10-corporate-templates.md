# Корпоративные шаблоны вне продукта — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** корпоративный шаблон живёт в репозитории своего канона и подключается к typst-deck монтированием; контракт шаблона — отдельная инструкция с проверкой; `lmru-hr` становится `lemana-tech` без потери двух боевых колод.

**Architecture:** реестр шаблонов учится трём вещам — каталогу шрифтов из `template.json`, алиасам старых id из окружения и пометке сломанных шаблонов. Правила контракта живут в новом модуле `contract.py`: им пользуются и CLI для автора шаблона (полный режим), и сервис при старте (стартовый режим). Корень репозитория канона Lemana Tech становится корнем шаблона: адаптер, шрифты и геометрия замера лежат в его папке `typst-deck/`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest (`uv run pytest`), Typst 0.15.1, rootless podman + Quadlet.

**Spec:** `docs/superpowers/specs/2026-09-10-corporate-templates-design.md`

## Global Constraints

- Комментарии, сообщения и тексты тестов — по-русски, как во всём репозитории.
- Новых зависимостей не добавлять; `src/typst_deck/model.py` не менять.
- `uv run pytest` зелёный перед каждым коммитом (сейчас 250 passed); `typst` 0.15.1 установлен, тесты компиляции реально выполняются. Начиная с задачи 8 — ещё и `TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest`.
- Слой LLM (`src/typst_deck/llm/`) не импортирует реестр шаблонов.
- Ответы с ошибкой имеют форму `{"error": {"code", "message"}}`.
- Id шаблона — имя каталога, под которым его корень виден реестру (точка монтирования или имя ссылки), а не имя репозитория канона.
- Алиасы задаются окружением: `TYPST_DECK_TEMPLATE_ALIASES="старый:новый,старый2:новый2"`. Продукт не хранит корпоративные id в коде.
- Стартовая проверка шаблонов не делает `/api/health` равным `ok: false`.
- Канон Lemana Tech: `~/projects/lmru--hr-analytics--design-template`, remote нет, ветка `main`. Правится только в задаче 7 и только так, как в ней написано.
- Каждое сообщение коммита заканчивается строкой `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Отклонения от спеки, принятые при планировании

1. **Правило 6 переформулировано.** Спека считала ошибкой любое `unknown font family`. Проверено 2026-09-10: typst предупреждает о каждом ненайденном семействе в списке, даже когда первое нашлось, — канон с исправным списком `("TT Interphases Pro", "TT Interphases Pro Trl", "Liberation Sans")` дал бы ошибку из-за запасных. Новое правило: если у шаблона есть каталог шрифтов, образец, собранный без системных шрифтов, обязан отличаться от собранного без этого каталога — иначе шрифты шаблона не используются (ровно случай «…Pro Trl»). Предупреждения typst о запасных семействах — пункты `warnings`, не ошибки. Приём проверен: `--ignore-system-fonts` в typst 0.15 есть, вывод с каталогом и без различается.
2. **Проверка — новый модуль `src/typst_deck/contract.py`,** а не `templates.py` (спека §9): реестр остаётся реестром, правила — отдельно.
3. **Сломанные шаблоны для тестов строятся в `tmp_path` из эталона `template/`** одной правкой `deck.typ`, а не лежат файлами в `tests/fixtures/`: так они не расходятся с эталоном, а правка, которая перестала применяться, валит тест с понятным сообщением.
4. **Правило 4 не требует маркер `caption` у слайда `image` без картинки:** эталон рисует подпись только под картинкой, а у образца картинки нет.
5. **Правило 5 проверяет «одна страница», как в спеке.** Обрезку текста внутри слота оно не видит — её ловит корпоративный тест задачи 8, который сравнивает высоту поля с зоной из `measure.json`.
6. **Проверка цвета падения на графиках для корпоративного шаблона снята:** цвета у каждого шаблона свои, общий тест их не знает. Проверка «одна страница на слайд» для корпоративных шаблонов остаётся.
7. **`SAMPLE_DECK` получает `author` и `department`,** чтобы правило 4 проверяло и их маркеры; превью шаблона заодно показывает подпись.
8. **`scripts/dev.sh` алиасы не задаёт:** локальные колоды переносятся той же командой, что и боевые.

---

### Task 1: каталог шрифтов из `template.json`

**Files:**
- Modify: `src/typst_deck/render.py` (`resolve_fonts`, `compile_deck`, `compile_pdf`)
- Modify: `src/typst_deck/templates.py` (`TemplateInfo.fonts`, `_info`, `check`)
- Modify: `src/typst_deck/service.py` (`template`, `template_dir`, `template_preview`, `render`, `pdf`)
- Test: `tests/test_render.py`, `tests/test_templates.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: ничего нового.
- Produces:
  - `render.resolve_fonts(template_dir: Path, rel: object = "fonts") -> Path | None` — каталог шрифтов или `None`; `ValueError`, если путь выводит за корень;
  - `compile_deck(deck, deck_dir, template_dir, typst_bin="typst", timeout=60, fonts_dir: Path | None = None)`;
  - `compile_pdf(build_dir, typst_bin="typst", timeout=60, fonts_dir: Path | None = None)`;
  - `TemplateInfo.fonts: Path | None`;
  - `DeckService.template(tid: str) -> TemplateInfo` — 422, если шаблона нет.

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_render.py` (импорты `pytest`, `Deck`, `TEMPLATE_DIR` влить в существующий блок):

```python
def test_compile_deck_takes_fonts_from_the_given_dir(deck_dir, tmp_path, monkeypatch):
    """Каталог шрифтов приходит из template.json шаблона, а не всегда <шаблон>/fonts."""
    import typst_deck.render as render

    class Stop(Exception):
        pass

    seen = []

    def fake_run(cmd, timeout):
        seen.append(cmd)
        raise Stop

    monkeypatch.setattr(render, "_run", fake_run)
    fonts = tmp_path / "typst-deck" / "fonts"
    fonts.mkdir(parents=True)
    with pytest.raises(Stop):
        render.compile_deck(Deck(slides=[{"type": "final"}]), deck_dir, TEMPLATE_DIR, fonts_dir=fonts)
    assert seen[0][seen[0].index("--font-path") + 1] == str(fonts)


def test_compile_pdf_takes_fonts_from_the_given_dir(tmp_path, monkeypatch):
    import typst_deck.render as render

    class Stop(Exception):
        pass

    seen = []

    def fake_run(cmd, timeout):
        seen.append(cmd)
        raise Stop

    monkeypatch.setattr(render, "_run", fake_run)
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
```

В `tests/test_templates.py`:

```python
def test_registry_resolves_fonts_dir(tmp_path):
    root = tmp_path / "templates"
    plain = root / "plain"
    (plain / "fonts").mkdir(parents=True)
    (plain / "deck.typ").write_text("// stub")
    custom = root / "custom"
    (custom / "typst-deck" / "fonts").mkdir(parents=True)
    (custom / "deck.typ").write_text("// stub")
    (custom / "template.json").write_text(json.dumps({"name": "C", "fonts": "typst-deck/fonts"}))
    bare = root / "bare"
    bare.mkdir()
    (bare / "deck.typ").write_text("// stub")
    reg = TemplateRegistry(TEMPLATE_DIR, root)
    assert reg.get("plain").fonts == plain / "fonts"
    assert reg.get("custom").fonts == custom / "typst-deck" / "fonts"
    assert reg.get("bare").fonts is None


def test_registry_refuses_fonts_outside_the_template(tmp_path, caplog):
    d = tmp_path / "templates" / "escape"
    (d / "fonts").mkdir(parents=True)
    (d / "deck.typ").write_text("// stub")
    (d / "template.json").write_text(json.dumps({"name": "E", "fonts": "../../elsewhere"}))
    with caplog.at_level("WARNING", logger="typst_deck.templates"):
        reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
        assert reg.get("escape").fonts == d / "fonts"  # взят каталог по умолчанию
    assert any("fonts" in r.getMessage() and "внутрь шаблона" in r.getMessage() for r in caplog.records)
```

В `tests/test_api.py`:

```python
async def test_pdf_is_built_with_the_template_fonts(settings, fake_llm, tmp_path, monkeypatch):
    """PDF собирается с каталогом шрифтов шаблона колоды, а не с жёстким build/template/fonts."""
    import json
    import shutil

    import typst_deck.service as service_module
    from typst_deck.app import create_app
    from typst_deck.model import Deck

    root = tmp_path / "corp"
    t = root / "withfonts"
    shutil.copytree(settings.template_dir, t)
    (t / "typst-deck" / "fonts").mkdir(parents=True)
    (t / "template.json").write_text(json.dumps({"name": "Со шрифтами", "fonts": "typst-deck/fonts"}))
    app = create_app(settings.model_copy(update={"templates_dir": str(root)}), llm=fake_llm)
    store, svc_ = app.state.store, app.state.service
    d = store.create(Deck(title="T", template="withfonts", slides=[{"type": "final"}]))
    build = store.deck_dir(d.id) / "build"
    build.mkdir()
    (build / "deck.typ").write_text("")
    seen = {}

    def fake_pdf(build_dir, typst_bin, fonts_dir=None):
        seen["fonts"] = fonts_dir
        (build_dir / "deck.pdf").write_bytes(b"%PDF")
        return build_dir / "deck.pdf"

    monkeypatch.setattr(service_module, "compile_pdf", fake_pdf)
    await svc_.pdf(d.id)
    assert seen["fonts"] == t / "typst-deck" / "fonts"
```

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/test_render.py tests/test_templates.py tests/test_api.py -k "fonts" -v`
Expected: FAIL — `compile_deck() got an unexpected keyword argument 'fonts_dir'`, `cannot import name 'resolve_fonts'`, `TemplateInfo` без `fonts`.

- [ ] **Step 3: `resolve_fonts` и параметр `fonts_dir` в `render.py`**

Добавить функцию рядом с `page_size`:

```python
def resolve_fonts(template_dir: Path, rel: object = "fonts") -> Path | None:
    """Каталог шрифтов шаблона: rel — поле fonts из template.json, от корня шаблона.

    None — каталога нет, typst обойдётся системными шрифтами. Путь наружу из
    шаблона — ValueError: в контейнере шаблон смонтирован, и цели снаружи там нет.
    """
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"fonts={rel!r}: путь должен вести внутрь шаблона")
    d = Path(template_dir) / rel
    return d if d.is_dir() else None
```

Сигнатура и строки шрифтов в `compile_deck`:

```python
def compile_deck(
    deck: Deck, deck_dir: Path, template_dir: Path, typst_bin: str = "typst", timeout: int = 60,
    fonts_dir: Path | None = None,
) -> CompileResult:
```

```python
    # каталог шрифтов — из template.json шаблона (TemplateInfo.fonts); без него прежнее место
    fonts = Path(fonts_dir) if fonts_dir is not None else Path(template_dir) / "fonts"
    font_args = ["--font-path", str(fonts)] if fonts.is_dir() else []
```

И в `compile_pdf`:

```python
def compile_pdf(build_dir: Path, typst_bin: str = "typst", timeout: int = 60,
                fonts_dir: Path | None = None) -> Path:
```

```python
    fonts = Path(fonts_dir) if fonts_dir is not None else build_dir / "template" / "fonts"
    font_args = ["--font-path", str(fonts)] if fonts.is_dir() else []
```

- [ ] **Step 4: `TemplateInfo.fonts` в реестре**

В `src/typst_deck/templates.py` добавить импорт `from .render import resolve_fonts`, поле и разбор:

```python
    # каталог шрифтов шаблона (поле fonts в template.json) или None
    fonts: Path | None = None
```

```python
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
```

В `check()` передать шрифты: `compile_deck(SAMPLE_DECK, deck_dir, t.path, typst_bin, fonts_dir=t.fonts)`.

- [ ] **Step 5: Сервис берёт шрифты у шаблона**

В `src/typst_deck/service.py` (импорт `TemplateInfo` влить в строку `from .templates import ...`; если `Path` не импортирован — добавить `from pathlib import Path`):

```python
    def template(self, tid: str) -> TemplateInfo:
        """Шаблон по id; неизвестный — 422 с понятным текстом."""
        try:
            return self.templates.get(tid)
        except TemplateNotFound:
            raise ApiError(422, "validation", f"шаблон «{tid}» не найден")

    def template_dir(self, tid: str):
        return self.template(tid).path
```

`template_preview`: `t = self.template(tid)`, `tdir = t.path`, и в вызов `compile_deck` добавить `fonts_dir=t.fonts`.

`render`:

```python
        t = self.template(deck.template)
        try:
            return await asyncio.to_thread(
                compile_deck, deck, self.store.deck_dir(deck.id), t.path,
                self.settings.typst_bin, fonts_dir=t.fonts,
            )
        except CompileError as e:
            raise ApiError(500, "render", f"{e}: {e.stderr[:2000]}")
```

`pdf` — колоду загрузить в переменную и передать шрифты:

```python
        deck = self.load(deck_id)
```

```python
            try:
                fonts = self.templates.get(deck.template).fonts
            except TemplateNotFound:
                fonts = None  # шаблон пропал, но build/ собран: PDF соберётся с прежним каталогом
            try:
                return await asyncio.to_thread(compile_pdf, build, self.settings.typst_bin, fonts_dir=fonts)
```

- [ ] **Step 6: Прогнать тесты**

Run: `uv run pytest tests/test_render.py tests/test_templates.py tests/test_api.py -k "fonts" -v && uv run pytest`
Expected: PASS, 250 + 6 новых.

- [ ] **Step 7: Коммит**

```bash
git add src/typst_deck/render.py src/typst_deck/templates.py src/typst_deck/service.py tests/test_render.py tests/test_templates.py tests/test_api.py
git commit -m "Каталог шрифтов шаблона берётся из template.json, а не всегда из fonts/"
```

---

### Task 2: алиасы старых id шаблонов

**Files:**
- Modify: `src/typst_deck/config.py`
- Modify: `src/typst_deck/templates.py` (`TemplateRegistry.__init__`, `resolve`, `get`)
- Modify: `src/typst_deck/service.py` (`__init__`, `new_deck_from_brief`, `change_template`, `generate`)
- Test: `tests/test_config.py`, `tests/test_templates.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `DeckService.template()` из задачи 1.
- Produces:
  - `Settings.template_aliases: str`, `Settings.template_alias_map -> dict[str, str]` (`ValueError` на кривую пару);
  - `TemplateRegistry(default_dir, templates_dirs, aliases: dict[str, str] | None = None)`, `.aliases`, `.resolve(tid) -> str`.

- [ ] **Step 1: Написать падающие тесты**

`tests/test_config.py` (импорты влить в существующий блок):

```python
def test_template_aliases_parse():
    s = Settings(_env_file=None, template_aliases=" lmru-hr:lemana-tech , a:b ,")
    assert s.template_alias_map == {"lmru-hr": "lemana-tech", "a": "b"}
    assert Settings(_env_file=None).template_alias_map == {}


def test_template_aliases_refuse_a_malformed_pair():
    with pytest.raises(ValueError, match="старый:новый"):
        Settings(_env_file=None, template_aliases="lmru-hr").template_alias_map
```

`tests/test_templates.py`:

```python
def test_registry_resolves_old_ids(tmp_path):
    d = tmp_path / "templates" / "new-id"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text("// stub")
    (d / "template.json").write_text(json.dumps({"name": "Новый"}))
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates", {"old-id": "new-id"})
    assert reg.get("old-id").id == "new-id" and reg.get("old-id").name == "Новый"
    assert reg.dir_for("old-id") == d
    assert [t.id for t in reg.list()] == ["default", "new-id"]  # в списке только действующий id
    assert reg.resolve("old-id") == "new-id" and reg.resolve("other") == "other"
```

`tests/test_api.py`:

```python
@requires_typst
async def test_old_template_id_is_stored_as_the_new_one(settings, fake_llm):
    """Бот мог зашить старый id: создание и переезд принимают его и пишут новый."""
    import httpx

    from typst_deck.app import create_app
    from typst_deck.model import Deck

    app = create_app(settings.model_copy(update={"template_aliases": "old-dark:dark"}), llm=fake_llm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        fake_llm._queue += [Completion("", [ToolCall("c1", "finish", {"summary": "ok"})])]
        r = await c.post("/api/decks", json={"brief": "Итоги", "template": "old-dark"})
        assert r.status_code == 202
        await wait_job(c, r.json()["job_id"])
        assert (await c.get(f"/api/decks/{r.json()['deck_id']}")).json()["deck"]["template"] == "dark"
        assert "old-dark" not in [t["id"] for t in (await c.get("/api/templates")).json()]
        d = app.state.store.create(Deck(title="T", slides=[{"type": "final"}]))
        r = await c.post(f"/api/decks/{d.id}/template", json={"template": "old-dark"})
        assert r.status_code == 200 and r.json()["deck"]["template"] == "dark"
```

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/test_config.py tests/test_templates.py tests/test_api.py -k "alias or old_template or old_ids" -v`
Expected: FAIL — нет `template_aliases`, `TemplateRegistry` не принимает третий аргумент.

- [ ] **Step 3: Настройка**

В `src/typst_deck/config.py`, в `Settings`:

```python
    template_aliases: str = ""                 # старые id шаблонов: "старый:новый,старый2:новый2"
```

```python
    @property
    def template_alias_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.template_aliases.split(","):
            pair = pair.strip()
            if not pair:
                continue
            old, sep, new = pair.partition(":")
            if not sep or not old.strip() or not new.strip():
                raise ValueError(f"TYPST_DECK_TEMPLATE_ALIASES: «{pair}» — ожидается старый:новый")
            out[old.strip()] = new.strip()
        return out
```

- [ ] **Step 4: Реестр разрешает алиасы**

В `TemplateRegistry.__init__` добавить параметр и поле:

```python
    def __init__(self, default_dir: Path, templates_dirs: Path | str | Iterable[Path | str],
                 aliases: dict[str, str] | None = None):
        ...
        # старый id → действующий: колоды и внешние вызовы могли запомнить прежний
        self.aliases = dict(aliases or {})
```

```python
    def resolve(self, tid: str) -> str:
        """Старый id шаблона → действующий; неизвестный id возвращается как есть."""
        return self.aliases.get(tid, tid)
```

Первой строкой `get`: `tid = self.resolve(tid)`.

- [ ] **Step 5: Сервис хранит действующий id**

```python
        self.templates = TemplateRegistry(settings.template_dir, settings.templates_dirs,
                                          settings.template_alias_map)
```

В `new_deck_from_brief` первой строкой после `self.require_llm()`: `template = self.templates.resolve(template)`.

В `change_template` первой строкой: `template = self.templates.resolve(template)`.

В `generate`, где строится словарь пределов:

```python
                limits = {t.id: (t.slots, t.name) for t in infos}
                # колода могла остаться на старом id — пределы у него те же, что у нового
                limits |= {old: limits[new] for old, new in self.templates.aliases.items() if new in limits}
                out = await run_agent(llm, deck, message, files, history, self.store.assets(deck_id),
                                      templates=[t.public() for t in infos], limits=limits)
```

- [ ] **Step 6: Прогнать тесты**

Run: `uv run pytest tests/test_config.py tests/test_templates.py tests/test_api.py -v && uv run pytest`
Expected: PASS.

- [ ] **Step 7: Коммит**

```bash
git add src/typst_deck/config.py src/typst_deck/templates.py src/typst_deck/service.py tests/test_config.py tests/test_templates.py tests/test_api.py
git commit -m "Старые id шаблонов разрешаются алиасами из окружения"
```

---

### Task 3: проверка шаблона на контракт

**Files:**
- Create: `src/typst_deck/contract.py`
- Modify: `src/typst_deck/render.py` (`CompileResult.stderr`, параметр `system_fonts`)
- Modify: `src/typst_deck/templates.py` (`SAMPLE_DECK` переезжает в `contract.py`, `check`, `main`)
- Modify: `tests/conftest.py` (`make_template` и правки-образцы)
- Test: `tests/test_contract.py` (создать)

**Interfaces:**
- Consumes: `resolve_fonts`, `compile_deck(..., fonts_dir=)` из задачи 1; `slots.clamp`.
- Produces:
  - `contract.SAMPLE_DECK` (реэкспортируется из `templates`);
  - `contract.Report(errors: list[str], warnings: list[str])`, `.ok`;
  - `contract.check_template(path: Path, typst_bin: str, work_dir: Path, full: bool = True) -> Report`;
  - `contract.filled_slide(stype: str, limits: dict, sample: str = FILL) -> dict`;
  - `compile_deck(..., system_fonts: bool = True)`, `CompileResult.stderr: str`;
  - `templates.check(registry, typst_bin, work_dir, full=True) -> list[str]`;
  - `python -m typst_deck.templates [каталог]`;
  - в `tests/conftest.py`: `make_template(parent, name, deck_edit=None, meta=None) -> Path` и правки `TWO_PAGES`, `NO_CLIP_FINAL`, `NO_CONTACT`, `FALLBACK_FONT`.

- [ ] **Step 1: Помощник для сломанных шаблонов**

В `tests/conftest.py` (импорт `shutil` уже есть):

```python
# Правки эталона template/deck.typ: каждая ломает ровно одно правило контракта.
TWO_PAGES = ("#let slide-final(title: none, contact: none) = slide(fill: accent)[",
             "#let slide-final(title: none, contact: none) = page[] + slide(fill: accent)[")
NO_CLIP_FINAL = ("#let slide-final(title: none, contact: none) = slide(fill: accent)[",
                 "#let slide-final(title: none, contact: none) = page(fill: accent)[")
NO_CONTACT = ("#if contact != none { v(0.4cm); text(size: 12pt, contact) }", "")
FALLBACK_FONT = ('set text(font: "DejaVu Sans",', 'set text(font: ("DejaVu Sans", "Нет Такого Шрифта"),')


def make_template(parent: Path, name: str, deck_edit: tuple[str, str] | None = None,
                  meta: dict | None = None) -> Path:
    """Копия эталона template/ с одной правкой deck.typ и своим template.json.

    Сломанные шаблоны выводятся из эталона, а не лежат файлами: так они не
    расходятся с ним, а правка, которая перестала применяться, валит тест сразу.
    """
    import json

    d = parent / name
    shutil.copytree(TEMPLATE_DIR, d)
    if deck_edit:
        old, new = deck_edit
        src = (d / "deck.typ").read_text()
        assert old in src, f"эталон template/deck.typ изменился: нет «{old}»"
        (d / "deck.typ").write_text(src.replace(old, new, 1))
    if meta is not None:
        (d / "template.json").write_text(json.dumps(meta, ensure_ascii=False))
    return d
```

- [ ] **Step 2: Написать падающие тесты**

Создать `tests/test_contract.py`:

```python
import shutil
from pathlib import Path

import pytest

from tests.conftest import (FALLBACK_FONT, NO_CLIP_FINAL, NO_CONTACT, ROOT, TEMPLATE_DIR, TWO_PAGES,
                            make_template, requires_typst)
from typst_deck.contract import check_template, filled_slide
from typst_deck.model import Deck

DEJAVU = Path("/usr/share/fonts/truetype/dejavu")
needs_dejavu = pytest.mark.skipif(not (DEJAVU / "DejaVuSans.ttf").exists(), reason="нет файлов DejaVu")


@requires_typst
@pytest.mark.parametrize("tdir", [TEMPLATE_DIR, ROOT / "templates" / "dark"], ids=["default", "dark"])
def test_reference_templates_pass_the_full_contract(tdir, tmp_path):
    rep = check_template(tdir, "typst", tmp_path)
    assert rep.errors == [] and rep.warnings == []


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
def test_extra_page_per_slide_is_an_error(tmp_path):
    d = make_template(tmp_path, "twopages", deck_edit=TWO_PAGES)
    assert any("образец не собирается" in e for e in check_template(d, "typst", tmp_path / "w").errors)


@requires_typst
def test_overflow_on_oversized_or_declared_text_is_an_error(tmp_path):
    """Правила 3 и 5: финальный слайд без обрезки переливается на вторую страницу."""
    d = make_template(tmp_path, "overflow", deck_edit=NO_CLIP_FINAL,
                      meta={"name": "П", "slots": {"final": {"title": {"max": 120},
                                                            "contact": {"max": 120, "lines": 9}}}})
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
def test_fallback_font_family_is_only_a_warning(tmp_path):
    """typst предупреждает о каждом запасном семействе; это сведения, не ошибка."""
    d = make_template(tmp_path, "fallback", deck_edit=FALLBACK_FONT)
    rep = check_template(d, "typst", tmp_path / "w")
    assert rep.errors == []
    assert any("нет такого шрифта" in w.lower() for w in rep.warnings), rep.warnings


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
    Deck(slides=[s, c, filled_slide("bar-chart", {"data": {"count": 6}}), filled_slide("final", {})])
```

- [ ] **Step 3: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/test_contract.py -v`
Expected: FAIL — `No module named 'typst_deck.contract'`.

- [ ] **Step 4: `render.py` — предупреждения typst и сборка без системных шрифтов**

В `CompileResult` добавить поле:

```python
    # предупреждения typst при сборке SVG (например, «unknown font family»): сборка при них проходит
    stderr: str = ""
```

В `compile_deck` добавить параметр `system_fonts: bool = True` (после `fonts_dir`) и сразу после `font_args`:

```python
    if not system_fonts:
        # проверка контракта: чем шаблон набирает текст, когда системных шрифтов нет
        font_args.append("--ignore-system-fonts")
```

После проверки `if r.returncode != 0` для SVG запомнить `svg_stderr = r.stderr` и передать `stderr=svg_stderr` в `CompileResult(...)`.

- [ ] **Step 5: Модуль `contract.py`**

Создать `src/typst_deck/contract.py`:

```python
"""Проверка шаблона на контракт typst-deck (docs/template-contract.md).

Два режима. Полный — для автора шаблона и CI: шесть правил, строго.
Стартовый — для работающего сервиса: сломанным считается только шаблон, который
не может работать; шрифты и ключи slots там — предупреждения, а не поломка,
иначе одна опечатка в корпоративной вёрстке остановила бы все колоды на ней.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .model import Deck
from .render import CompileError, CompileResult, compile_deck, resolve_fonts
from .slots import clamp

# Образец: по слайду каждого типа. Им же рисуются превью шаблонов в интерфейсе.
SAMPLE_DECK = Deck(id="templatepreview", title="Образец шаблона", slides=[
    {"id": "s000001", "type": "title", "title": "Название презентации", "subtitle": "Подзаголовок и дата",
     "author": "Имя Фамилия", "department": "Подразделение"},
    {"id": "s000002", "type": "section", "title": "Раздел", "subtitle": "Промежуточный слайд"},
    {"id": "s000003", "type": "image", "title": "Текст и картинка", "bullets": ["Первый тезис", "Второй тезис", "Третий тезис"], "caption": "Подпись"},
    {"id": "s000004", "type": "bar-chart", "title": "Диаграмма", "unit": "млн", "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": 17}, {"label": "Юг", "value": 28}]},
    {"id": "s000005", "type": "chart", "title": "График", "labels": ["Q1", "Q2", "Q3", "Q4"], "series": [{"name": "Выручка", "values": [10, 14, 13, 18]}, {"name": "Расходы", "values": [8, 9, 11, 12]}]},
    {"id": "s000006", "type": "final", "contact": "team@corp"},
])

TEXT_FIELDS = ("title", "subtitle", "author", "department", "caption", "contact", "bullets")
STRING_LISTS = ("bullets", "labels")
FONT_WARNING = re.compile(r"unknown font family: ([^\n]+)")
OVERSIZED = "Очень длинный текст, который заведомо не помещается в отведённое место " * 6
FILL = "Итоги квартала по направлению данных и аналитики "


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class _Collect(logging.Handler):
    """Предупреждения clamp своего потока: clamp зовут и параллельные запросы."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.thread = threading.get_ident()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread == self.thread:
            self.messages.append(record.getMessage())


def _clamp_collect(raw: object, tid: str) -> tuple[dict, list[str]]:
    handler = _Collect()
    lg = logging.getLogger("typst_deck.slots")
    lg.addHandler(handler)
    try:
        declared = clamp(raw, tid)
    finally:
        lg.removeHandler(handler)
    return declared, handler.messages


def _text(sample: str, n: int, lines: int = 1) -> str:
    """Ровно n знаков из sample; при lines > 1 — с lines-1 явными переводами строки внутри."""
    body = (sample * (n // max(len(sample), 1) + 2))[: max(n - (lines - 1), 1)]
    if lines <= 1:
        return body
    step = max(len(body) // lines, 1)
    parts = [body[i * step:(i + 1) * step] for i in range(lines - 1)] + [body[(lines - 1) * step:]]
    return "\n".join(parts)


def filled_slide(stype: str, limits: dict[str, dict[str, int]], sample: str = FILL) -> dict:
    """Слайд типа stype, где каждое объявленное поле заполнено ровно по его пределам.
    Обязательные поля без объявления получают короткие значения."""
    slide: dict = {"type": stype}
    for fld, lim in limits.items():
        if fld in STRING_LISTS:
            slide[fld] = [_text(sample, lim.get("max", 40))] * lim.get("count", 3)
        elif fld == "data":
            slide["data"] = [{"label": f"Пункт {i + 1}", "value": i + 1} for i in range(lim.get("count", 3))]
        elif fld != "series":  # ряды собираются ниже, под число подписей
            slide[fld] = _text(sample, lim.get("max", 40), lim.get("lines", 1))
    if stype in ("title", "section", "image", "bar-chart", "chart"):
        slide.setdefault("title", "Итоги")
    if stype == "bar-chart":
        slide.setdefault("data", [{"label": "Центр", "value": 42}])
    if stype == "chart":
        slide.setdefault("labels", ["Q1", "Q2"])
        k = limits.get("series", {}).get("count", 1)
        slide["series"] = [{"name": f"Ряд {j + 1}", "values": list(range(len(slide["labels"])))}
                           for j in range(k)]
    return slide


def _read_meta(path: Path, report: Report) -> dict | None:
    """Правило 1, файлы: deck.typ и читаемый template.json с name."""
    if not (path / "deck.typ").is_file():
        report.errors.append("нет deck.typ в корне шаблона")
    mp = path / "template.json"
    if not mp.is_file():
        report.errors.append("нет template.json в корне шаблона")
        return None
    try:
        meta = json.loads(mp.read_text())
    except ValueError as e:
        report.errors.append(f"template.json не читается: {e}")
        return None
    if not isinstance(meta, dict) or not meta.get("name"):
        report.errors.append("в template.json нет поля name")
        return None
    return meta


def _rule_fonts_used(path: Path, typst_bin: str, work_dir: Path, fonts: Path | None) -> list[str]:
    """Правило 6: шрифты из каталога шаблона реально используются.

    Образец собирается без системных шрифтов дважды — с каталогом и без него.
    Одинаковый вывод значит, что семейства, которые называет шаблон, не совпадают
    с файлами. Ровно так канон Lemana Tech просил «…Pro Trl», которого в его же
    архиве нет, и молча получал чужой шрифт.
    """
    if fonts is None:
        return []
    empty = work_dir / "no-fonts"
    empty.mkdir(parents=True, exist_ok=True)
    try:
        a = compile_deck(SAMPLE_DECK, work_dir / "fonts-with", path, typst_bin, fonts_dir=fonts, system_fonts=False)
        b = compile_deck(SAMPLE_DECK, work_dir / "fonts-without", path, typst_bin, fonts_dir=empty, system_fonts=False)
    except CompileError as e:
        return [f"образец без системных шрифтов не собирается: {e}"]
    if a.pages == b.pages:
        return [f"шрифты из {fonts.relative_to(path)}/ не используются: "
                "семейства, которые называет шаблон, не совпадают с файлами"]
    return []


def _rule_oversized(path: Path, typst_bin: str, work_dir: Path, fonts: Path | None) -> list[str]:
    """Правило 3: переросший вход не выносит слайд на вторую страницу."""
    big = OVERSIZED[:120]
    breaks = big[:60] + "\n" * 8 + big[:40]  # переводы строки — механизм инцидента 2026-09-09
    deck = Deck(slides=[
        {"type": "title", "title": big, "subtitle": breaks, "author": big, "department": big},
        {"type": "section", "title": big, "subtitle": breaks},
        {"type": "final", "title": big, "contact": breaks},
    ])
    try:
        compile_deck(deck, work_dir / "oversized", path, typst_bin, fonts_dir=fonts)
    except CompileError as e:
        return [f"переросший текст ломает страницу: {e}"]
    return []


def _rule_markers(sample: CompileResult) -> list[str]:
    """Правило 4: у каждого непустого текстового поля образца есть маркер <edit>."""
    have = {(p.get("slide"), p.get("field")) for p in sample.positions}
    missing = []
    for n, s in enumerate(SAMPLE_DECK.slides, 1):
        for fld in TEXT_FIELDS:
            if not getattr(s, fld, None):
                continue
            if fld == "caption" and s.type == "image" and not s.image:
                continue  # подпись — к картинке; без картинки шаблон вправе её не рисовать
            if (s.id, fld) not in have:
                missing.append(f"слайд {n} ({s.type}): поле {fld} не размечено — "
                               "шаблон не выводит его или выводит без маркера")
    return missing


def _rule_declared_fit(path: Path, typst_bin: str, work_dir: Path, fonts: Path | None,
                       declared: dict) -> list[str]:
    """Правило 5: слайды, заполненные ровно по объявленным пределам, — по одной странице."""
    if not declared:
        return []
    try:
        deck = Deck(slides=[filled_slide(t, lim) for t, lim in declared.items()])
        compile_deck(deck, work_dir / "declared", path, typst_bin, fonts_dir=fonts)
    except CompileError as e:
        return [f"текст по объявленным пределам slots не помещается: {e}"]
    except ValueError as e:
        return [f"по пределам slots нельзя собрать слайд: {e}"]
    return []


def check_template(path: Path, typst_bin: str, work_dir: Path, full: bool = True) -> Report:
    """Правила контракта для каталога шаблона; full=False — стартовый режим сервиса."""
    path, work_dir = Path(path), Path(work_dir)
    report = Report()
    strict = report.errors if full else report.warnings
    meta = _read_meta(path, report)
    if meta is None or report.errors:
        return report
    declared, notes = _clamp_collect(meta.get("slots"), path.name)
    strict.extend(f"slots: {m}" for m in notes)
    try:
        fonts = resolve_fonts(path, meta.get("fonts", "fonts"))
    except ValueError as e:
        report.errors.append(str(e))
        return report
    try:  # правило 2: образец собирается, одна функция — одна страница
        sample = compile_deck(SAMPLE_DECK, work_dir / "sample", path, typst_bin, fonts_dir=fonts)
    except CompileError as e:
        report.errors.append(f"образец не собирается: {e} {e.stderr.strip()}".strip())
        return report
    report.warnings.extend(f"typst не нашёл семейство шрифта «{f}»"
                           for f in sorted(set(FONT_WARNING.findall(sample.stderr))))
    strict.extend(_rule_fonts_used(path, typst_bin, work_dir, fonts))
    if full:
        report.errors.extend(_rule_oversized(path, typst_bin, work_dir, fonts))
        report.errors.extend(_rule_markers(sample))
        report.errors.extend(_rule_declared_fit(path, typst_bin, work_dir, fonts, declared))
    return report
```

- [ ] **Step 6: `templates.py` — образец из `contract`, проверка и CLI**

Удалить определение `SAMPLE_DECK` из `templates.py` и импортировать: `from .contract import SAMPLE_DECK, check_template` (`service.py` продолжает брать `SAMPLE_DECK` из `templates` — реэкспорт сохраняется). Импорт `Deck` из `.model`, если он больше не нужен, удалить.

Заменить `check` и `main`:

```python
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
```

- [ ] **Step 7: Прогнать тесты**

Run: `uv run pytest tests/test_contract.py tests/test_templates.py -v && uv run pytest && uv run python -m typst_deck.templates`
Expected: PASS; последняя команда печатает «каждый шаблон соблюдает контракт». Если `lmru-hr` (копия канона в `templates/`) даёт ошибку правила 6 — записать её текст в отчёт и не чинить: это ровно та проблема, которую задача 7 решает в каноне.

- [ ] **Step 8: Коммит**

```bash
git add src/typst_deck/contract.py src/typst_deck/render.py src/typst_deck/templates.py tests/conftest.py tests/test_contract.py
git commit -m "Проверка шаблона на контракт: шесть правил, полный и стартовый режимы"
```

---

### Task 4: сломанные шаблоны при старте и `templates` в `/api/health`

**Files:**
- Modify: `src/typst_deck/templates.py` (`TemplateBroken`, `broken`, `warnings`, `checked`, `all`, `list`, `get`, `check_all`)
- Modify: `src/typst_deck/service.py` (`template`, `deck_response`, `check_templates`, `templates_health`)
- Modify: `src/typst_deck/config.py` (`check_templates_on_start`)
- Modify: `src/typst_deck/app.py` (фоновая проверка, `/api/health`)
- Modify: `tests/conftest.py` (`check_templates_on_start=False` в `settings` и `tight_settings`)
- Test: `tests/test_templates.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `contract.check_template(..., full=False)` из задачи 3; `make_template`, `TWO_PAGES`, `FALLBACK_FONT` из `tests/conftest.py`.
- Produces:
  - `templates.TemplateBroken(tid, reason)` — подкласс `TemplateNotFound`, поле `reason`;
  - `TemplateRegistry.broken: dict[str, str]`, `.warnings: dict[str, list[str]]`, `.checked: bool`, `.all()`, `.check_all(typst_bin, work_dir)`;
  - `DeckService.check_templates()`, `DeckService.templates_health() -> dict`;
  - `Settings.check_templates_on_start: bool = True`.

- [ ] **Step 1: Отключить фоновую проверку в тестовых настройках**

В `tests/conftest.py`, в `Settings(...)` фикстур `settings` и `tight_settings` добавить `check_templates_on_start=False`.

- [ ] **Step 2: Написать падающие тесты**

`tests/test_templates.py` (импорты `FALLBACK_FONT`, `TWO_PAGES`, `make_template`, `TemplateBroken` влить в блок):

```python
@requires_typst
def test_start_check_hides_broken_and_keeps_warned_templates(tmp_path):
    root = tmp_path / "templates"
    make_template(root, "broken", deck_edit=TWO_PAGES)
    make_template(root, "odd-font", deck_edit=FALLBACK_FONT)
    reg = TemplateRegistry(TEMPLATE_DIR, root)
    assert not reg.checked
    reg.check_all("typst", tmp_path / "work")
    assert reg.checked
    assert [t.id for t in reg.list()] == ["default", "odd-font"]
    assert "образец не собирается" in reg.broken["broken"]
    with pytest.raises(TemplateBroken) as e:
        reg.get("broken")
    assert "образец не собирается" in e.value.reason
    assert any("нет такого шрифта" in w.lower() for w in reg.warnings["odd-font"])
    assert "broken" in [t.id for t in reg.all()]


@requires_typst
def test_incomplete_template_is_reported_as_broken(tmp_path):
    d = tmp_path / "templates" / "half"
    d.mkdir(parents=True)
    (d / "deck.typ").write_text('#import "slides_template.typ": *\n')
    reg = TemplateRegistry(TEMPLATE_DIR, tmp_path / "templates")
    reg.check_all("typst", tmp_path / "work")
    assert "slides_template.typ" in reg.broken["half"]
```

`tests/test_api.py`:

```python
@requires_typst
async def test_broken_template_is_hidden_refused_and_reported(settings, fake_llm, tmp_path):
    import httpx

    from tests.conftest import TWO_PAGES, make_template
    from typst_deck.app import create_app

    root = tmp_path / "corp"
    make_template(root, "broken", deck_edit=TWO_PAGES, meta={"name": "Сломанный"})
    app = create_app(settings.model_copy(update={"templates_dir": str(root)}), llm=fake_llm)
    app.state.service.check_templates()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert "broken" not in [t["id"] for t in (await c.get("/api/templates")).json()]
        r = await c.post("/api/decks", json={"brief": "Итоги", "template": "broken"})
        assert r.status_code == 422 and "сломан" in r.json()["error"]["message"]
        h = (await c.get("/api/health")).json()
        assert h["ok"] is True and h["templates"]["checked"] is True
        assert "broken" in h["templates"]["broken"] and "default" in h["templates"]["ok"]


@requires_typst
async def test_app_checks_templates_in_background_on_start(settings, fake_llm):
    from typst_deck.app import create_app

    app = create_app(settings.model_copy(update={"check_templates_on_start": True}), llm=fake_llm)
    for _ in range(200):
        if app.state.service.templates.checked:
            break
        await asyncio.sleep(0.05)
    assert app.state.service.templates.checked
```

- [ ] **Step 3: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/test_templates.py tests/test_api.py -k "broken or background or incomplete_template_is" -v`
Expected: FAIL — нет `TemplateBroken`, `check_all`, `check_templates`.

- [ ] **Step 4: Реестр помнит сломанные шаблоны**

В `src/typst_deck/templates.py`:

```python
class TemplateBroken(TemplateNotFound):
    """Шаблон на месте, но работать не может; причина — в reason."""

    def __init__(self, tid: str, reason: str):
        super().__init__(tid)
        self.reason = reason
```

В `__init__` реестра:

```python
        self.broken: dict[str, str] = {}          # id → причина; заполняет check_all
        self.warnings: dict[str, list[str]] = {}  # id → предупреждения стартовой проверки
        self.checked = False
```

`list` переименовать в `all` и добавить новый `list`:

```python
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
```

В `get`, сразу после `tid = self.resolve(tid)`:

```python
        if tid in self.broken:
            raise TemplateBroken(tid, self.broken[tid])
```

И проверка:

```python
    def check_all(self, typst_bin: str, work_dir: Path) -> None:
        """Стартовая проверка: сломанные шаблоны прячутся, предупреждения запоминаются.
        Корпоративные шаблоны монтируются при запуске, и сборка образа их не видела."""
        broken: dict[str, str] = {}
        warnings: dict[str, list[str]] = {}
        for t in self.all():
            rep = check_template(t.path, typst_bin, work_dir / t.id, full=False)
            if rep.errors:
                broken[t.id] = "; ".join(rep.errors)
            if rep.warnings:
                warnings[t.id] = rep.warnings
        for tid, missing in self.incomplete.items():
            broken[tid] = f"нет {', '.join(missing)}"
        self.broken, self.warnings, self.checked = broken, warnings, True
```

- [ ] **Step 5: Сервис, настройка и приложение**

`src/typst_deck/config.py`, в `Settings`:

```python
    check_templates_on_start: bool = True      # фоновая проверка шаблонов при старте
```

`src/typst_deck/service.py` (импорты `tempfile` и `TemplateBroken` добавить в блок):

```python
    def template(self, tid: str) -> TemplateInfo:
        """Шаблон по id; неизвестный или сломанный — 422 с понятным текстом."""
        try:
            return self.templates.get(tid)
        except TemplateBroken as e:
            raise ApiError(422, "validation", f"шаблон «{e.args[0]}» сломан: {e.reason}")
        except TemplateNotFound:
            raise ApiError(422, "validation", f"шаблон «{tid}» не найден")

    def check_templates(self) -> None:
        """Стартовая проверка шаблонов; идёт в фоне, итог — в лог и в /api/health."""
        with tempfile.TemporaryDirectory() as tmp:
            self.templates.check_all(self.settings.typst_bin, Path(tmp))
        for tid, reason in self.templates.broken.items():
            log_event(log, "template.broken", template=tid, reason=reason, level=logging.ERROR)
        for tid, notes in self.templates.warnings.items():
            for w in notes:
                log_event(log, "template.warning", template=tid, warning=w, level=logging.WARNING)

    def templates_health(self) -> dict:
        t = self.templates
        return {"checked": t.checked, "ok": [x.id for x in t.list()],
                "broken": dict(t.broken), "warnings": dict(t.warnings)}
```

В `deck_response` ветка `except TemplateNotFound` называет причину, если шаблон сломан:

```python
        except TemplateNotFound as e:
            reason = e.reason if isinstance(e, TemplateBroken) else "шаблон не найден"
            template = {"id": deck.template, "name": deck.template, "description": reason}
```

`src/typst_deck/app.py` (импорт `threading`):

```python
    if settings.check_templates_on_start:
        # смонтированные шаблоны сборка образа не видит — сервис проверяет их сам,
        # в фоне: typst собирает образец каждым шаблоном, а старт ждать не должен
        threading.Thread(target=app.state.service.check_templates, name="template-check", daemon=True).start()
```

`/api/health` дополняется полем:

```python
        return {"ok": True, "llm": llm is not None,
                "model": settings.llm_model if llm is not None else None,
                "tokens": meter.public(), "since": meter.since.isoformat(),
                "templates": app.state.service.templates_health()}
```

- [ ] **Step 6: Прогнать тесты**

Run: `uv run pytest tests/test_templates.py tests/test_api.py -v && uv run pytest`
Expected: PASS.

- [ ] **Step 7: Коммит**

```bash
git add src/typst_deck/templates.py src/typst_deck/service.py src/typst_deck/config.py src/typst_deck/app.py tests/conftest.py tests/test_templates.py tests/test_api.py
git commit -m "Сломанный шаблон скрывается при старте и называет причину, а не роняет сервис"
```

---

### Task 5: команда переноса колод на новый id шаблона

**Files:**
- Create: `src/typst_deck/migrate_template.py`
- Test: `tests/test_migrate_template.py` (создать)

**Interfaces:**
- Consumes: `DeckStore`, `write_atomic`, `TEMPLATE_PATTERN`.
- Produces: `migrate_template.migrate(store: DeckStore, old: str, new: str) -> list[str]`, `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_migrate_template.py`:

```python
import pytest

from typst_deck.migrate_template import main, migrate
from typst_deck.model import Deck
from typst_deck.store import DeckStore


def test_migrate_moves_only_decks_on_the_old_id(tmp_path):
    store = DeckStore(tmp_path)
    a = store.create(Deck(title="A", template="lmru-hr"))
    b = store.create(Deck(title="B", template="dark"))
    before = store.load(a.id)
    assert migrate(store, "lmru-hr", "lemana-tech") == [a.id]
    after = store.load(a.id)
    assert after.template == "lemana-tech"
    assert after.version == before.version and after.updated_at == before.updated_at  # это не правка
    assert store.load_version(a.id, before.version).template == "lmru-hr"  # снимки не тронуты
    assert store.load(b.id).template == "dark"


def test_migrate_twice_changes_nothing_the_second_time(tmp_path):
    store = DeckStore(tmp_path)
    store.create(Deck(template="lmru-hr"))
    migrate(store, "lmru-hr", "lemana-tech")
    assert migrate(store, "lmru-hr", "lemana-tech") == []


def test_migrate_refuses_an_invalid_new_id(tmp_path):
    with pytest.raises(ValueError):
        migrate(DeckStore(tmp_path), "lmru-hr", "Bad/Id")


def test_main_reads_data_dir_from_settings(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TYPST_DECK_DATA_DIR", str(tmp_path))
    DeckStore(tmp_path).create(Deck(template="lmru-hr"))
    assert main(["lmru-hr", "lemana-tech"]) == 0
    assert "колод 1" in capsys.readouterr().out
    assert main(["only-one"]) == 2
```

- [ ] **Step 2: Прогнать и убедиться, что падают**

Run: `uv run pytest tests/test_migrate_template.py -v`
Expected: FAIL — `No module named 'typst_deck.migrate_template'`.

- [ ] **Step 3: Модуль**

Создать `src/typst_deck/migrate_template.py`:

```python
"""Разовый перенос колод со старого id шаблона на новый.

`python -m typst_deck.migrate_template старый-id новый-id`

Переписывает только поле template в deck.json — без подъёма версии: это
переименование, а не правка. Снимки versions/ не трогаются: откат колоды
копирует из снимка только title и slides. Запускать при остановленном сервисе,
иначе его запись и эта могут разойтись.
"""
from __future__ import annotations

import re
import sys

from .model import TEMPLATE_PATTERN, Deck
from .store import DeckStore, write_atomic


def migrate(store: DeckStore, old: str, new: str) -> list[str]:
    """Колоды на шаблоне old переводит на new; возвращает их id."""
    if not re.fullmatch(TEMPLATE_PATTERN, new):
        raise ValueError(f"некорректный id шаблона «{new}»")
    moved = []
    root = store.data_dir / "decks"
    for p in sorted(root.glob("*/deck.json")) if root.is_dir() else []:
        try:
            deck = Deck.model_validate_json(p.read_text())
        except ValueError:
            continue  # битый deck.json не наш вопрос: list_decks его тоже пропускает
        if deck.template != old:
            continue
        deck.template = new
        write_atomic(p, deck.model_dump_json(indent=2))
        moved.append(deck.id)
    return moved


def main(argv: list[str] | None = None) -> int:
    from .config import get_settings

    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("использование: python -m typst_deck.migrate_template старый-id новый-id", file=sys.stderr)
        return 2
    old, new = argv
    moved = migrate(DeckStore(get_settings().data_dir), old, new)
    print(f"{old} → {new}: колод {len(moved)}" + (f" ({', '.join(moved)})" if moved else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/test_migrate_template.py -v && uv run pytest`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/typst_deck/migrate_template.py tests/test_migrate_template.py
git commit -m "Команда переноса колод на новый id шаблона без подъёма версии"
```

---

### Task 6: `measure_slots.py` по пути к шаблону и геометрии из `measure`

**Files:**
- Modify: `scripts/measure_slots.py`
- Test: `tests/test_measure_slots.py` (создать)

**Interfaces:**
- Consumes: `render.resolve_fonts`, `render.typ_value`.
- Produces: `scripts/measure_slots.py <корень шаблона>`; формат `measure.json`:
  `{"import": str, "sample": str, "list": str, "probes": [{"slide", "field", "width", "height", "item"?, "size", "weight", "font"}]}`.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_measure_slots.py`:

```python
import json
import subprocess
import sys

from tests.conftest import ROOT, make_template, requires_typst

SCRIPT = ROOT / "scripts" / "measure_slots.py"


def _measure(tdir):
    return subprocess.run([sys.executable, str(SCRIPT), str(tdir)], capture_output=True, text=True)


@requires_typst
def test_measures_slots_from_the_template_measure_file(tmp_path):
    d = make_template(tmp_path, "m", meta={"name": "М", "measure": "measure.json"})
    (d / "measure.json").write_text(json.dumps({
        "import": "deck.typ",
        "sample": "Итоги квартала по направлению ",
        "list": "#set list(spacing: 0.35em)",
        "probes": [
            {"slide": "title", "field": "title", "width": "138mm", "height": "24mm",
             "size": "28pt", "weight": "bold", "font": "\"DejaVu Sans\""},
            {"slide": "image", "field": "bullets", "width": "80mm", "height": "40mm", "item": "12mm",
             "size": "11pt", "weight": "regular", "font": "\"DejaVu Sans\""},
        ],
    }, ensure_ascii=False))
    r = _measure(d)
    assert r.returncode == 0, r.stderr
    slots = json.loads(r.stdout)["slots"]
    assert 5 <= slots["title"]["title"]["max"] <= 400 and slots["title"]["title"]["lines"] >= 1
    assert slots["image"]["bullets"]["count"] >= 1 and slots["image"]["bullets"]["max"] >= 5
    assert not list(d.glob("_measure*.typ"))  # временные файлы убраны


def test_template_without_measure_is_refused(tmp_path):
    d = make_template(tmp_path, "nomeasure")
    r = _measure(d)
    assert r.returncode != 0 and "measure" in r.stderr
```

- [ ] **Step 2: Прогнать и убедиться, что падает**

Run: `uv run pytest tests/test_measure_slots.py -v`
Expected: FAIL — скрипт ищет шаблон по id в `templates/` и знает только `lmru-hr`.

- [ ] **Step 3: Переписать скрипт**

Заменить в `scripts/measure_slots.py` всё от докстринга до конца на:

```python
#!/usr/bin/env python
"""Ёмкость слота в знаках: не угадывается, а измеряется typst'ом.

Скрипт просит typst померить высоту текста настоящим шрифтом шаблона на наборе
длин-кандидатов и берёт наибольшую, которая ещё влезает в высоту слота. Тем же
способом (список кандидатов, наибольший подходящий) меряется допустимое число
явных строк и число тезисов в списке — для тезисов список из k штук набран
оформлением списка шаблона, чтобы учесть интервал между ними.

Геометрия слотов — в файле, на который указывает поле measure в template.json
шаблона (формат — docs/template-contract.md, раздел «Ёмкость слотов»).

Запуск:  uv run --project ~/projects/typst-deck python ~/projects/typst-deck/scripts/measure_slots.py <корень шаблона>
Вывод — готовый раздел slots для template.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from typst_deck.render import resolve_fonts, typ_value  # noqa: E402  (Typst tuple-литералы)

SAMPLE = "Итоги квартала по направлению данных и аналитики "

# {chars}, {lines}, {ks} — Typst-литералы от typ_value ("(10, 15, ...,)"): Python-репр
# списка дал бы content-блок "[10, 15, ...]", у которого нет .map(). {size}, {weight},
# {font} — выражения Typst из measure.json, вычисляемые после импорта шаблона.
PROBE_TYP = """#import "{imp}": *
#set page(width: {width}, height: auto, margin: 0pt)
#let base = "{sample}"
#let sample(n) = {{ let s = ""; while s.clusters().len() < n {{ s = s + base }}; s.clusters().slice(0, n).join() }}
#let lines(k) = range(k).map(i => "Строка").join("\\n")
#let h(body) = measure(width: {width}, text(size: {size}, weight: "{weight}", font: {font}, body)).height.mm()
#context [#metadata((
  chars: {chars}.map(n => (n, h(sample(n)))),
  lines: {lines}.map(k => (k, h(lines(k)))),
)) <probe>]
"""

# Список из k тезисов с оформлением списка шаблона (поле list в measure.json —
# копия его #set list): интервал стоит МЕЖДУ тезисами, поэтому меряется весь
# список, а не высота одного, умноженная на k.
COUNT_TYP = """#import "{imp}": *
#set page(width: {width}, height: auto, margin: 0pt)
{list_style}
#let base = "{sample}"
#let sample(n) = {{ let s = ""; while s.clusters().len() < n {{ s = s + base }}; s.clusters().slice(0, n).join() }}
#let one = text(size: {size}, weight: "{weight}", font: {font}, sample({max}))
#let h(k) = measure(width: {width}, list(..range(k).map(i => one))).height.mm()
#context [#metadata({ks}.map(k => (k, h(k)))) <count>]
"""


def load(tdir: Path) -> tuple[dict, Path | None]:
    """Геометрия из measure-файла шаблона и каталог его шрифтов."""
    meta = json.loads((tdir / "template.json").read_text())
    rel = meta.get("measure")
    if not rel:
        raise SystemExit(f"{tdir}/template.json: нет поля measure — геометрию слотов взять неоткуда")
    return json.loads((tdir / rel).read_text()), resolve_fonts(tdir, meta.get("fonts", "fonts"))


def _eval(tdir: Path, name: str, text: str, label: str, fonts: Path | None, what: str):
    """Пробный .typ живёт внутри корня (иначе typst не компилирует) и убирается всегда."""
    src = tdir / name
    src.write_text(text)
    try:
        font_args = ["--font-path", str(fonts)] if fonts else []
        cmd = ["typst", "eval", f"query(<{label}>).map(it => it.value)", "--root", str(tdir),
               *font_args, "--in", str(src), "--format", "json"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"typst не смог померить {what}:\n{r.stderr}")
        return json.loads(r.stdout)[0]
    finally:
        src.unlink(missing_ok=True)


def measure(tdir: Path, cfg: dict, probe: dict, fonts: Path | None) -> dict:
    """Высоты текста в мм для набора длин и для набора числа строк."""
    text = PROBE_TYP.format(imp=cfg["import"], width=probe["width"], sample=cfg.get("sample", SAMPLE),
                            size=probe["size"], weight=probe["weight"], font=probe["font"],
                            chars=typ_value(list(range(10, 401, 5))), lines=typ_value(list(range(1, 13))))
    return _eval(tdir, "_measure.typ", text, "probe", fonts, f"{probe['slide']}.{probe['field']}")


def measure_count(tdir: Path, cfg: dict, probe: dict, fonts: Path | None, max_chars: int) -> list[list]:
    """Высоты в мм списков из k оформленных тезисов по max_chars знаков — один вызов typst."""
    text = COUNT_TYP.format(imp=cfg["import"], width=probe["width"], sample=cfg.get("sample", SAMPLE),
                            list_style=cfg.get("list", ""), size=probe["size"], weight=probe["weight"],
                            font=probe["font"], max=max_chars, ks=typ_value(list(range(1, 21))))
    return _eval(tdir, "_measure_count.typ", text, "count", fonts,
                 f"список тезисов {probe['slide']}.{probe['field']}")


def largest_fitting(pairs: list[list], cap_mm: float) -> int:
    """Наибольшее значение, при котором высота ещё не превысила потолок."""
    ok = [n for n, h in pairs if h <= cap_mm]
    return max(ok) if ok else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("использование: measure_slots.py <корень шаблона>", file=sys.stderr)
        return 2
    tdir = Path(argv[0]).expanduser().resolve()
    if not (tdir / "deck.typ").exists():
        raise SystemExit(f"{tdir}: нет deck.typ — это не корень шаблона")
    cfg, fonts = load(tdir)
    out: dict[str, dict[str, dict[str, int]]] = {}
    for probe in cfg["probes"]:
        m = measure(tdir, cfg, probe, fonts)
        cap_mm = float(probe["height"].removesuffix("mm"))
        item = probe.get("item")
        item_mm = float(item.removesuffix("mm")) if item else cap_mm
        limits: dict[str, int] = {}
        chars = largest_fitting(m["chars"], item_mm)
        limits["max"] = max(chars - chars % 5, 5)
        if item:
            counts = measure_count(tdir, cfg, probe, fonts, limits["max"])
            limits["count"] = max(largest_fitting(counts, cap_mm), 1)
        else:
            limits["lines"] = max(largest_fitting(m["lines"], cap_mm), 1)
        out.setdefault(probe["slide"], {})[probe["field"]] = limits
        print(f"{probe['slide']}.{probe['field']}: {limits}", file=sys.stderr)
    print(json.dumps({"slots": out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Высоты в `measure.json` задаются в миллиметрах (`"60mm"`) — скрипт считает потолок в мм.

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/test_measure_slots.py -v && uv run pytest`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add scripts/measure_slots.py tests/test_measure_slots.py
git commit -m "Замер ёмкости слотов по пути к шаблону и геометрии из его measure.json"
```

---

### Task 7: Lemana Tech в репозитории канона

Работа идёт в `~/projects/lmru--hr-analytics--design-template` (далее `$C`), коммит — там же.

**Files (в `$C`):**
- Create: `deck.typ`, `template.json`, `typst-deck/adapter.typ`, `typst-deck/fonts/*.ttf`, `typst-deck/measure.json`
- Modify: `templates/typst/slides_template.typ` (списки шрифтов), `CLAUDE.md`, `AGENTS.md`

**Interfaces:**
- Consumes: `python -m typst_deck.templates <каталог>` (задача 3), `scripts/measure_slots.py <корень>` (задача 6), поле `fonts` (задача 1).
- Produces: корень шаблона Lemana Tech, проходящий полный контракт.

- [ ] **Step 1: Убедиться, что канон чист**

Run: `C=~/projects/lmru--hr-analytics--design-template; git -C $C status --short; git -C $C log --oneline -1`
Expected: пустой статус, HEAD `aac5628` (или новее — тогда записать в отчёт).

- [ ] **Step 2: Шрифты и адаптер**

```bash
C=~/projects/lmru--hr-analytics--design-template
mkdir -p $C/typst-deck/fonts
unzip -q -o -j $C/references/TTInterphasesPro.zip "TT Interphases Pro/ttf/*" -d $C/typst-deck/fonts
ls $C/typst-deck/fonts   # ожидаем три TTF: Regular, Medium, Bold
cp ~/projects/typst-deck/templates/lmru-hr/deck.typ $C/typst-deck/adapter.typ
```

Первые пять строк `$C/typst-deck/adapter.typ`:

```typst
// Адаптер контракта typst-deck поверх канонического шаблона Lemana Tech.
// Канон (slides_template.typ) не меняется, кроме константы lm-components-dir —
// так предписывает README шаблона. Здесь только семь функций контракта:
// deck, slide-title, slide-section, slide-image, slide-bar-chart, slide-chart, slide-final.
#import "slides_template.typ": *
```

заменить на:

```typst
// Адаптер контракта typst-deck (docs/template-contract.md в репозитории typst-deck)
// поверх канона этого репозитория. Канон подключается как есть: корень шаблона —
// корень репозитория, поэтому lm-components-dir канона ("../../references/components")
// разрешается внутри песочницы typst. Здесь только семь функций контракта:
// deck, slide-title, slide-section, slide-image, slide-bar-chart, slide-chart, slide-final.
#import "../templates/typst/slides_template.typ": *
```

- [ ] **Step 3: Точки входа в корне**

`$C/deck.typ`:

```typst
// Точка входа typst-deck: всё остальное — в typst-deck/ (контракт: docs/template-contract.md в typst-deck).
#import "typst-deck/adapter.typ": *
```

`$C/template.json` — имя, описание и `slots` перенести из `~/projects/typst-deck/templates/lmru-hr/template.json` без изменений, добавив два поля:

```json
{
  "name": "Lemana Tech",
  "description": "Корпоративный шаблон Лемана Тех: жёлтый титул, канонические компоненты, TT Interphases Pro",
  "fonts": "typst-deck/fonts",
  "measure": "typst-deck/measure.json",
  "slots": { "…": "ровно тот раздел slots, что сейчас в templates/lmru-hr/template.json" }
}
```

Раздел `slots` скопировать программно, а не руками:

```bash
cd ~/projects/typst-deck && uv run python - <<'PY'
import json, pathlib
src = json.loads(pathlib.Path("templates/lmru-hr/template.json").read_text())
out = {"name": src["name"], "description": src["description"],
       "fonts": "typst-deck/fonts", "measure": "typst-deck/measure.json", "slots": src["slots"]}
dst = pathlib.Path.home() / "projects/lmru--hr-analytics--design-template/template.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(dst.read_text())
PY
```

- [ ] **Step 4: Геометрия замера**

`$C/typst-deck/measure.json` — перенос `PROBES` из прежнего `scripts/measure_slots.py` и оформления списка из `deck()` адаптера:

```json
{
  "import": "templates/typst/slides_template.typ",
  "sample": "Итоги квартала по направлению данных и аналитики Лемана Тех ",
  "list": "#set list(marker: text(fill: lm-yellow, size: 1.2em)[•], spacing: 0.7em, indent: 0pt, body-indent: 0.5em)",
  "probes": [
    {"slide": "title", "field": "title", "width": "552mm", "height": "60mm", "size": "size-title", "weight": "bold", "font": "title-font"},
    {"slide": "title", "field": "subtitle", "width": "552mm", "height": "30mm", "size": "size-h2", "weight": "regular", "font": "title-font"},
    {"slide": "title", "field": "author", "width": "552mm", "height": "12mm", "size": "size-body", "weight": "regular", "font": "body-font"},
    {"slide": "title", "field": "department", "width": "552mm", "height": "12mm", "size": "size-body", "weight": "regular", "font": "body-font"},
    {"slide": "image", "field": "title", "width": "617mm", "height": "50mm", "size": "size-h1-compact", "weight": "bold", "font": "title-font"},
    {"slide": "image", "field": "bullets", "width": "349mm", "height": "250mm", "item": "40mm", "size": "size-body", "weight": "regular", "font": "body-font"},
    {"slide": "chart", "field": "title", "width": "617mm", "height": "50mm", "size": "size-h1-compact", "weight": "bold", "font": "title-font"},
    {"slide": "chart", "field": "bullets", "width": "230mm", "height": "200mm", "item": "40mm", "size": "size-body", "weight": "regular", "font": "body-font"},
    {"slide": "bar-chart", "field": "title", "width": "617mm", "height": "50mm", "size": "size-h1-compact", "weight": "bold", "font": "title-font"},
    {"slide": "bar-chart", "field": "bullets", "width": "230mm", "height": "200mm", "item": "40mm", "size": "size-body", "weight": "regular", "font": "body-font"}
  ]
}
```

Откуда числа (пересказать в сообщении коммита): страница 677mm, поля 30+30; на титульном слайде колонка текста уже на стрелку 47mm и gutter 18mm → 552mm, высоты — аргументы `slot()` адаптера; у содержательных слайдов тело — `body-box` высотой 250mm, колонка тезисов `image` — (617−15)×58% ≈ 349mm, `chart` и `bar-chart` — (617−12)×38% ≈ 230mm.

- [ ] **Step 5: Имя шрифта в каноне**

```bash
C=~/projects/lmru--hr-analytics--design-template
sed -i 's|("TT Interphases Pro Trl", "Liberation Sans")|("TT Interphases Pro", "TT Interphases Pro Trl", "Liberation Sans")|' $C/templates/typst/slides_template.typ
grep -n "title-font =\|body-font =" $C/templates/typst/slides_template.typ
```
Expected: обе строки начинаются с `("TT Interphases Pro", …`.

В `$C/CLAUDE.md` и `$C/AGENTS.md` (файлы-двойники) строку `- **Typst-деки** (\`templates/typst/\`) — шрифт **TT Interphases Pro Trl**` исправить на `… — шрифт **TT Interphases Pro** (так называется семейство в TTF из references/TTInterphasesPro.zip; «…Pro Trl» — имя пробной версии, оставлено запасным)`. В конец раздела «Typst-шаблон (templates/typst/)» обоих файлов добавить абзац:

```markdown
### Шаблон для typst-deck

Корень этого репозитория — корень шаблона typst-deck: `deck.typ` и
`template.json` в корне, адаптер, шрифты и геометрия замера — в `typst-deck/`.
Контракт — `docs/template-contract.md` в репозитории typst-deck. Правка канона,
меняющая функции `title-slide`, `content-slide`, `divider-slide-*` или
`conclusion-slide`, проверяется командой
`uv run --project ~/projects/typst-deck python -m typst_deck.templates .`
```

- [ ] **Step 6: Полный контракт**

Run: `uv run --project ~/projects/typst-deck python -m typst_deck.templates ~/projects/lmru--hr-analytics--design-template`
Expected: `lmru--hr-analytics--design-template: контракт соблюдён`; предупреждения о запасных `tt interphases pro trl` и `liberation sans` допустимы.

- [ ] **Step 7: Вёрстка не изменилась**

```bash
cd ~/projects/typst-deck && uv run python - <<'PY'
import pathlib, tempfile
from typst_deck.contract import SAMPLE_DECK
from typst_deck.render import compile_deck, resolve_fonts
canon = pathlib.Path.home() / "projects/lmru--hr-analytics--design-template"
with tempfile.TemporaryDirectory() as t:
    t = pathlib.Path(t)
    a = compile_deck(SAMPLE_DECK, t / "old", pathlib.Path("templates/lmru-hr"))
    b = compile_deck(SAMPLE_DECK, t / "new", canon, fonts_dir=resolve_fonts(canon, "typst-deck/fonts"))
    diff = [i + 1 for i, (x, y) in enumerate(zip(a.pages, b.pages)) if x != y]
    print("страниц:", len(a.pages), len(b.pages), "| различаются:", diff or "нет")
PY
```
Expected: `страниц: 6 6 | различаются: нет`. Если страницы различаются — остановиться и сообщить номера: перенос не должен менять вёрстку.

- [ ] **Step 8: Замер воспроизводит объявление**

```bash
cd ~/projects/typst-deck && uv run python - <<'PY'
import json, pathlib, subprocess, sys
from typst_deck.slots import clamp
canon = pathlib.Path.home() / "projects/lmru--hr-analytics--design-template"
r = subprocess.run([sys.executable, "scripts/measure_slots.py", str(canon)], capture_output=True, text=True, check=True)
measured = clamp(json.loads(r.stdout)["slots"], "замер")
declared = clamp(json.loads((canon / "template.json").read_text())["slots"], "объявление")
print("совпадает" if measured == declared else f"РАСХОДИТСЯ:\nзамер {measured}\nобъявлено {declared}")
PY
```
Expected: `совпадает`. Расхождение — остановиться и сообщить: значит, `measure.json` перенесён неточно.

- [ ] **Step 9: Демо канона по-прежнему собирается**

Run: `cd ~/projects/lmru--hr-analytics--design-template/templates/typst && typst compile --root ../.. demo.typ /tmp/canon-demo.pdf && echo ok`
Expected: `ok`.

- [ ] **Step 10: Коммит в каноне**

```bash
C=~/projects/lmru--hr-analytics--design-template
git -C $C add deck.typ template.json typst-deck templates/typst/slides_template.typ CLAUDE.md AGENTS.md
git -C $C commit -m "feat(typst-deck): корень репозитория — шаблон typst-deck

Адаптер семи функций контракта typst-deck, распакованные TT Interphases Pro
и геометрия замера ёмкости слотов — в typst-deck/, точки входа deck.typ и
template.json — в корне. Канон подключается как есть: lm-components-dir
разрешается внутри корня. Первым семейством шрифта теперь стоит настоящее
«TT Interphases Pro» — «…Pro Trl» из пробной версии в архиве нет, и любой
потребитель канона молча получал Liberation Sans.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: typst-deck без `lmru-hr`

**Files:**
- Delete: `templates/lmru-hr/` (весь каталог, включая неотслеживаемую копию канона), `scripts/sync-lmru-template.sh`
- Modify: `.gitignore`, `Dockerfile` (комментарий), `scripts/dev.sh`
- Modify: `tests/conftest.py` (`CORP_PARAMS`), `tests/test_compile.py`, `tests/test_slots.py`, `tests/test_charts.py`, `tests/test_agent.py`, `tests/test_api.py`, `tests/test_model.py`
- Create: `tests/test_corporate.py`
- Вне репозитория: `~/corp-templates/lemana-tech` → ссылка на канон

**Interfaces:**
- Consumes: `check_template`, `filled_slide` (задача 3); канон из задачи 7.
- Produces: `tests/conftest.py`: `NO_CORP: str`, `CORP_PARAMS: list` — параметры `pytest.param(TemplateInfo, id=...)`.

- [ ] **Step 1: Ссылка на канон для локальной работы**

```bash
mkdir -p ~/corp-templates
ln -sfn ~/projects/lmru--hr-analytics--design-template ~/corp-templates/lemana-tech
ls -l ~/corp-templates
```

- [ ] **Step 2: Корпоративные шаблоны в тестах**

В `tests/conftest.py` (импорт `os` добавить в блок):

```python
NO_CORP = ("нет корпоративных шаблонов: задайте TYPST_DECK_TEST_TEMPLATES "
           "(корни через «:», как TYPST_DECK_TEMPLATES_DIR)")


def corp_templates() -> list:
    """Корпоративные шаблоны для общих тестов — все шаблоны корней из TYPST_DECK_TEST_TEMPLATES."""
    raw = os.environ.get("TYPST_DECK_TEST_TEMPLATES", "")
    if not raw:
        return []
    from typst_deck.templates import TemplateRegistry

    roots = [Path(p).expanduser() for p in raw.split(os.pathsep) if p]
    return [t for t in TemplateRegistry(TEMPLATE_DIR, roots).list() if t.id != "default"]


CORP_PARAMS = ([pytest.param(t, id=t.id) for t in corp_templates()]
               or [pytest.param(None, id="no-corp", marks=pytest.mark.skip(reason=NO_CORP))])
```

- [ ] **Step 3: Общие корпоративные тесты**

Создать `tests/test_corporate.py`:

```python
"""Общие тесты корпоративных шаблонов: те же проверки для каждого шаблона из
TYPST_DECK_TEST_TEMPLATES. Раньше они были прибиты к templates/lmru-hr; теперь
корпоративный шаблон живёт в репозитории своего канона (docs/template-contract.md).
На этом сервере: TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest
"""
import json

import pytest

from tests.conftest import CORP_PARAMS, requires_typst
from tests.test_charts import signed_deck
from typst_deck.contract import check_template, filled_slide
from typst_deck.model import Deck
from typst_deck.render import compile_deck
from typst_deck.slots import check_slide, clamp

MM = 2.83465  # мм в пунктах: зоны заданы в мм, positions отдаёт пункты


@requires_typst
@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_template_passes_the_full_contract(t, tmp_path):
    assert check_template(t.path, "typst", tmp_path).errors == []


@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_declaration_survives_clamp_unchanged(t):
    raw = json.loads((t.path / "template.json").read_text()).get("slots") or {}
    assert clamp(raw, t.id) == raw


@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_rejects_the_2026_09_09_incident(t):
    """Переводы строки в подзаголовке титульного слайда сверх объявленного — отказ до рендера."""
    lines = t.slots.get("title", {}).get("subtitle", {}).get("lines")
    if lines is None:
        pytest.skip(f"{t.id}: у подзаголовка титульного слайда не объявлено lines")
    bad = Deck(slides=[{"type": "title", "title": "Итоги",
                        "subtitle": "Лемана" + "\n" * lines + "хвост"}]).slides[0]
    assert check_slide(bad, t.slots, n=1, template_name=t.name)
    ok = Deck(slides=[{"type": "title", "title": "Итоги",
                       "subtitle": "\n".join(["Лемана"] * lines)}]).slides[0]
    assert check_slide(ok, t.slots, n=1, template_name=t.name) == []


@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_every_declared_limit_is_enforced(t):
    for stype, fields in t.slots.items():
        for fld, lim in fields.items():
            for key, value in lim.items():
                over = dict(lim)
                over[key] = value + 1
                try:
                    slide = Deck(slides=[filled_slide(stype, {fld: over})]).slides[0]
                except ValueError:
                    continue  # сверх глобального потолка model.py — его держит валидация модели
                assert check_slide(slide, t.slots, n=1, template_name=t.name), f"{stype}.{fld}.{key}"


@requires_typst
@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_declared_text_fits_its_measured_zone(t, tmp_path):
    """Текст ровно по объявленным пределам не выше зоны, в которой его меряли (measure.json).
    Обрезку внутри слота правило «одна страница» не видит, а этот тест видит."""
    meta = json.loads((t.path / "template.json").read_text())
    if not meta.get("measure"):
        pytest.skip(f"{t.id}: нет measure")
    cfg = json.loads((t.path / meta["measure"]).read_text())
    for i, p in enumerate(cfg["probes"]):
        lim = t.slots.get(p["slide"], {}).get(p["field"])
        if not lim:
            continue
        slide = filled_slide(p["slide"], {p["field"]: lim}, sample=cfg.get("sample", "Итоги квартала "))
        r = compile_deck(Deck(slides=[slide]), tmp_path / f"p{i}", t.path, fonts_dir=t.fonts)
        h = next(x["h"] for x in r.positions if x["field"] == p["field"])
        zone = float(p["height"].removesuffix("mm")) * MM
        assert h <= zone, f"{p['slide']}.{p['field']}: {h:.1f}pt при зоне {zone:.1f}pt"


@requires_typst
@pytest.mark.parametrize("t", CORP_PARAMS)
def test_corp_signed_charts_keep_one_page_per_slide(t, deck_dir):
    assert len(compile_deck(signed_deck(), deck_dir, t.path, fonts_dir=t.fonts).svgs) == 2
```

- [ ] **Step 4: Убрать тесты, прибитые к `lmru-hr`**

- `tests/test_compile.py`: удалить `test_title_slide_survives_many_line_breaks`, `test_lmru_long_title_fits_the_slot_instead_of_being_clipped`, `test_lmru_text_at_declared_limits_fits_on_one_page` — их заменили правила 3 и 5 контракта и `test_corp_declared_text_fits_its_measured_zone`.
- `tests/test_slots.py`: удалить `test_lmru_declaration_rejects_the_2026_09_09_incident`, `_lmru_declared`, `test_lmru_bar_chart_bullets_over_capacity_are_rejected` — их заменили `test_corp_rejects_the_2026_09_09_incident` и `test_corp_every_declared_limit_is_enforced`.
- `tests/test_charts.py`: из `TEMPLATES` убрать строку `"lmru-hr"`, `compile_in` упростить до

  ```python
  def compile_in(tid, deck_dir):
      path, pos, neg = TEMPLATES[tid]
      return compile_deck(signed_deck(), deck_dir, path), pos, neg
  ```
- `tests/test_agent.py`: id `"lmru-hr"` заменить на `"corp"` во всех девяти местах (имена шаблонов вроде `"Lemana Tech"` — оставить: это просто строки).
- `tests/test_api.py`: комментарий в `test_templates_history_and_template_choice` — «только шаблоны из git: корпоративные подключаются монтированием, их проверяют tests/test_corporate.py и сервис при старте».
- `tests/test_model.py`: в докстринге `test_title_slide_has_author_and_department` — «Канон Lemana Tech верстает…».

- [ ] **Step 5: Удалить копию канона и скрипт синхронизации**

```bash
git rm -q -r templates/lmru-hr scripts/sync-lmru-template.sh
rm -rf templates/lmru-hr   # неотслеживаемая копия канона: источник теперь — сам канон (задача 7)
ls templates               # ожидаем только dark
```

`.gitignore` — удалить блок из пяти строк, начинающийся с `# Корпоративный шаблон Lemana Tech: канон…`, вместе с правилами `templates/lmru-hr/*` и `!templates/lmru-hr/…`.

`Dockerfile` — комментарий перед `RUN python -m typst_deck.templates` заменить на:

```dockerfile
# Встроенные шаблоны (default, dark) проверяются по контракту при сборке. Корпоративные
# в образ не попадают: их монтируют при запуске, и сервис проверяет их при старте.
```

`scripts/dev.sh` — перед строкой `exec uv run uvicorn …`:

```bash
# корпоративные шаблоны — ссылки в ~/corp-templates на репозитории канонов (docs/template-contract.md)
export TYPST_DECK_TEMPLATES_DIR="${TYPST_DECK_TEMPLATES_DIR:-templates:$HOME/corp-templates}"
```

- [ ] **Step 6: Прогнать оба режима тестов**

Run: `uv run pytest -q && TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest -q && uv run python -m typst_deck.templates`
Expected: первый прогон — зелёный, корпоративные тесты `SKIPPED` с причиной `NO_CORP`; второй — зелёный и без пропусков в `tests/test_corporate.py`; третья команда — «каждый шаблон соблюдает контракт» (default, dark).

- [ ] **Step 7: Коммит**

```bash
git add -A tests .gitignore Dockerfile scripts/dev.sh
git commit -m "Корпоративный шаблон уходит из продукта: общие тесты вместо прибитых к lmru-hr"
```

---

### Task 9: контракт и README

**Files:**
- Create: `docs/template-contract.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: всё из задач 1–8.
- Produces: документ для автора шаблона.

- [ ] **Step 1: Контракт**

Создать `docs/template-contract.md`:

~~~~markdown
# Контракт шаблона typst-deck

Как сделать шаблон, который typst-deck подключит без правок кода. Эталон —
`template/` в этом репозитории: каждое правило ниже в нём выполнено, и когда
непонятно, как сделать, — смотрите туда.

## Шаблон — это каталог

Корень шаблона — каталог, который typst-deck видит в песочнице сборки как
`/template`. Всё, что шаблон импортирует, рисует и чем набирает текст, лежит
внутри него. Ссылка, ведущая наружу, локально сработает, а в контейнере нет:
туда шаблон попадает монтированием, и цели ссылки там не будет.

Корпоративный шаблон — это корень репозитория его канона. Всё, что относится к
typst-deck, лежит в папке `typst-deck/`, в корне только две точки входа:

```
<репозиторий канона>/
├── deck.typ          #import "typst-deck/adapter.typ": *
├── template.json
├── typst-deck/
│   ├── adapter.typ   семь функций контракта поверх канона
│   ├── fonts/        TTF/OTF
│   └── measure.json  геометрия слотов для замера
└── …канон как есть
```

## deck.typ

Экспортирует семь функций — ровно с такими параметрами:

```typst
#let deck(title: none, body)
#let slide-title(title: none, subtitle: none, author: none, department: none)
#let slide-section(title: none, subtitle: none)
#let slide-image(title: none, bullets: none, image: none, image-size: "medium", caption: none)
#let slide-bar-chart(title: none, data: (), unit: none, bullets: none)
#let slide-chart(title: none, labels: (), series: (), unit: none, bullets: none)
#let slide-final(title: none, contact: none)
```

**Одна функция слайда — ровно одна страница.** Лишний текст обрезается
(`box(clip: true)`), а не переносится на следующую страницу: typst-deck сверяет
число страниц с числом слайдов и называет слайд, который вылез.

**Параметры.** `title`, `subtitle`, `author`, `department`, `caption`,
`contact`, `bullets` приходят как content — уже обёрнутые в маркер поля, по
которому работает правка по клику, — или `none`. Выводите их как есть и не
делайте над ними строковых операций. `bullets` — готовый список. `image` —
content или `none`. `data`, `labels`, `series` — сырые массивы и словари:
графики шаблон рисует сам, падение — другим цветом, чем рост. Пакеты
`@preview` не используйте: у корпоративной сети может не быть доступа к реестру.

**Автор и подразделение** — отдельные блоки подписи, сначала человек, потом
подразделение.

## template.json

| поле | обязательно | смысл |
|---|---|---|
| `name` | да | имя в интерфейсе |
| `description` | нет | подпись в «Моих шаблонах» |
| `fonts` | нет | каталог шрифтов от корня; по умолчанию `fonts` |
| `measure` | нет | файл геометрии слотов для замера |
| `slots` | нет | ёмкость слотов |

## Шрифты

TTF/OTF — в каталоге из поля `fonts`. Семейства, которые называет шаблон,
обязаны совпадать с семействами внутри файлов (посмотреть: `fc-scan --format
"%{family}\n" файл.ttf`). Запасные семейства в списке допустимы: typst
предупредит о каждом ненайденном, это не ошибка. Ошибка — когда шрифты шаблона
не используются вовсе.

## Ёмкость слотов

Раздел `slots` объявляет, сколько вмещает каждое поле каждого типа слайда.
Пределы доходят до модели в схеме и проверяются при каждой правке. Объявление
может только сузить глобальные пределы typst-deck (120 знаков заголовка, 200 —
тезиса, 6 тезисов на `image`, 4 — на графиках), не расширить.

| ключ | смысл | применим к |
|---|---|---|
| `max` | знаков | строковым полям и спискам строк (`bullets`, `labels`) |
| `lines` | явных строк (`\n` + 1) | строковым полям |
| `count` | элементов | спискам (`bullets`, `labels`, `data`, `series`) |

Пределы не угадываются, а меряются настоящим шрифтом:

```sh
uv run --project ~/projects/typst-deck python ~/projects/typst-deck/scripts/measure_slots.py <корень шаблона>
```

Скрипт печатает готовый раздел `slots`. Геометрию он берёт из `measure.json`:

```json
{
  "import": "templates/typst/slides_template.typ",
  "sample": "Итоги квартала по направлению данных и аналитики ",
  "list": "#set list(spacing: 0.7em)",
  "probes": [
    {"slide": "title", "field": "title", "width": "552mm", "height": "60mm",
     "size": "size-title", "weight": "bold", "font": "title-font"},
    {"slide": "image", "field": "bullets", "width": "349mm", "height": "250mm", "item": "40mm",
     "size": "size-body", "weight": "regular", "font": "body-font"}
  ]
}
```

- `import` — файл, после импорта которого `size`, `font` и оформление списка
  становятся выражениями Typst; путь от корня шаблона;
- `width` и `height` — зона поля в вёрстке, в мм;
- `item` есть только у списков: высота одного элемента, на которую меряется
  `max`; `count` меряется списком целиком, с интервалами между элементами;
- `list` — копия `#set list(...)` из вашего `deck()`; держите её в шаге с ним.

Автоподбор кегля в зонах заголовков (приём `fit-text` из эталона) —
рекомендация: пределы приблизительны, широкие знаки всё равно вылезают.

## Проверка

```sh
uv run --project ~/projects/typst-deck python -m typst_deck.templates <корень шаблона>
```

Шесть правил; нарушение любого — ошибка:

1. есть `deck.typ` и `template.json` с `name`, `slots` проходят без единого
   отброшенного ключа;
2. образец — по слайду каждого типа — собирается, страниц столько же, сколько
   слайдов;
3. переросший текст и восемь переводов строки в титульном, разделительном и
   финальном слайдах не выносят слайд на вторую страницу;
4. у каждого текстового поля образца есть маркер правки;
5. слайды, заполненные ровно по объявленным пределам, собираются по одному на
   страницу;
6. шрифты из каталога шаблона используются: образец без системных шрифтов с
   этим каталогом и без него собирается по-разному.

При старте сервис проверяет каждый подключённый шаблон мягче. Сломанным
считается только шаблон, который не может работать (правила 1 — файлы — и 2):
он скрыт из выбора, а колоды на нём получают понятную ошибку. Правило 6 и
отброшенные ключи `slots` — предупреждения в `/api/health`.

## Подключение

Id шаблона — имя каталога, под которым реестр видит его корень.

На сервере корень монтируется только на чтение, вторым корнем шаблонов:

```ini
# ~/stack/quadlet/typst-deck.container
Volume=%h/projects/<канон>:/corp/<id>:ro
Environment=TYPST_DECK_TEMPLATES_DIR=/app/templates:/corp
```

Локально — ссылкой: `ln -sfn ~/projects/<канон> ~/corp-templates/<id>`;
`scripts/dev.sh` подключает `~/corp-templates` сам.

Сменили id — задайте алиас, пока внешние вызовы помнят старый:
`TYPST_DECK_TEMPLATE_ALIASES=старый:новый`. Колоды переносит
`python -m typst_deck.migrate_template старый новый` (при остановленном
сервисе).
~~~~

- [ ] **Step 2: README**

- Раздел «Шаблон Lemana Tech (`templates/lmru-hr`)» вместе с подразделом «Ёмкость слотов» и раздел «Подключение корпоративного шаблона» заменить одним разделом:

  ```markdown
  ## Корпоративные шаблоны

  В образе и в этом репозитории — только встроенные шаблоны `default`
  (`template/`, он же эталон контракта) и `dark`. Корпоративный шаблон живёт в
  репозитории своего канона и подключается монтированием: как сделать
  совместимый шаблон, проверить его и подключить — `docs/template-contract.md`.

  На этом сервере подключён Lemana Tech (`lemana-tech`) из
  `~/projects/lmru--hr-analytics--design-template`. Старый id `lmru-hr`
  разрешается алиасом `TYPST_DECK_TEMPLATE_ALIASES`.

  Ёмкость слотов (`slots` в `template.json`) доходит до модели в схеме и
  проверяется при каждой правке — чата и панели свойств одинаково. Пределы
  меряет `scripts/measure_slots.py <корень шаблона>` по геометрии из
  `measure.json` шаблона.
  ```
- В разделе про контейнер абзац, который начинается словами «В образ попадает `templates/` с хоста целиком…», заменить на:

  ```markdown
  В образ попадают только встроенные шаблоны: на последнем шаге сборки
  `python -m typst_deck.templates` проверяет их по контракту, и `podman build`
  падает, если какой-то его нарушил. Образ не содержит корпоративных файлов и
  может публиковаться. Корпоративный шаблон монтируется при запуске вторым
  корнем: `-v ~/projects/<канон>:/corp/<id>:ro -e TYPST_DECK_TEMPLATES_DIR=/app/templates:/corp`.
  ```
- В разделе «Запуск» строку `uv run pytest …` заменить на две:

  ```sh
  uv run pytest                                           # встроенные шаблоны; корпоративные тесты пропускаются
  TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest  # плюс общие тесты корпоративных шаблонов
  ```
- В разделе «Демо на этом сервере» в пункт про Quadlet-юнит добавить монтирование канона и `TYPST_DECK_TEMPLATE_ALIASES=lmru-hr:lemana-tech`.

- [ ] **Step 3: Проверить ссылки и упоминания**

Run: `grep -n "lmru-hr\|sync-lmru" README.md docs/template-contract.md`
Expected: только алиас `lmru-hr` в README; `sync-lmru` — нигде.

- [ ] **Step 4: Коммит**

```bash
git add docs/template-contract.md README.md
git commit -m "Контракт шаблона — инструкция для автора корпоративного шаблона"
```

---

### Task 10: выкатка (выполняет координатор, не субагент)

Затрагивает живой сервис и `~/stack`; выполнять только после зелёных задач 1–9.

- [ ] **Step 1: Финальные прогоны**

Run: `uv run pytest -q && TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest -q`
Expected: оба зелёные.

- [ ] **Step 2: Образ с меткой отката**

```bash
podman tag localhost/typst-deck:latest localhost/typst-deck:pre-corp
podman build -t localhost/typst-deck:latest -t localhost/typst-deck:corp ~/projects/typst-deck
```

- [ ] **Step 3: Остановить и перенести колоды**

```bash
systemctl --user stop typst-deck
podman run --rm -v typst-deck-data:/data localhost/typst-deck:corp python -m typst_deck.migrate_template lmru-hr lemana-tech
```
Expected: `lmru-hr → lemana-tech: колод 2 (…)`.

- [ ] **Step 4: Юнит с монтированием канона**

В `~/stack/quadlet/typst-deck.container`, в секцию `[Container]`, после строки `Volume=typst-deck-data.volume:/data`:

```ini
# корпоративный шаблон Lemana Tech — корень репозитория канона, только чтение (docs/template-contract.md в typst-deck)
Volume=%h/projects/lmru--hr-analytics--design-template:/corp/lemana-tech:ro
Environment=TYPST_DECK_TEMPLATES_DIR=/app/templates:/corp
# бот мог зашить прежний id шаблона
Environment=TYPST_DECK_TEMPLATE_ALIASES=lmru-hr:lemana-tech
```

```bash
cp ~/stack/quadlet/typst-deck.container ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start typst-deck
systemctl --user is-active typst-deck
```

- [ ] **Step 5: Проверка на живом сервисе**

```bash
for i in $(seq 1 40); do c=$(curl -s 127.0.0.1:8088/api/health | python3 -c "import json,sys; print(json.load(sys.stdin)['templates']['checked'])"); [ "$c" = True ] && break; sleep 0.5; done
curl -s 127.0.0.1:8088/api/health | python3 -m json.tool | sed -n '/templates/,$p'
curl -s 127.0.0.1:8088/api/templates
for id in $(curl -s 127.0.0.1:8088/api/decks | python3 -c "import json,sys; print(' '.join(d['id'] for d in json.load(sys.stdin)))"); do
  curl -s 127.0.0.1:8088/api/decks/$id | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['deck']['id'], d['deck']['template'], d['template']['name'])"
  curl -s -o /dev/null -w "PDF %{http_code}\n" 127.0.0.1:8088/api/decks/$id/deck.pdf
done
```
Expected: `checked: true`, `broken: {}`, в `/api/templates` есть `lemana-tech` и нет `lmru-hr`; обе колоды — `lemana-tech`, «Lemana Tech», PDF 200 (PDF собирается заново со шрифтами из смонтированного канона).

- [ ] **Step 6: Документация стека и коммит**

В `~/stack/quadlet/README.md`, в список «Грабли…», добавить пункт:

```markdown
- Корпоративный шаблон typst-deck монтируется из репозитория канона только на
  чтение (`Volume=…:/corp/<id>:ro`) — в образе его нет. Правка канона
  подхватывается рестартом юнита, пересборка образа не нужна.
```

```bash
git -C ~/stack add quadlet/typst-deck.container quadlet/README.md
git -C ~/stack commit -m "typst-deck: корпоративный шаблон монтируется из репозитория канона

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Откат (только если шаг 5 не прошёл)**

```bash
systemctl --user stop typst-deck
podman run --rm -v typst-deck-data:/data localhost/typst-deck:corp python -m typst_deck.migrate_template lemana-tech lmru-hr
podman tag localhost/typst-deck:pre-corp localhost/typst-deck:latest
git -C ~/stack checkout -- quadlet/typst-deck.container && cp ~/stack/quadlet/typst-deck.container ~/.config/containers/systemd/
systemctl --user daemon-reload && systemctl --user start typst-deck
```
