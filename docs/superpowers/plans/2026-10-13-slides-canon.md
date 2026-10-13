# Набор слайдов, план D — канон Lemana Tech и выкатка одним окном

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** канон Lemana Tech рисует все 15 типов слайдов по одной странице и экспортирует их в PPTX на своём мастере, его пределы слотов замерены; затем ветка `slides-v2` вливается в `main` и вместе с каноном и переносом колод выкатывается одним окном.

**Architecture:** вся правка канона идёт в git worktree канона на ветке `slides-v2` (`~/projects/lemana-canon-slides-v2`) — живой каталог канона смонтирован в прод и до окна выкатки не меняется. Адаптер `typst-deck/adapter.typ` получает 9 новых функций и переделку графиков; простые типы собираются на `content-slide` канона с ограниченным телом, графики, таблица, метрики, галерея и видео переносятся с эталона `template/deck.typ` по таблице соответствия масштаба и токенов. Корпоративные тесты typst-deck гоняются по worktree канона через отдельный корень `~/corp-templates-next`.

**Tech Stack:** Typst 0.15.1, канон Lemana Tech (`templates/typst/slides_template.typ`), python-pptx, pytest, podman/systemd (выкатка).

**Spec:** `docs/superpowers/specs/2026-09-13-slide-set-design.md` (§6 — контракт, §7 — PPTX и раскладка Lemana, §9 — тесты и проверка вёрстки, §10 — выкатка одним окном). Решения: ADR 0016 «канон — это прод», ADR 0022 «видео — ссылкой» (в `main`, `docs/adr/`).

## Global Constraints

- **Живой канон `~/projects/lmru--hr-analytics--design-template` не трогать до задачи 8.** Он смонтирован в прод (ADR 0016): любая правка файла сразу видна пользователям. Вся работа — в worktree `~/projects/lemana-canon-slides-v2` (ветка `slides-v2` репозитория канона).
- В typst-deck работа идёт в `.worktrees/slides-v2`. Корпоративные тесты: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next uv run pytest -q tests/test_corporate.py`; общий набор — без этой переменной, 482 passed, 8 skipped.
- Контракт: `deck` и 15 функций слайдов с сигнатурами спеки §6; одна функция — ровно одна страница; переполнение обрезается; маркер поля у каждого текстового значения пропускается как есть (не строковать content).
- Канон не правится: только `deck.typ`, `template.json` и папка `typst-deck/` (ADR 0011). Компоненты канона используются как есть; где канон рисует страницу без обрезки (agenda-slide, metrics-slide, gallery-slide, comparison-slide), адаптер собирает тип сам на `content-slide` с телом `body-box`.
- Пределы — замером (`scripts/measure_slots.py`), ниже обрыва на 10–15 % (правило запаса из ADR 0010); объявление в `template.json` только сужает глобальные пределы модели.
- **Выкатка (задача 8) — только с явного «да» пользователя на каждом шаге, который трогает прод:** слияние в `main`, `git push`, остановка сервиса, перемотка канона, перенос колод, новый образ, запуск. До этого — подготовка и проверки без побочных эффектов.
- Коммиты в обоих репозиториях заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; сообщения в репозитории канона — в его стиле (`feat(typst-deck): …`).

## Отклонения от спеки, принятые при планировании

1. **Эталон не импортируется** (спека §2 разрешает «импортировать эталонные функции»): эталон лежит в репозитории typst-deck, вне корня шаблона, и в контейнере его нет. Функции переносятся в адаптер с пересчётом масштаба.
2. **`bar-chart` уходит из адаптера:** тип снят в плане A; `slide-chart` получает `kind` и несколько рядов.
3. **Вложенные пределы мерятся тем же `measure_slots.py`:** имя поля в пробе (`blocks.text`, `left.bullets`, `rows`) для скрипта — подпись, нужны только ширина и высота зоны. Скрипт не меняется.

## Таблица переноса эталона (задачи 3–4)

Эталон `template/deck.typ` свёрстан на странице 160×90 мм, канон — 677×381 мм. При переносе функции:

| в эталоне | в адаптере |
|---|---|
| `accent` | `lm-yellow` (рост, акцент) |
| `ink` | `lm-dark` |
| `muted` | `lm-gray` |
| `negative` | `lm-red` |
| `palette` | `chart-palette` (уже есть: жёлтый, тёмный, бирюзовый, светло-коричневый) |
| `paper` | `lm-white` |
| длины в `cm`, `mm`, `pt` у геометрии (отступы, высоты зон, зазоры, радиусы, толщины линий) | × `K`, где `#let K = 677 / 160` |
| кегль 19pt / 15pt (заголовок) | `size-h1-compact` / `40pt` |
| кегль 11pt (текст) | `size-body` |
| кегль 10pt, 9pt, 8pt (подписи) | `size-caption` |
| лестница 8pt…4pt (подписи категорий) | `(24pt, 20pt, 18pt, 16pt, 14pt, 12pt)` |
| `slide[…]` + `heading-block(title)` | `cs(title, […])` (задача 2) |
| `body-h`, `body-bottom` | `body-height` (250mm) и низ тела `cs` |

