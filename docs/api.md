# HTTP API

Маршруты — `src/typst_deck/api/`; живая схема — `/docs` (FastAPI) на запущенном
сервисе.

Для веб-интерфейса: `POST /api/uploads`, `GET /api/decks` (каталог), `POST /api/decks`
(с полем `template`), `PATCH /api/decks/{id}` (название), `POST /api/decks/{id}/template`
(смена шаблона с откатом при ошибке рендера), `DELETE /api/decks/{id}` (в корзину
`data/trash/`), `POST …/uploads` (материалы из чата), `GET /api/templates`,
`GET /api/templates/{id}/preview/{n}.svg`, `GET /api/history`,
`GET /api/decks/{id}`, `…/slides/{n}.svg`, `…/deck.pdf`, `…/deck.pptx`, `…/positions`,
`PATCH …/slides/{sid}`, `POST …/slides`, `DELETE …/slides/{sid}`,
`POST …/slides/{sid}/move`, `POST …/assets`, `GET …/versions`,
`POST …/revert`, `POST …/messages`, `GET …/chat`, `GET /api/jobs/{id}`.

Для чат-бота (синхронные, ждут генерацию до `wait_seconds`):

```
POST /api/agent/create_deck  {brief, files: [{name, content_base64}], wait_seconds}
POST /api/agent/revise_deck  {deck_id, request, wait_seconds}
GET  /api/agent/decks/{deck_id}
→ {deck_id, status, pdf_url, pptx_url, edit_url, outline: [{n, type, title}], reply}
```

Бот про слайды не знает: передаёт задание, получает PDF и ссылку
`edit_url`, которая открывает ту же колоду в веб-интерфейсе. MCP-обёртка
поверх этих трёх вызовов — следующий шаг.

`pptx_url` — редактируемый PPTX на PowerPoint-мастере шаблона; `null`, если у
шаблона мастера нет (`docs/template-contract.md`, раздел «PowerPoint-мастер»).
Файл собирается на каждый запрос и колоду не меняет.
