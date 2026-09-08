# typst-deck — проектная спецификация

Дата: 2026-09-08. Статус: утверждена к реализации (первая версия).

## 1. Цель и границы

Веб-сервис в корпоративной сети, который по текстовому заданию и приложенным
файлам собирает презентацию в корпоративном Typst-шаблоне, показывает её в
браузере, даёт править через чат с LLM и руками кликом по слайду, отдаёт PDF.
Тот же сервис доступен чат-боту как инструмент: «сделай презентацию по
файлу» → PDF плюс ссылка на доработку в веб-интерфейсе.

В первой версии:

- закрытый набор типов слайдов, без сырого Typst внутри слайдов;
- один процесс FastAPI, колоды на диске, задачи генерации в том же процессе;
- без аутентификации: сервис живёт за корпоративным прокси или Basic Auth;
- корпоративный шаблон подключается как каталог `template/` с оговорённым
  интерфейсом функций; до его появления используется заглушка с тем же
  интерфейсом;
- выход только PDF (плюс SVG для превью).

Вне первой версии: PPTX, SSO, совместное редактирование, MCP-обёртка (REST
для бота есть сразу, MCP добавляется отдельно), очередь задач вне процесса,
загрузка картинок из интернета (есть только загрузка файлом).

## 2. Ключевые принципы

1. **LLM не пишет Typst.** Источник истины — JSON-модель колоды. Код `.typ`
   порождается детерминированно из модели. Ошибка компиляции — это баг
   рендерера или шаблона, а не «модель ошиблась».
2. **Одна модель — два клиента.** Веб-интерфейс и чат-бот работают через один
   и тот же HTTP API. Ни одна операция не существует только в UI.
3. **Правки — патчи полей.** И LLM, и человек меняют отдельные поля слайда.
   Каждая правка порождает новую версию колоды; откат — восстановление
   версии.
4. **Шаблон — это контракт.** Сервис знает только имена функций слайдов и
   их параметры. Внешний вид целиком в шаблоне.

## 3. Модель колоды

Pydantic-модели в `typst_deck/model.py`. JSON-схема генерируется из них и
используется и для валидации патчей, и в системном промпте LLM.

```
Deck
  id: str            # 12 символов [a-z0-9], генерируется сервисом
  title: str         # название колоды (для списка и имени файла)
  slides: list[Slide]
  version: int       # монотонный счётчик, растёт при любой правке
  created_at, updated_at: datetime (UTC, ISO)

Slide (discriminated union по полю type)
  id: str            # "s" + 6 символов, стабилен между версиями
  type: Literal[...]
  notes: str = ""    # заметки докладчика; в рендер не идут, но LLM их видит
```

Типы слайдов и поля:

| type        | поля                                                                                  |
|-------------|----------------------------------------------------------------------------------------|
| `title`     | `title: str`, `subtitle: str = ""`                                                     |
| `section`   | `title: str`, `subtitle: str = ""`                                                     |
| `image`     | `title: str`, `bullets: list[str] (0..6)`, `image: str \| None` (asset id), `image_size: "small"\|"medium"\|"large" = "medium"`, `caption: str = ""` |
| `bar-chart` | `title: str`, `data: list[BarItem] (1..12)`, `unit: str = ""`, `bullets: list[str] (0..4)` |
| `chart`     | `title: str`, `labels: list[str] (2..24)`, `series: list[Series] (1..4)`, `unit: str = ""`, `bullets: list[str] (0..4)` |
| `final`     | `title: str = "Спасибо"`, `contact: str = ""`                                          |

`BarItem = {label: str, value: float}`; `Series = {name: str, values: list[float]}`,
длина `values` равна длине `labels` (проверяется валидатором).

Ограничения длины строк: заголовок до 120 символов, буллет до 200, чтобы LLM
не выдавала абзацы вместо тезисов. Нарушение — ошибка валидации, которая
возвращается LLM как результат инструмента, а человеку как 422.

Ассеты: файл в `assets/` каталога колоды; id — `a` + 6 символов плюс
расширение (`a3f9k2q.png`). Разрешены png, jpg, svg. Поле `image` ссылается
на id; при рендере проверяется существование файла, иначе слайд
рендерится без картинки и в ответе API появляется предупреждение.

## 4. Контракт шаблона

