# HTTP API

Маршруты — `src/typst_deck/api/`; живая схема — `/docs` (FastAPI) на запущенном
сервисе.

Для веб-интерфейса: `POST /api/uploads`, `GET /api/decks` (каталог), `POST /api/decks`
(с полем `template`), `PATCH /api/decks/{id}` (название), `POST /api/decks/{id}/template`
(смена шаблона с откатом при ошибке рендера), `DELETE /api/decks/{id}` (в корзину
`data/trash/`), `POST …/uploads` (материалы из чата), `GET /api/templates`,
`GET /api/templates/{id}/preview/{n}.svg`, `GET /api/templates/{id}/schema` (схема слайда с пределами шаблона — по ней панель проверяет длины до отправки), `GET /api/history`,
`GET /api/decks/{id}`, `…/slides/{n}.svg`, `…/deck.pdf`, `…/deck.pptx`, `…/positions`,
`PATCH …/slides/{sid}`, `POST …/slides`, `DELETE …/slides/{sid}`,
`POST …/slides/{sid}/move`, `POST …/assets`, `GET …/assets/{asset}` (картинка колоды; SVG — в песочнице), `GET …/versions`,
`POST …/revert`, `POST …/messages`, `GET …/chat`, `GET /api/jobs/{id}`.

Для чат-бота (синхронные, ждут генерацию до `wait_seconds`):

```
POST /api/agent/create_deck  {brief, files: [{name, content_base64}], template, wait_seconds}
POST /api/agent/revise_deck  {deck_id, request, wait_seconds}
POST /api/agent/render_deck  {deck: {title, slides}, template, files: [{name, content_base64}], deck_id?}
GET  /api/agent/decks/{deck_id}
→ {deck_id, status, pdf_url, pptx_url, edit_url, outline: [{n, type, title}], reply, last_error}
```

Бот про слайды не знает: передаёт задание, получает PDF и ссылку
`edit_url`, которая открывает ту же колоду в веб-интерфейсе. `template` —
id шаблона (`GET /api/templates`), по умолчанию `default`; старый id из алиаса
принимается.

`render_deck` — для агента, у которого колода уже готова: она собирается как
есть, без нейросети, текст попадает на слайды дословно. `deck` — модель колоды
(типы слайдов и поля — схема `GET /api/templates/{id}/schema`); `id`,
`version` и даты в ней не нужны и игнорируются. Картинки слайдов (`image`,
`images[].image`, `poster`) называют файлы из `files`. С `deck_id` колода
переписывается новой версией (прежняя остаётся в истории), без него —
создаётся новая. Ответ ждёт рендер, `reply` пустой. Ошибки проверки — 422,
колода не создаётся и не меняется:

```
{"error": {"code": "validation", "message": "…",
  "fields": [{"path": "slides.2.title", "message": "…", "limit": 60, "actual": 74}]}}
```

`path` — путь в `deck`. `limit` и `actual` есть у ошибок длины. Пределы
шаблона (`slots`) проверяются строго, когда сама колода прошла проверку
модели. Провал рендера — 500 `render` с выводом typst.

MCP-обёртка поверх этих вызовов — следующий шаг.

`pptx_url` — редактируемый PPTX на PowerPoint-мастере шаблона; `null`, если у
шаблона мастера нет (`docs/template-contract.md`, раздел «PowerPoint-мастер»).
Файл собирается на каждый запрос и колоду не меняет.
