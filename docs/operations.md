# Эксплуатация

Как typst-deck собирается в контейнер, стоит на сервере, выкатывается и
откатывается, и что он пишет в логи. Локальный запуск и переменные окружения —
в [README](../README.md), список переменных с пояснениями — в
[`.env.example`](../.env.example).

## Контейнер

Контейнер (на этом сервере — rootless podman 5.7):

```sh
podman build -t typst-deck .
podman run -p 127.0.0.1:8088:8000 -v typst-deck-data:/data \
  -e DEEPSEEK_API_KEY=… -e DEEPSEEK_MODEL=deepseek-chat typst-deck
```

Файлы сборки называются `Dockerfile` и `.dockerignore` и переименования не
требуют: podman читает их как есть. Образ для Quadlet-юнита собирается
командой `podman build -t localhost/typst-deck:latest .` (см. «Демо на этом
сервере»).

В образ попадают только встроенные шаблоны: на последнем шаге сборки
`python -m typst_deck.templates` проверяет их по контракту, и `podman build`
падает, если какой-то его нарушил. Образ не содержит корпоративных файлов и
может публиковаться. Корпоративный шаблон монтируется при запуске вторым
корнем: `-v ~/projects/<канон>:/corp/<id>:ro -e TYPST_DECK_TEMPLATES_DIR=/app/templates:/corp`.

## Демо на этом сервере

Стек в `~/stack` устроен единообразно, typst-deck встаёт в него тем же
способом, что и `deepseek-web`:

- контейнерами управляет rootless podman через systemd (Quadlet), а не compose:
  юнит `typst-deck.container` версионируется в `~/stack/quadlet/`, работает из
  `~/.config/containers/systemd/`, порт `127.0.0.1:8088:8000`, сеть
  `portfolio-internal`, healthcheck на `/api/health`; юнит монтирует канон
  Lemana Tech вторым корнем шаблонов и держит алиас старого id:
  `Volume=%h/projects/lmru--hr-analytics--design-template:/corp/lemana-tech:ro`,
  `Environment=TYPST_DECK_TEMPLATES_DIR=/app/templates:/corp`,
  `Environment=TYPST_DECK_TEMPLATE_ALIASES=lmru-hr:lemana-tech`;
- выкатка после правки кода — сборка образа и рестарт юнита, они разведены
  намеренно; порядок с меткой отката и проверками — «Выкатка и откат» ниже;
- ключ и модель из уже существующих `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`,
  `DEEPSEEK_MODEL`; замена на внутренний эндпоинт — две переменные;
- путь `/deck/` в `nginx/portfolio.conf` по образцу `/deepseek/`: Basic Auth,
  лимиты, Nginx срезает префикс, страницы используют относительные пути
  (`<base href>`), поэтому префикс им не мешает;
- колоды и загрузки в volume `typst-deck-data` — он в хранилище пользователя,
  а не системном: смотреть `podman volume ls`, а не из-под root.

## Выкатка и откат

1. Тесты на том, что выкатывается, — обычные и с корпоративными шаблонами:
   `uv run pytest -q` и `TYPST_DECK_TEST_TEMPLATES=~/corp-templates uv run pytest -q`.
2. Метка отката на текущий образ:
   `podman tag localhost/typst-deck:latest localhost/typst-deck:pre-<что>`.
3. Сборка: `podman build -t localhost/typst-deck:latest ~/projects/typst-deck`.
   Последний шаг сборки проверяет встроенные шаблоны по контракту и роняет
   сборку, если какой-то его нарушил.
4. `systemctl --user restart typst-deck`.
5. Проверка на живом сервисе:

   ```sh
   curl -s 127.0.0.1:8088/api/health | python3 -m json.tool   # templates: checked true, broken {}, pptx_off {}
   curl -s 127.0.0.1:8088/api/templates                        # pptx: true у шаблонов с мастером
   curl -s -o /dev/null -w "%{http_code}\n" 127.0.0.1:8088/api/decks/<id>/deck.pdf
   curl -s -o /dev/null -w "%{http_code}\n" 127.0.0.1:8088/api/decks/<id>/deck.pptx
   ```

Откат — вернуть метку и перезапустить:
`podman tag localhost/typst-deck:pre-<что> localhost/typst-deck:latest && systemctl --user restart typst-deck`.
Колоды откат не трогает: они в volume `typst-deck-data`.

### Правка канона

Канон Lemana Tech смонтирован в сервис живым каталогом: правка его файлов —
даже незакоммиченная — сразу видна пользователям, рестарт не нужен.

- Новое поле в `template.json` или `pptx.json` — сначала выкатить typst-deck,
  который его знает (шаги выше), потом править канон. Старая версия отвергает
  неизвестные ключи `pptx.json`, и экспорт в PPTX отвечает 422 — так 2026-09-11
  сломалось поле `font`, пока его не откатили.
- Правку готовить на копии канона (git worktree) и проверять там:
  `docs/template-contract.md`, раздел «Подключение».
- После правки — пункт 5 выше: `/api/health` и выгрузка PDF и PPTX. Стартовая
  проверка шаблонов идёт только при запуске: чтобы `/api/health` проверил новый
  канон, перезапустить сервис.
- Готовые сборки живых колод (`build/`: превью, зоны полей, PDF) правка канона
  не трогает — они обновятся при первой правке колоды. Чтобы новый вид увидели
  сразу, удалить `build/` живых колод, сервис соберёт его при первом открытии:
  `podman exec typst-deck sh -c 'rm -rf /data/decks/*/build'` — когда ни одна
  колода не генерируется (`status` в `GET /api/decks/<id>`). То же — после
  выкатки, меняющей `deck.typ` колод или `fields.typ`.

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