Каталог `template/` содержит `deck.typ` и произвольные ресурсы (SVG, шрифты
в `template/fonts/`). `deck.typ` обязан экспортировать:

```typst
#let deck(title: none, body)                 // обёртка документа: page setup, шрифты
#let slide-title(title: none, subtitle: none)
#let slide-section(title: none, subtitle: none)
#let slide-image(title: none, bullets: none, image: none, image-size: "medium", caption: none)
#let slide-bar-chart(title: none, data: (), unit: none, bullets: none)
#let slide-chart(title: none, labels: (), series: (), unit: none, bullets: none)
#let slide-final(title: none, contact: none)
```

Правила контракта:

- Текстовые параметры (`title`, `subtitle`, `caption`, `contact`, `bullets`)
  приходят как **content**, не как строки: сервис оборачивает их в маркер
  поля. Шаблон не должен делать строковые операции над ними. `bullets`
  приходит уже как готовый список (`list`-контент), шаблон только размещает.
- `image` приходит как content (`image("...")`, уже обёрнутый) или `none`.
- `data`, `labels`, `series` приходят сырыми (массивы и словари): шаблон
  сам рисует графики. Заглушка рисует их средствами ядра Typst без пакетов,
  потому что у корпоративной сети может не быть доступа к реестру пакетов.
- Каждая функция слайда сама создаёт страницу (`page[...]` или `pagebreak`).
  Одна функция — ровно одна страница; сервис опирается на это при
  сопоставлении номера страницы SVG и индекса слайда. Соответствие
  проверяется после компиляции: число страниц PDF должно равняться числу
  слайдов, иначе ошибка рендера.
- Шаблон импортируется как `#import "/template/deck.typ": *`; корень Typst —
  каталог `build/` колоды, где `template` — symlink на каталог шаблона.

Маркеры полей (в `typst_deck/typst/fields.typ`, часть сервиса, не шаблона):

```typst
#let field(slide, name, body) = layout(sz => context {
  let pos = here().position()
  let m = measure(width: sz.width, body)
  [#metadata((slide: slide, field: name, page: pos.page,
              x: pos.x.pt(), y: pos.y.pt(), w: m.width.pt(), h: m.height.pt())) <edit>]
  body
})
```

Координаты извлекаются командой
`typst eval 'query(<edit>).map(it => it.value)' --root build --in build/deck.typ --format json`
и отдаются как есть: viewBox SVG-страниц Typst в пунктах, пересчёт не нужен.
Проверено на Typst 0.15.1.

## 5. Рендерер

`typst_deck/render.py`:

