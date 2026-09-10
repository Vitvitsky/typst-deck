# typst-deck

Корпоративный генератор презентаций: чат с корпоративной нейросетью плюс
живое превью слайдов в корпоративном Typst-шаблоне. Сотрудник описывает
презентацию текстом или кидает Word/Excel/CSV, правит результат через чат
или кликом по слайду, скачивает PDF. Тот же сервис доступен чат-боту как
инструмент: «сделай презентацию по файлу» → PDF плюс ссылка на доработку.

Замена внешним сервисам (Gamma, DeepSeek) для сценария «сделай презентацию»
внутри корпоративной сети.

Спека: `docs/superpowers/specs/2026-09-08-typst-deck-design.md`.
План: `docs/superpowers/plans/2026-09-08-typst-deck-v1.md`.

## Принцип

**Нейросеть не пишет Typst-код.** Источник истины — модель презентации
(JSON): список слайдов, у каждого тип из закрытого набора шаблона и поля
этого типа. Python детерминированно превращает модель в `.typ` и
компилирует. Нейросеть и человек правят одну и ту же модель точечными
патчами; каждая правка — новая версия с откатом.

```json
{
  "slides": [
    {"type": "title", "title": "Итоги квартала", "subtitle": "Финансы, Q3"},
    {"type": "image", "title": "Рост выручки", "bullets": ["…"],
     "image": "a3f9k2q.png", "image_size": "large"},
    {"type": "bar-chart", "title": "Продажи по регионам",
     "data": [{"label": "Центр", "value": 42}, {"label": "Север", "value": 17}]},
    {"type": "final"}
  ]
}
```

## Запуск

Нужны `uv` и `typst` 0.15+ в PATH.

```sh
uv sync                      # окружение
uv run pytest                # 92 теста; компиляция пропускается без typst
scripts/dev.sh               # http://127.0.0.1:8000, ключ DeepSeek берётся из ~/stack/.env
```

Переменные окружения (префикс `TYPST_DECK_`): `DATA_DIR`, `TEMPLATE_DIR`,
`TEMPLATES_DIR` (корни дополнительных шаблонов, несколько — через `:` как
PATH; при совпадении id побеждает первый), `TYPST_BIN`, `PUBLIC_BASE_URL`, `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`,
`LLM_MAX_TOKENS` (по умолчанию 16384: рассуждающим моделям вроде deepseek-v4-flash нужен запас на рассуждение), `LLM_TOOL_MODE` (`tools` | `json`), `MAX_UPLOAD_MB`,
`LOG_LEVEL` (по умолчанию `INFO`), `LOG_FORMAT` (`text` | `json`).
`DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `DEEPSEEK_MODEL` принимаются как
синонимы. Без ключа сервис стартует, работает ручная правка, генерация
отвечает 503.

## Что видно в логах

Каждый этап пишет одно событие с длительностью, так что по `podman logs typst-deck` видно,
куда ушло время: чтение материалов, каждый вызов модели, компиляция typst
(отдельно PDF, SVG и запрос позиций), итог задачи, ручные правки и все
HTTP-запросы. `/api/health` в лог не попадает — иначе HEALTHCHECK контейнера
занимает 80% строк.

```
job.start      deck=3a7d4cn2 job=jfcddeur first=True
stage.reading  deck=3a7d4cn2 job=jfcddeur files=2 chars=8412 history=4 ms=18
llm.done       iter=1 tok_in=8421 tok_out=1204 cached=0 calls=1
llm.done       iter=2 tok_in=9980 tok_out=142 cached=8320 calls=1
render.done    deck=3a7d4cn2 slides=3 svg_kb=39 pdf_ms=65 svg_ms=47 query_ms=43 ms=157
job.done       deck=3a7d4cn2 job=jfcddeur v=2 slides=3 tok_in=18401 tok_out=1346 cached=8320 iter=2 ms=177
http           method=POST path=/api/decks status=202 ms=247
```

`TYPST_DECK_LOG_FORMAT=json` даёт те же события построчным JSON для сборщика
логов. `httpx` и `uvicorn.access` приглушены до WARNING: они дублируют
`llm.done` и `http`, но без токенов и без времени ответа.

## Счётчик токенов

Один запрос пользователя — это до 12 вызовов модели, поэтому считается сумма по
всем итерациям агента. Цифры берутся из поля `usage` ответа провайдера, не
оцениваются.

- **В чате** под каждым ответом модели: `18 401 → 1 346 тк · кэш 45% · 23.1 с · модель ×2`.
  Хранится в `chat.jsonl` рядом с `ops` и `changes`; у записей, сделанных до
  этой версии, полей нет — тогда строка не показывается.
- **В `/api/health`** — сумма за время жизни процесса (при рестарте
  обнуляется, поэтому рядом отдаётся `since`):
  `"tokens": {"in": 18401, "out": 1346, "cached": 8320, "requests": 2}`.

Контейнер (на этом сервере — rootless podman 5.7):

```sh
podman build -t typst-deck .
podman run -p 127.0.0.1:8088:8000 -v typst-deck-data:/data \
  -e DEEPSEEK_API_KEY=… -e DEEPSEEK_MODEL=deepseek-chat typst-deck