Перенос считается сделанным, когда тест типа из задачи 1 зелёный и замер задачи 7 не находит содержимого ниже низа тела.

## Review Focus

1. **Длинный заголовок на новых типах** (120 знаков, две строки 48pt) — тело не съезжает под логотип и номер: зона заголовка фиксирована (`title-zone`), тело — `body-box`. Тест — задача 1 (`test_corp_type_at_declared_limits_stays_on_the_page`).
2. **Цитата без автора и метрика без подписи/изменения** — пустые части не оставляют «дыр» и не ломают вертикальное центрирование. Тест — задача 1 (минимальные слайды каждого типа).
3. **График: одна категория, все значения нулевые, только отрицательные, 4 ряда** — одна страница, подписи не под обрезом (вырожденный размах эталона перенесён). Тест — задача 3.
4. **PPTX на настоящем мастере:** каждое сопоставление `pptx.json` проходит `open_master` (макет и idx есть), блоки на «Блоках текста» не тянут маркер уровня 1. Тест — задача 6; маркер — ручная приёмка.
5. **Выкатка:** колоды прода после `migrate_slides` собираются на новом каноне без предупреждений; откат возвращает и образ, и канон, и том. Проверка — задача 8 (сухой прогон на копии тома до окна).

---

### Task 1: Worktree канона, корень тестов и тесты на каждый тип

**Files (typst-deck, ветка `slides-v2`):**
- Modify: `tests/test_corporate.py`

**Files (вне репозиториев):**
- Create: worktree `~/projects/lemana-canon-slides-v2` (ветка `slides-v2` канона)
- Create: `~/corp-templates-next/lemana-tech` → ссылка на worktree

**Interfaces:**
- Produces: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next` — корень с шаблоном `lemana-tech` из worktree; тесты `test_corp_type_compiles_on_one_page[lemana-tech-<тип>]` и `test_corp_type_at_declared_limits_stays_on_the_page[lemana-tech-<тип>]`.

- [ ] **Step 1: Worktree и корень**

```sh
C=~/projects/lmru--hr-analytics--design-template
git -C $C status --short          # пусто: живой канон чист
git -C $C worktree add ~/projects/lemana-canon-slides-v2 -b slides-v2
mkdir -p ~/corp-templates-next
ln -s ~/projects/lemana-canon-slides-v2 ~/corp-templates-next/lemana-tech
```

Id шаблона — имя ссылки (`lemana-tech`), как в проде.

- [ ] **Step 2: Тесты на каждый тип** — в `tests/test_corporate.py`:

```python
from typst_deck.model import SLIDE_TYPES

TYPE_PARAMS = [pytest.param(t, s, id=f"{p.id}-{s}") for p in CORP_PARAMS for t in p.values if t is not None
               for s in SLIDE_TYPES] or [pytest.param(None, None, id="no-corp", marks=pytest.mark.skip(reason=NO_CORP))]
PAGE_BOTTOM_MM = 381 - 24  # низ поля content-slide канона: ниже — логотип и номер