- `render_typ(deck: Deck, assets: dict[str, Path]) -> str` — чистая функция,
  возвращает текст `deck.typ`. Строки экранируются для Typst-разметки
  (`#`, `*`, `_`, `` ` ``, `<`, `>`, `@`, `\`, `$`, `[`, `]`), потому что
  LLM и люди пишут что угодно. Буллеты собираются в `list(..)` с явными
  элементами, а не через markdown-подобный синтаксис.
- `compile(deck_dir: Path) -> CompileResult` — пишет `build/deck.typ`,
  гарантирует symlink `build/template`, вызывает `typst compile` для PDF и
  для SVG (`slide-{p}.svg`), затем `typst eval` для координат. Возвращает
  пути, список позиций полей, предупреждения, stderr компилятора при ошибке.
  Таймаут 60 с, `--font-path template/fonts` если каталог есть.
- Компиляция идёт в `build/` и атомарно: сначала во временный подкаталог,
  затем `os.replace` на место, чтобы превью не читало полуготовые файлы.

## 6. Хранилище

`data/decks/<deck_id>/`:

```
deck.json            текущая модель
versions/000001.json …   снимок каждой версии
assets/              картинки
uploads/             исходные файлы задания и извлечённый текст (.txt рядом)
build/               deck.typ, deck.pdf, slide-N.svg, positions.json, template -> symlink
chat.jsonl           история сообщений чата (роль, текст, вызовы инструментов, версия)
```

`typst_deck/store.py`: `create`, `load`, `save` (с инкрементом версии и
снимком), `list_versions`, `revert`, `add_asset`, `add_upload`, `append_chat`,
`read_chat`. Запись `deck.json` — через временный файл и `os.replace`.
Блокировка на колоду — `asyncio.Lock` в процессе (один процесс по
условию первой версии).

## 7. LLM-слой

`typst_deck/llm/`:

- `client.py` — протокол `LLM` с одним методом
  `complete(messages, tools) -> Completion` (текст и/или список вызовов
  инструментов). Реализации: `OpenAICompatLLM` (httpx, chat completions с
  `tools`, переменные `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`;
  `DEEPSEEK_*` из стека принимаются как синонимы) и `FakeLLM` для тестов
  (скриптованные ответы).
- `tools.py` — инструменты для модели внутри сервиса:
  `set_deck(title, slides)` (полная сборка при создании), `update_slide(slide_id,
  patch)`, `add_slide(slide, after)`, `remove_slide(slide_id)`,
  `move_slide(slide_id, to_index)`, `finish(summary)`. Схемы аргументов
  выводятся из Pydantic. Каждый вызов валидируется; ошибка валидации
  возвращается модели текстом, цикл продолжается.
- `agent.py` — цикл `run(deck, user_message, context_files) -> Outcome`:
  системный промпт (роль, правила, JSON-схема слайдов, список ассетов,
  краткая документация типов слайдов), история чата, текст файлов; до
  12 итераций вызовов инструментов; по `finish` или ответу без вызовов —
  выход. Итог: новая версия колоды (если были правки), текстовый ответ для
  чата, список применённых операций. Рендер запускается после цикла один
  раз.
- Системный промпт лежит в `typst_deck/llm/prompt.md` и собирается
  шаблонизацией простыми подстановками, без Jinja.

Извлечение текста из файлов (`typst_deck/extract.py`): `.txt`, `.md` как
есть; `.docx` через `python-docx` (абзацы и таблицы в Markdown-таблицы);
`.xlsx` через `openpyxl` (каждый лист как Markdown-таблица, не более 200
строк на лист); `.csv` как таблица. Лимит итогового текста 60k символов с
пометкой об усечении. Картинки (`png/jpg/svg`) идут в `assets/`, не в текст.

## 8. HTTP API

FastAPI, префикс `/api`. Все ответы JSON. Ошибки — `{"error": {"code",
"message"}}`.

Колоды и файлы:

- `POST /api/uploads` (multipart) → `{upload_id, name, kind: "text"|"image", chars}`.
  Загрузка без колоды, чтобы форму создания можно было заполнить до
  генерации; при создании колоды файлы копируются в её каталог.
- `POST /api/decks` `{brief, upload_ids: []}` → `202 {deck_id, job_id}`.
  Создаёт колоду со статусом `generating` и запускает задачу.
- `GET /api/decks/{id}` → `{deck, status, version, pdf_url, edit_url, warnings}`.
- `GET /api/decks/{id}/slides/{n}.svg`, `GET /api/decks/{id}/deck.pdf`,
  `GET /api/decks/{id}/positions` → массив позиций полей текущей сборки.
- `PATCH /api/decks/{id}/slides/{slide_id}` `{patch}` → новая версия и
  рендер, ответ как у `GET`. Ручная правка.
- `POST /api/decks/{id}/slides` `{slide, after}`, `DELETE .../slides/{slide_id}`,
  `POST .../slides/{slide_id}/move {to_index}`.
- `POST /api/decks/{id}/assets` (multipart) → `{asset_id}`.
- `GET /api/decks/{id}/versions`, `POST /api/decks/{id}/revert {version}`.
- `POST /api/decks/{id}/messages` `{text}` → `202 {job_id}`; правка через чат.
- `GET /api/decks/{id}/chat` → история.
- `GET /api/jobs/{job_id}` → `{status: queued|running|done|failed, error, deck_version}`.

Для чат-бота (тонкие обёртки, синхронные — ждут завершения задачи до
таймаута 180 с, потом отдают `status: generating` и `deck_id`):

- `POST /api/agent/create_deck` `{brief, files: [{name, content_base64}]}` →
  `{deck_id, status, pdf_url, edit_url, outline}`.
- `POST /api/agent/revise_deck` `{deck_id, request}` → то же.
- `GET /api/agent/decks/{deck_id}` → то же.

`outline` — список `{n, type, title}`, чтобы бот мог пересказать структуру.
`edit_url` — абсолютная ссылка на `/d/{deck_id}` с учётом `PUBLIC_BASE_URL`.

Задачи: `typst_deck/jobs.py`, реестр в памяти, исполнение через
`asyncio.create_task`; на колоду не более одной активной задачи (вторая
получает 409).

## 9. Веб-интерфейс

Статика без сборки: `typst_deck/static/` (`index.html`, `deck.html`,
`app.js`, `deck.js`, `style.css`), ES-модули, без фреймворков. Все пути
относительные, чтобы работать под префиксом за Nginx.

- `/` — форма создания: задание, загрузка файлов, кнопка «Создать
  презентацию», прогресс, переход на `/d/{deck_id}`.
- `/d/{deck_id}` — чат слева (около трети ширины), превью справа: список
  SVG-страниц одна под другой, над каждой прозрачный слой с зонами полей из
  `positions`. Клик по зоне открывает всплывающий редактор: текст для
  строковых полей, многострочный (строка = пункт) для буллетов, выбор
  размера и загрузка картинки для `image`. Сохранение → `PATCH` →
  перезагрузка SVG. Клик по слайду вне зон — панель со всеми полями слайда
  (запасной путь, если координаты не сошлись). Кнопки: скачать PDF,
  добавить слайд, удалить, история версий с откатом.
- Чат: отправка → `202` → опрос задачи раз в секунду → обновление превью
  и ответа.

## 10. Конфигурация

Переменные окружения с префиксом `TYPST_DECK_` (pydantic-settings):
`DATA_DIR` (по умолчанию `./data`), `TEMPLATE_DIR` (`./template`),
`TYPST_BIN` (`typst`), `PUBLIC_BASE_URL` (`""` — относительные ссылки),
`LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_MAX_TOKENS` (4096),
`MAX_UPLOAD_MB` (20). При отсутствии `LLM_API_KEY` сервис стартует, ручная
правка работает, генерация возвращает 503 с внятным текстом.

## 11. Тестирование

`pytest`, `uv` для окружения. Автотесты обязательны для всего, кроме статики.

- Модель: валидные и невалидные слайды, патчи, ограничения длины, связь
  `labels`/`series`.
- Рендерер: экранирование, golden-файлы `.typ` для эталонной колоды из всех
  шести типов; тест на «одна функция — одна страница» против заглушки.
- Компиляция: интеграционные тесты с реальным `typst` (пропускаются, если
  бинарника нет), проверка числа страниц, наличия SVG, что позиции
  возвращаются для каждого текстового поля.
- Хранилище: версии, откат, атомарность записи (симуляция обрыва).
- LLM-цикл с `FakeLLM`: создание колоды, правка одного поля, ошибка
  валидации возвращается модели и исправляется на следующей итерации,
  лимит итераций.
- API через `httpx.AsyncClient` и `ASGITransport`: полный сценарий
  «загрузка → создание → ожидание задачи → патч → PDF → откат», а также
  агентские обёртки.
- Извлечение текста: docx и xlsx собираются в тестах программно.

## 12. Структура репозитория

```
pyproject.toml            uv, зависимости: fastapi, uvicorn, pydantic,
                          pydantic-settings, httpx, python-multipart,
                          python-docx, openpyxl; dev: pytest, pytest-asyncio
src/typst_deck/
  model.py  render.py  store.py  jobs.py  extract.py  config.py  app.py
  api/  (decks.py, uploads.py, agent.py, jobs.py)
  llm/  (client.py, tools.py, agent.py, prompt.md)
  typst/fields.typ
  static/
template/                 заглушка; корпоративный шаблон кладётся сюда же
tests/
docs/superpowers/specs/, docs/superpowers/plans/
Dockerfile                python:3.12-slim + бинарник typst + fonts
```

## 13. Риски и решения

- **Координаты не сошлись с SVG** (сложная вёрстка в корпоративном
  шаблоне): запасной путь — панель полей слайда, работает всегда.
- **Модель без tool calling**: `OpenAICompatLLM` содержит запасной режим
  `LLM_TOOL_MODE=json`, где инструменты описаны в промпте, а ответ ждётся
  JSON-объектом `{tool, args}`; включается переменной, тестируется
  с `FakeLLM` так же.
- **Долгая генерация в агентских обёртках**: синхронное ожидание до 180 с,
  дальше бот получает `deck_id` и опрашивает `GET`.
- **Typst-пакеты недоступны в корпоративной сети**: заглушка и рендерер
  не используют `@preview`; для корпоративного шаблона это требование
  контракта либо заранее прогретый `~/.cache/typst`.