```

Файлы сборки называются `Dockerfile` и `.dockerignore` и переименования не
требуют: podman читает их как есть, на них же ссылается `~/stack/compose.yaml`.

В образ попадает `templates/` с хоста целиком, включая подтянутый канон и
шрифты Lemana Tech, поэтому образ с корпоративным шаблоном публиковать
нельзя. На последнем шаге сборки `python -m typst_deck.templates` собирает
образец каждым шаблоном, и `podman build` падает, если какой-то каталог
неполный (например, канон не подтянут). Ту же команду можно запускать
локально. Если шаблон не должен попадать в образ, его каталог исключается в
`.dockerignore`, а в контейнер монтируется снаружи и добавляется вторым
корнем: `-v /srv/templates:/private -e TYPST_DECK_TEMPLATES_DIR=/app/templates:/private`.

## Как это работает

```
браузер ── чат ──▶ FastAPI ──▶ LLM (OpenAI-совместимый API) через инструменты
   ▲                 │              set_deck / update_slide / add_slide /
   │ SVG-превью      │              remove_slide / move_slide / set_template / finish
   │ клик по полю    ▼
   └──────── модель колоды (JSON) ──▶ render.py ──▶ build/deck.typ
                                        │
                                  typst compile ──▶ SVG (превью) / PDF (скачать)
                                  typst eval query ──▶ координаты полей для кликов