@requires_typst
@pytest.mark.parametrize("t,stype", TYPE_PARAMS)
def test_corp_type_compiles_on_one_page(t, stype, tmp_path):
    """Минимальный слайд каждого типа — одна страница: функция контракта есть и не переносит."""
    from typst_deck.contract import write_sample_assets

    write_sample_assets(tmp_path)
    slide = next(s for s in SAMPLE_DECK.slides if s.type == stype)
    r = compile_deck(Deck(slides=[slide]), tmp_path, t.path, fonts_dir=t.fonts)
    assert len(r.svgs) == 1


@requires_typst
@pytest.mark.parametrize("t,stype", TYPE_PARAMS)
def test_corp_type_at_declared_limits_stays_on_the_page(t, stype, tmp_path):
    """Слайд по объявленным пределам шаблона (а без объявления — по глобальным модели):
    ни одно поле не уходит ниже поля страницы — обрезку clip правило «одна страница» не видит."""
    from typst_deck.contract import write_sample_assets

    write_sample_assets(tmp_path)
    slide = filled_slide(stype, t.slots.get(stype, {}))
    r = compile_deck(Deck(slides=[slide]), tmp_path, t.path, fonts_dir=t.fonts)
    assert len(r.svgs) == 1
    worst = max((p["y"] + p["h"] for p in r.positions), default=0)
    assert worst <= PAGE_BOTTOM_MM * MM, f"{stype}: низ {worst / MM:.1f} мм при поле {PAGE_BOTTOM_MM} мм"
```

`NO_CORP` — импортировать из `tests.conftest` вместе с `CORP_PARAMS`.

- [ ] **Step 3: Базовая линия**

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next uv run pytest -q tests/test_corporate.py 2>&1 | tail -25`
Expected: FAIL — `unknown variable: slide-agenda` и прочие новые типы, `bar-chart` в `slots`, `pptx.json` без новых типов. Записать в журнал список упавших тестов: это объём работы задач 2–6.

- [ ] **Step 4: Коммит (typst-deck)**

```bash
git add tests/test_corporate.py
git commit -m "Корпоративные тесты: каждый тип — одна страница и в поле страницы на пределах

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Адаптер — общая основа и текстовые типы

**Files (канон, worktree):**
- Modify: `typst-deck/adapter.typ`

**Interfaces:**
- Produces: `cs(title, body)` — страница `content-slide` канона с зоной заголовка `title-zone` и телом `body-box`; `K`; функции `slide-agenda`, `slide-text`, `slide-columns`, `slide-comparison`, `slide-quote`.
- Consumes: из канона `content-slide`, `lm-*`, `size-*`, `title-font`, `body-font`; из адаптера `num`, `or-empty`, `body-box`, `fit-text`, `title-zone`.

- [ ] **Step 1: Тесты задачи** — уже написаны в задаче 1.

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next uv run pytest -q tests/test_corporate.py -k "agenda or -text] or columns or comparison or quote"`
Expected: FAIL — функций нет.

- [ ] **Step 2: Общая основа** — в `adapter.typ` после `body-box`:

```typst
#let K = 677 / 160  // масштаб эталона typst-deck (160×90 мм) к странице канона

// Страница содержимого: заголовок в фиксированной зоне, тело — обрезанный box.
#let cs(title, body) = content-slide(
  title: or-empty(title), slide-number: num, title-size: size-h1-compact, title-height: title-zone,
  body-box(body),
)
```

`slide-image` и `slide-chart` перевести на `cs` (поведение то же).

- [ ] **Step 3: Текстовые типы**

```typst
#let slide-text(title: none, bullets: none) = cs(title, if bullets != none { bullets })

// Повестка: номера серым жирным — как agenda-slide канона, но в зоне тела с обрезкой.
#let slide-agenda(title: none, items: ()) = cs(title, {
  for (i, it) in items.enumerate() {
    grid(columns: (22mm, 1fr), column-gutter: 4mm,
      text(fill: lm-gray, weight: "bold")[#(i + 1).], it)
    v(8mm)
  }
})

// Блоки: жёлтая черта, жирный заголовок, текст; колонки равные.
#let slide-columns(title: none, blocks: ()) = cs(title, grid(
  columns: blocks.map(_ => 1fr), column-gutter: 15mm,
  ..blocks.map(b => [
    #line(length: 100%, stroke: 3mm + lm-yellow)
    #v(6mm)
    #if b.heading != none { text(weight: "bold", font: title-font, size: 32pt, b.heading); v(4mm) }
    #fit-text(200mm, (size-body, 24pt, 20pt), b.text)
  ]),
))

// Сравнение: как comparison-slide канона — две подложки и «VS» между ними.
#let slide-comparison(title: none, left: (:), right: (:)) = cs(title, grid(
  columns: (1fr, auto, 1fr), column-gutter: 8mm, align: (top, horizon, top),
  ..((left, lm-gray.lighten(90%)), none, (right, lm-yellow.lighten(85%))).map(x => if x == none {
    text(fill: lm-yellow, size: size-h1, weight: "bold", font: title-font)[VS]
  } else {
    let (side, fill) = x
    block(width: 100%, height: 230mm, fill: fill, radius: 8pt, inset: 12mm, clip: true)[
      #if side.heading != none { text(weight: "bold", font: title-font, size: 36pt, side.heading); v(6mm) }
      #if side.bullets != none { fit-text(170mm, (size-body, 24pt, 20pt), list(..side.bullets)) }
    ]
  }),
))

// Цитата: крупно по центру, автор ниже серым — как «Акцентный» мастера.
#let slide-quote(text: none, author: none) = content-slide(
  title: "", slide-number: num, title-size: size-h1-compact, title-height: 0mm,
  box(width: 100%, height: 300mm, clip: true, align(center + horizon, {
    std.text(fill: lm-yellow, size: 160pt, weight: "bold", font: title-font)[«]
    v(-20mm)
    fit-text(170mm, (size-h2, 40pt, 32pt), text, weight: "bold", font: title-font)
    if author != none { v(10mm); std.text(fill: lm-gray, size: size-body, author) }
  })),
)
```

`text` — имя параметра функции цитаты (контракт), поэтому внутри неё встроенная функция зовётся `std.text`. `left` и `right` у сравнения — параметры, а не выравнивания: в `align` их не использовать.

- [ ] **Step 4: Тесты типов зелёные**

Run: тот же `-k`, что в шаге 1.
Expected: PASS для agenda, text, columns, comparison, quote (оба теста каждого типа). Если `stays_on_the_page` падает — уменьшить кегли лестницы или высоты, а не расширять тело; причину записать в журнал.

- [ ] **Step 5: Коммит (канон, worktree)**

```bash
git -C ~/projects/lemana-canon-slides-v2 add typst-deck/adapter.typ
git -C ~/projects/lemana-canon-slides-v2 commit -m "feat(typst-deck): повестка, тезисы, блоки, сравнение и цитата

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Адаптер — график с видом и два графика

**Files (канон, worktree):**
- Modify: `typst-deck/adapter.typ` (удалить `bar-chart`, `line-chart`, `legend`, `chart-layout`, `slide-bar-chart`; добавить `bars`, `lines`, `legend`, `slide-chart`, `slide-dual-chart`)
- Test: `tests/test_corporate.py` (typst-deck)

**Interfaces:**
- Consumes: `cs`, `K`, `chart-palette` (задача 2).
- Produces: `bars(labels, series, unit, height: …)`, `lines(labels, series, height: …)`, `slide-chart(title, kind, labels, series, unit, bullets)`, `slide-dual-chart(title, left, right)`.

- [ ] **Step 1: Вырожденные данные — падающий тест** (typst-deck, `tests/test_corporate.py`):

```python
DEGENERATE = {
    "одна категория": {"labels": ["Центр"], "series": [{"name": "млн", "values": [42]}]},
    "все нули": {"labels": ["A", "B", "C"], "series": [{"name": "x", "values": [0, 0, 0]}]},
    "только минус": {"labels": ["A", "B"], "series": [{"name": "x", "values": [-3, -7]}]},
    "четыре ряда": {"labels": ["A", "B", "C"],
                    "series": [{"name": f"Ряд {k}", "values": [k, -k, 2 * k]} for k in range(1, 5)]},
}