```

- `src/typst_deck/model.py` — Pydantic-модель слайдов и колоды, патчи.
- `render.py` — `deck.typ` из модели, `typst compile`, координаты полей.
- `store.py` — колоды на диске: `data/decks/<id>/` с версиями, ассетами,
  загрузками и чатом.
- `llm/` — клиент (tool calling и запасной JSON-режим), инструменты, цикл
  агента, системный промпт `prompt.md`.
- `service.py` — операции над колодой, общие для веб-интерфейса и бота.
- `api/` — маршруты; `static/` — интерфейс без сборки (ES-модули). Правила
  интерфейса — `DESIGN.md`, клиентские пути и требования —
  `docs/design/2026-09-08-ux-journeys.md`.
- `template/` — шаблон по умолчанию (id `default`); дополнительные шаблоны
  живут в корнях `<корень>/<id>/deck.typ` с тем же контрактом и необязательным
  `template.json` (`name`, `description`); корней несколько (`TEMPLATES_DIR`,
  через `:`), при совпадении id побеждает первый. Каталог без `deck.typ`
  пропускается с предупреждением в логе. Колода хранит `template`, выбор
  на форме создания, смена — эндпоинтом или инструментом `set_template`.
- Страницы: `/` — новая презентация, `/decks` — каталог, `/history` —
  все запросы к модели, `/templates` — шаблоны с превью, `/d/{id}` —
  редактор. Общее боковое меню (`static/shell.js`) с недавними колодами и
  статусом модели; на странице колоды свёрнуто по умолчанию.

Кликабельные зоны на превью: сервис оборачивает каждое текстовое поле в
маркер `field(slide, name, body)` из `typst/fields.typ`, который пишет в
метаданные позицию и размер; `typst eval 'query(<edit>)…'` отдаёт их в
пунктах, viewBox SVG тоже в пунктах, пересчёт не нужен.

## HTTP API

Для веб-интерфейса: `POST /api/uploads`, `GET /api/decks` (каталог), `POST /api/decks`
(с полем `template`), `PATCH /api/decks/{id}` (название), `POST /api/decks/{id}/template`
(смена шаблона с откатом при ошибке рендера), `DELETE /api/decks/{id}` (в корзину
`data/trash/`), `POST …/uploads` (материалы из чата), `GET /api/templates`,
`GET /api/templates/{id}/preview/{n}.svg`, `GET /api/history`,
`GET /api/decks/{id}`, `…/slides/{n}.svg`, `…/deck.pdf`, `…/positions`,
`PATCH …/slides/{sid}`, `POST …/slides`, `DELETE …/slides/{sid}`,
`POST …/slides/{sid}/move`, `POST …/assets`, `GET …/versions`,
`POST …/revert`, `POST …/messages`, `GET …/chat`, `GET /api/jobs/{id}`.

Для чат-бота (синхронные, ждут генерацию до `wait_seconds`):

```
POST /api/agent/create_deck  {brief, files: [{name, content_base64}], wait_seconds}
POST /api/agent/revise_deck  {deck_id, request, wait_seconds}
GET  /api/agent/decks/{deck_id}
→ {deck_id, status, pdf_url, edit_url, outline: [{n, type, title}], reply}
```

Бот про слайды не знает: передаёт задание, получает PDF и ссылку
`edit_url`, которая открывает ту же колоду в веб-интерфейсе. MCP-обёртка
поверх этих трёх вызовов — следующий шаг.

## Шаблон Lemana Tech (`templates/lmru-hr`)

Подключён 2026-09-08 из репозитория `lmru--hr-analytics--design-template`
(клон в `~/projects/`). Канонический `slides_template.typ` скопирован без
изменений, кроме двух: константа `lm-components-dir` указывает на
`components/` рядом с шаблоном, и в списки шрифтов первым добавлено настоящее
имя семейства «TT Interphases Pro» (канон просит «…Pro Trl», имя пробной
версии, которого на сервере нет). Поверх канона лежит `deck.typ` — адаптер
семи функций контракта: заглавный → `title-slide`, раздел →
`divider-slide-black`, текст и картинка / диаграмма / график →
`content-slide` с фиксированной зоной заголовка и обрезанным телом, финальный
→ `conclusion-slide`. Диаграммы рисуются средствами Typst в фирменных цветах,
потому что канонический `chart-slide` ждёт готовый файл графика. Номер слайда
берётся из счётчика страниц.

Канонический `title-slide` вызов обёрнут в `set par(spacing: 0pt)`: внутри
правой колонки канона есть пустые строки между элементами, а в Typst пустая
строка — параграф-брейк, добавляющий интервал, пропорциональный кеглю
(после 80pt заголовка — десятки миллиметров). С длинным заголовком и
подзаголовком страница переполнялась, и `title-slide` съезжал на вторую
страницу — слайдов в PDF оказывалось больше, чем в модели, а контракт
требует «одна функция = одна страница». Остальные функции канона такого не
дают: `divider-slide-*` и `conclusion-slide` краткие, а `content-slide`
защищён обрезанным `box`. При правках канона правило простое: внутри
функции-слайда пустых строк быть не должно, отступы задаются явными `v()`.

В git из этого каталога лежит только своё: адаптер `deck.typ`, `template.json`
и `CANON_REV` — короткий хеш коммита канона, с которым адаптер проверен. Сам
канон (`slides_template.typ`, `components/`, `fonts/`) закрытый, он в
`.gitignore`, и на свежем клоне его нет: пока не выполнен скрипт синхронизации,
реестр шаблонов не покажет `lmru-hr` (адаптер без канона в реестр не попадает:
`deck.typ` импортирует `slides_template.typ`, которого нет), а
`tests/test_compile.py` не пройдёт. Образ
собирается из рабочего дерева и проверяет каждый шаблон, поэтому скрипт
нужно выполнить перед `podman build`.

Подтянуть канон на свежем клоне или обновить его после правок в репозитории
шаблона:

```sh
scripts/sync-lmru-template.sh            # копирует канон, компоненты и шрифты, пишет CANON_REV
uv run pytest tests/test_compile.py      # контракт проверяется для каждого шаблона в templates/
```

Скрипт берёт текущий HEAD клона канона. Если после синхронизации `CANON_REV`
изменился, а адаптер собирается — закоммитить новый `CANON_REV` вместе с
правками `deck.typ`; если сборка сломалась, известная рабочая ревизия — в
закоммиченном `CANON_REV`, на неё можно откатить клон канона.

### Ёмкость слотов

`template.json` объявляет разделом `slots`, сколько знаков и строк вмещает
каждое поле каждого типа слайда. Эти пределы попадают в схему, которую видит
модель, и проверяются при каждой правке — чата и панели свойств одинаково.
Объявление может только сузить глобальные пределы `model.py`, но не расширить:
колода переезжает между шаблонами, и текст, написанный под расширенный предел,
не прошёл бы в другом шаблоне.

Значения не угадываются: `uv run python scripts/measure_slots.py lmru-hr`
меряет высоту текста настоящим шрифтом шаблона и печатает готовый раздел
`slots`. Последний рубеж — автоподбор кегля в `deck.typ`: текст, уложившийся в
предел, но набранный широкими знаками, набирается меньшим кеглем из лесенки
канона (`size-title` → `size-h1` → `size-h1-compact`).

## Подключение корпоративного шаблона

Положить в `template/` (или указать `TYPST_DECK_TEMPLATE_DIR`) файл
`deck.typ`, ресурсы и шрифты в `template/fonts/`. `deck.typ` экспортирует:

```typst
#let deck(title: none, body)
#let slide-title(title: none, subtitle: none)
#let slide-section(title: none, subtitle: none)
#let slide-image(title: none, bullets: none, image: none, image-size: "medium", caption: none)
#let slide-bar-chart(title: none, data: (), unit: none, bullets: none)
#let slide-chart(title: none, labels: (), series: (), unit: none, bullets: none)
#let slide-final(title: none, contact: none)
```

Правила: текстовые параметры и `bullets` приходят как content (строковые
операции над ними недопустимы); `image` — content с `width: 100%,
height: 100%, fit: "contain"`, контейнер задаёт шаблон; `data`, `labels`,
`series` — сырые массивы; каждая функция — ровно одна страница (после
компиляции число страниц сверяется с числом слайдов); пакеты `@preview`
нежелательны, если у сети нет доступа к реестру. Заглушка в `template/`
показывает всё это на примере, включая приём с обрезанным `box` на всю
страницу, чтобы переполнение не порождало вторую страницу.

## Проверено 2026-09-08

- 67 автотестов: модель, рендер, компиляция, хранилище, извлечение текста,
  клиент LLM, цикл агента, задачи, HTTP API, агентское API, страницы.
- Реальный прогон с DeepSeek (`deepseek-v4-flash`) через `~/stack/.env`:
  презентация из 7 слайдов по CSV с выручкой и расходами собралась за
  16 секунд, числа взяты из файла; правка «короче заголовок, добавь единицу
  измерения» ушла двумя патчами `update_slide` за 9 секунд.
- Образ собран, контейнер отдал `/api/health`, сгенерировал колоду и PDF.
- Веб-интерфейс проверен скриншотами в headless Chromium (образ
  `mcr.microsoft.com/playwright/python` на host-сети, потому что на хосте
  нет библиотек Chromium): главная, колода, панель свойств, редактор поля,
  состояние сборки. Кликов-сценариев автотестами нет.

## Проверено 2026-09-09

- 92 автотеста (`uv run pytest`).
- Ghost-страница `title-slide` в lmru-hr: длинный заголовок + подзаголовок
  создавали вторую страницу из-за параграф-брейков канона; исправлено в
  адаптере `set par(spacing: 0pt)`. Реальная колода «Итоги Q3» снова
  10 страниц = 10 слайдов, `warnings.json` пуст. Диагностика и фикс — выше,
  в разделе про шаблон Lemana Tech.
- Смена шаблона: эндпоинт `POST /api/decks/{id}/template`, инструмент
  `set_template` (LLM выбирает id из списка в системном промпте), селект
  в шапке редактора. При ошибке рендера — откат версии, как у остальных
  правок.

## Демо на этом сервере

Стек в `~/stack` устроен единообразно, typst-deck встаёт в него тем же
способом, что и `deepseek-web`:

- контейнерами управляет rootless podman через systemd (Quadlet), а не compose:
  юнит `typst-deck.container` версионируется в `~/stack/quadlet/`, работает из
  `~/.config/containers/systemd/`, порт `127.0.0.1:8088:8000`, сеть
  `portfolio-internal`, healthcheck на `/api/health`;
- выкатка после правки кода — два шага, образ и юнит разведены намеренно:
  `podman build -t localhost/typst-deck:latest ~/projects/typst-deck` и
  `systemctl --user restart typst-deck`;
- ключ и модель из уже существующих `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`,
  `DEEPSEEK_MODEL`; замена на внутренний эндпоинт — две переменные;
- путь `/deck/` в `nginx/portfolio.conf` по образцу `/deepseek/`: Basic Auth,
  лимиты, Nginx срезает префикс, страницы используют относительные пути
  (`<base href>`), поэтому префикс им не мешает;
- колоды и загрузки в volume `typst-deck-data` — он в хранилище пользователя,
  а не системном: смотреть `podman volume ls`, а не из-под root.

## Открытые вопросы

- Умеет ли корпоративный эндпоинт tool calling; если нет —
  `TYPST_DECK_LLM_TOOL_MODE=json`.
- Графики в корпоративном шаблоне: своими средствами или внешним рендером.
- Аутентификация и ссылки с токеном для `edit_url` (в первой версии — за
  Basic Auth прокси).
- MCP-обёртка над агентским API.