@requires_typst
@pytest.mark.parametrize("t", CORP_PARAMS)
@pytest.mark.parametrize("kind", ["bar", "line"])
@pytest.mark.parametrize("case", DEGENERATE)
def test_corp_degenerate_charts_stay_on_one_page(t, kind, case, tmp_path):
    data = DEGENERATE[case]
    if kind == "line" and len(data["labels"]) < 2:
        pytest.skip("линии нужны две точки — модель это не пропустит")
    deck = Deck(slides=[{"type": "chart", "title": "Итоги", "kind": kind, "unit": "млн", **data},
                        {"type": "dual-chart", "title": "Два", "left": {"kind": kind, **data},
                         "right": {"kind": kind, **data}}])
    r = compile_deck(deck, tmp_path, t.path, fonts_dir=t.fonts)
    assert len(r.svgs) == 2
    assert max(p["y"] + p["h"] for p in r.positions) <= PAGE_BOTTOM_MM * MM
```

`test_corp_signed_charts_keep_one_page_per_slide` использует `signed_deck()` из `tests/test_charts.py` — проверить, что он на новых типах (`chart` с `kind: "bar"`); если нет — поправить сам `signed_deck`.

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next uv run pytest -q tests/test_corporate.py -k "chart or degenerate"`
Expected: FAIL — `slide-dual-chart` нет, `slide-chart` не знает `kind`.

- [ ] **Step 2: Перенос** — из `template/deck.typ` (ветка `slides-v2` typst-deck) перенести `bars` (строки «#let bars(…)» … конец функции), `lines`, `slide-chart` и `slide-dual-chart` по таблице переноса. Сохранить без изменений: обработку вырожденного размаха (`flat`), легенду в коробке постоянной высоты (`0.75cm × K` у chart, `0.5cm × K` у стороны dual-chart), лестницу кеглей подписей категорий, колонку «Выводы» (`heading` из `pptx.json` в Typst не попадает — заголовок колонки `Выводы`, как сейчас в адаптере), обход имён `left`/`right` в `slide-dual-chart`. Старые `bar-chart`, `line-chart`, `legend`, `chart-layout`, `slide-bar-chart` удалить.

- [ ] **Step 3: Тесты зелёные**

Run: тот же `-k`.
Expected: PASS, включая `test_corp_type_*[lemana-tech-chart]` и `[lemana-tech-dual-chart]`.

- [ ] **Step 4: Коммит (канон)**

```bash
git -C ~/projects/lemana-canon-slides-v2 commit -am "feat(typst-deck): график с видом bar/line и несколькими рядами, два графика

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

и в typst-deck — тест вырожденных графиков.

---

### Task 4: Адаптер — метрики, таблица, галерея, видео

**Files (канон, worktree):** `typst-deck/adapter.typ`

**Interfaces:**
- Consumes: `cs`, `K`, `fit-text`.
- Produces: `slide-metrics`, `slide-table`, `slide-gallery`, `slide-video`.

- [ ] **Step 1: Тесты задачи**

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next uv run pytest -q tests/test_corporate.py -k "metrics or table or gallery or video"`
Expected: FAIL — функций нет.

- [ ] **Step 2: Метрики** — стиль metrics-slide канона: серая подложка, число жёлтым жирным, подпись тёмным; изменение цветом тренда. Равные колонки, лестница кеглей числа — с эталона (`value-cell`), пересчитанная по таблице переноса:

```typst
// рост — тёмным, как trend.up в pptx.json: жёлтый на светло-серой подложке не читается
#let lm-up = lm-dark

#let slide-metrics(title: none, items: ()) = cs(title, align(horizon, grid(
  columns: items.map(_ => 1fr), column-gutter: 12mm,
  ..items.map(m => rect(width: 100%, height: 150mm, fill: lm-gray.lighten(85%), radius: 8pt, inset: 10mm,
    align(center + horizon, {
      fit-text(45mm, (size-title, size-h1, size-h2), m.value, weight: "bold", font: title-font, fill: lm-dark)
      if m.label != none { v(4mm); fit-text(35mm, (size-body, 24pt), m.label, fill: lm-gray) }
      if m.delta != none {
        v(4mm)
        text(size: size-body, weight: "bold",
          fill: if m.trend == "down" { lm-red } else if m.trend == "up" { lm-up } else { lm-gray }, m.delta)
      }
    }))),
)))
```

Число и рост — тёмным, а не жёлтым, как в metrics-slide канона: на светлой подложке жёлтый не читается; это решение записать в журнал.

- [ ] **Step 3: Таблица** — перенос `slide-table` эталона: шапка на `lm-yellow`, «зебра» `lm-gray.lighten(92%)`, тонкие линии `lm-gray.lighten(60%)`, `align: numeric.map(…)` как в эталоне, кегль ячеек — лестница `(size-body, 24pt, 20pt, 18pt)` по высоте тела.

- [ ] **Step 4: Галерея и видео** — перенос `slide-gallery` (сетка 2/3 в ряд, 4 — 2×2, `p.image` приходит готовым content) и `slide-video` (кадр 16:9, без обложки — заливка `lm-gray.lighten(85%)` и «▶» `lm-yellow`; `if url == none { frame } else { link(url, frame) }`; подпись под кадром `size-caption` серым).

- [ ] **Step 5: Тесты зелёные, коммит (канон)**

Run: `-k` шага 1.
Expected: PASS.

```bash
git -C ~/projects/lemana-canon-slides-v2 commit -am "feat(typst-deck): метрики, таблица, галерея и видео

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Пределы слотов — замер и объявление

**Files (канон):** `typst-deck/measure.json`, `template.json`

**Interfaces:**
- Consumes: функции задач 2–4 (геометрия зон).
- Produces: раздел `slots` в `template.json` на 15 типов (без `bar-chart`).

- [ ] **Step 1: Пробы** — в `measure.json` заменить пробы `bar-chart` на пробы новых полей. Ширина и высота — зона поля в адаптере (мм); `item` — высота одного тезиса для списков:

| slide | field | width | height | item | size |
|---|---|---|---|---|---|
| agenda | items | 591mm | 250mm | 24mm | size-body |
| text | title | 617mm | 50mm | — | size-h1-compact |
| text | bullets | 617mm | 250mm | 40mm | size-body |
| columns | blocks.heading | 182mm | 30mm | — | 32pt |
| columns | blocks.text | 182mm | 200mm | — | size-body |
| comparison | left.bullets | 249mm | 170mm | 40mm | size-body |
| comparison | right.bullets | 249mm | 170mm | 40mm | size-body |
| quote | text | 617mm | 170mm | — | size-h2 |
| quote | author | 617mm | 15mm | — | size-body |
| metrics | items.label | 140mm | 35mm | — | size-body |
| table | rows | — по ширине колонки при 6 колонках | 30mm | — | size-body |
| gallery | images.caption | 190mm | 15mm | — | size-caption |
| video | caption | 617mm | 15mm | — | size-caption |
| chart | title, bullets | как было у `chart` | | | |

Ширины колонок — из адаптера: блоки `(617 − 2·15)/3`, сравнение `(617 − 2·8 − ширина «VS»)/2 − 2·12` (поля подложки), метрики при 4 колонках `(617 − 3·12)/4 − 2·10`, ячейка таблицы `617/6 − отступы ячейки`. Если число в адаптере изменилось при задачах 2–4 — брать из адаптера, а не из этой таблицы.

- [ ] **Step 2: Замер**

```sh
uv run --project ~/projects/typst-deck/.worktrees/slides-v2 python \
  ~/projects/typst-deck/.worktrees/slides-v2/scripts/measure_slots.py ~/projects/lemana-canon-slides-v2 > /tmp/slots.json
```

Expected: раздел `slots` на все пробы, в stderr — по строке на пробу.

- [ ] **Step 3: Объявление** — перенести в `template.json` результат с запасом 10–15 % от обрыва (правило ADR 0010; `measure_slots` даёт наибольшее влезающее — снизить на 10–15 % и округлить вниз до 5), не выше глобальных пределов модели (§4 спеки), удалить `bar-chart`. Заголовки новых типов — как у `image`/`chart` (`max: 120, lines: 2`), если замер не дал меньше.

- [ ] **Step 4: Тесты пределов**

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next uv run pytest -q tests/test_corporate.py -k "clamp or enforced or declared or limits"`
Expected: PASS: объявление переживает `clamp` без изменений, каждый предел проверяется, текст по пределам влезает в свою зону и в поле страницы.

- [ ] **Step 5: Коммит (канон)**

```bash
git -C ~/projects/lemana-canon-slides-v2 commit -am "feat(typst-deck): пределы слотов 15 типов — замер measure_slots

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `pptx.json` на 15 типов

**Files (канон):** `typst-deck/pptx.json`

- [ ] **Step 1: Сопоставление** — по спеке §7 («Раскладка Lemana Tech») и новым ключам оформления:

```json
{
  "master": "references/lm-tech_template.pptx",
  "font": "Calibri",
  "text":  {"size": 28, "bullet": "FFDE00", "caption": "666666", "quote": 54, "metric": 80},
  "chart": {"palette": ["FFDE00", "1E1E1E", "00FFE0", "FF8700"], "negative": "FF2E00"},
  "trend": {"up": "1E1E1E", "down": "FF2E00"},
  "table": {"size": 20, "header_fill": "FFDE00", "stripe_fill": "F4F4F4", "rule": "D9D9D9"},
  "slides": {
    "title":      {"layout": "Титульный слайд", "ph": {"title": 0, "subtitle": 1, "author": 21, "department": 21}},
    "agenda":     {"layout": "Стандартный",  "ph": {"title": 0}, "body": [83, 100, 564, 240]},
    "section":    {"layout": "Отбивочный слайд 2", "ph": {"title": 0, "subtitle": 1}},
    "text":       {"layout": "Стандартный",  "ph": {"title": 0}, "body": [83, 100, 564, 240]},
    "image":      {"layout": "Стандартный",  "ph": {"title": 0}, "body": [83, 100, 564, 240],
                   "image_width": {"small": 30, "medium": 42, "large": 55}, "gap": 15},
    "columns":    {"layout": "Блоки текста", "ph": {"title": 0, "blocks": [10, 11, 12]}},
    "comparison": {"layout": "Стандартный",  "ph": {"title": 0}, "body": [83, 100, 564, 240], "gap": 20},
    "quote":      {"layout": "Акцентный",    "ph": {},           "body": [83, 90, 511, 200]},
    "chart":      {"layout": "Стандартный",  "ph": {"title": 0}, "body": [83, 100, 564, 240],
                   "text_width": 38, "gap": 12, "heading": "Выводы"},
    "dual-chart": {"layout": "Стандартный",  "ph": {"title": 0}, "body": [83, 100, 564, 240], "gap": 20},
    "metrics":    {"layout": "Статистика",   "ph": {"title": 0}, "body": [83, 160, 564, 130], "gap": 15},
    "table":      {"layout": "Таблица",      "ph": {"title": 0}, "body": [83, 95, 564, 245]},
    "gallery":    {"layout": "Стандартный",  "ph": {"title": 0}, "body": [83, 100, 564, 240], "gap": 12},
    "video":      {"layout": "Стандартный",  "ph": {"title": 0}, "body": [83, 100, 564, 240]},
    "final":      {"layout": "Заключительный", "ph": {"title": 0, "contact": 1}}
  }
}
```

`header_fill` — жёлтый канона (шапка таблицы в фирменном стиле), а не серый эталона; записать в журнал.

- [ ] **Step 2: Проверка на настоящем мастере**

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next uv run pytest -q tests/test_corporate.py -k "pptx or master"` и `uv run python -m typst_deck.templates ~/projects/lemana-canon-slides-v2`
Expected: PASS; проверка контракта — без ошибок (правило 7 экспортирует образец из 15 слайдов на мастер Lemana).

- [ ] **Step 3: Файл для ручной приёмки** — выгрузить образец на мастере Lemana в scratchpad (`export_pptx(SAMPLE_DECK, …)` с `write_sample_assets`) и передать пользователю: открывается без «восстановить»; «Блоки текста» без лишних маркеров; таблица на «Таблице», цитата на «Акцентном», метрики на «Статистике» читаются.

- [ ] **Step 4: Коммит (канон)**

```bash
git -C ~/projects/lemana-canon-slides-v2 commit -am "feat(typst-deck): сопоставление PowerPoint-мастера на 15 типов и ключи оформления

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Весь контракт, вёрстка на пределах и картинки для приёмки

**Files:** нет новых; проверки.

- [ ] **Step 1: Полный набор корпоративных тестов**

Run: `TYPST_DECK_TEST_TEMPLATES=~/corp-templates-next uv run pytest -q tests/test_corporate.py` и `uv run pytest -q`
Expected: оба зелёные; `test_corp_template_passes_the_full_contract` — без ошибок.

- [ ] **Step 2: Вёрстка на пределах — измерением** (спека §9): собрать колоду оговорённых случаев — 7 пунктов повестки, 5 тезисов на сторону сравнения, 6 тезисов текстового слайда, 4 колонки метрик, 3 ряда на сторону у двух графиков, таблица 8×6, 3 блока по пределу — значениями ровно по объявленным пределам (`filled_slide`), и сверить низ каждого поля из `positions` с низом тела (`80 + 250` мм от верха). Числа записать в журнал; превышение — правка адаптера (кегль, высота), а не предела.

- [ ] **Step 3: Картинки для глаз** — та же колода и `SAMPLE_DECK` в PNG (`typst compile --format png --ppi 40` по `build/deck.typ`), в scratchpad. Картинка — только гипотеза: замеченную «обрезку» подтверждать измерением шага 2 (спека §9).

- [ ] **Step 4: Ревью** — финальное ревью ветки typst-deck и ветки канона свежим ревьюером (по процессу исполнения плана).

---

### Task 8: Слияние и выкатка одним окном

**Только с явного согласия пользователя перед шагами 2, 4, 5–9.** Порядок — спека §10, откат — там же.

- [ ] **Step 1: Сухой прогон на копии тома** (без побочных эффектов): `podman cp typst-deck:/data <scratch>`, `migrate_slides --check` и перенос копии кодом ветки, сборка каждой колоды копии на `~/projects/lemana-canon-slides-v2` — все колоды собираются, предупреждений нет. Копию после проверки удалить.
- [ ] **Step 2: Слияние typst-deck** — `slides-v2` → `main` (fast-forward или merge-коммит), перенос в `main` обновлений документации ветки: `docs/api.md` (`GET …/assets/{asset}`), бэклог (планы A–D сделаны). `uv run pytest -q` на `main`.
- [ ] **Step 3: Метка отката:** `podman tag localhost/typst-deck:latest localhost/typst-deck:pre-slides-v2`.
- [ ] **Step 4: Резервная копия тома:** `podman volume export typst-deck-data > ~/backups/typst-deck-data-<дата>.tar`.
- [ ] **Step 5: Остановка:** `systemctl --user stop typst-deck`.
- [ ] **Step 6: Канон:** в живом каноне `git merge --ff-only slides-v2` (ветка из worktree).
- [ ] **Step 7: Перенос колод:** `podman run --rm -v typst-deck-data:/data localhost/typst-deck:<новый> python -m typst_deck.migrate_slides` после сборки образа шага 8 (или из ветки с `TYPST_DECK_DATA_DIR`, смонтировав том).
- [ ] **Step 8: Образ и запуск:** `podman build -t localhost/typst-deck:latest ~/projects/typst-deck`, `systemctl --user start typst-deck`.
- [ ] **Step 9: Проверки** — `docs/operations.md`, пункт 5: `/api/health` (`templates.broken {}`, `pptx_off {}`), `/api/templates`, PDF и PPTX живой колоды; ручная приёмка пользователем.

**Откат:** `git -C <канон> reset --hard <прежний коммит>` (записать его до шага 6), `podman volume import typst-deck-data <копия>` при остановленном сервисе, `podman tag localhost/typst-deck:pre-slides-v2 localhost/typst-deck:latest`, `systemctl --user restart typst-deck`. Правки колод после выкатки при откате пропадут.

## После плана

- `git push` в `origin` обоих репозиториев — по согласию пользователя.
- Удалить worktree канона и `~/corp-templates-next` после выкатки.
- Бэклог: снять «Выкатка одним окном», «замер промпта»; оставить ручную приёмку PPTX и плеера.
