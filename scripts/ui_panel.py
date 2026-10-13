"""Браузерная проверка панели «Слайд»: python ui_panel.py <адрес сервиса> <id колоды>.

Запуск — как ui_smoke.py, в контейнере Playwright на сети хоста; в образе нет
пакета playwright, его ставит pip:
  podman run --rm --network host -v "$PWD/scripts:/s:ro" mcr.microsoft.com/playwright/python:v1.49.0-noble \\
    sh -c 'pip install -q --break-system-packages playwright==1.49.0 && python /s/ui_panel.py http://127.0.0.1:8011 <id>'
Колода — свежая, три слайда: text «Тезисы», table с шапкой «Регион, Выручка», metrics «Числа».
Проверяет: после отказа сервера вторая попытка не шлёт прежнее значение; ↑ в ленте,
повторный выбор того же слайда и вкладки не стирают несохранённый ввод; колонка с
текстом убирается со второго нажатия, и подтверждение не «залипает» после 3,5 с;
устаревшая форма при сохранении не затирает правку, пришедшую с сервера.
"""
import sys

from playwright.sync_api import expect, sync_playwright

BASE, DECK = sys.argv[1].rstrip("/"), sys.argv[2]

with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1366, "height": 850})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{BASE}/d/{DECK}")
    page.wait_for_selector(".thumb-item")

    def open_slide(i):
        page.locator(".thumb-item").nth(i).click()
        page.locator('.tabs button[data-tab="slide"]').click()

    open_slide(0)
    title = page.locator("#props input[name=title]")
    title.fill("Очень длинный заголовок " * 20)
    page.locator("#props button[type=submit]").click()
    expect(page.locator("#props .error")).not_to_be_empty()
    title.fill("Тезисы")
    page.locator("#props button[type=submit]").click()
    expect(page.locator(".toast").last).to_contain_text("Изменений нет")
    expect(page.locator("#props .error")).to_be_empty()
    print("ok: после отказа вторая попытка не шлёт прежнее значение, ошибка стёрта")

    open_slide(1)
    page.locator("#props .table-edit tbody input").first.fill("Юг")
    page.locator(".thumb-item").nth(2).hover()
    page.locator(".thumb-item").nth(2).locator("button[title=Выше]").click()
    expect(page.locator(".thumb-item").nth(1)).to_contain_text("Числа")
    expect(page.locator("#props .table-edit tbody input").first).to_have_value("Юг")
    print("ok: ↑ в ленте не стёр ввод в панели")
    page.locator("#props button[type=submit]").click()
    expect(page.locator(".toast").last).to_contain_text("Сохранено")

    cols = lambda: page.locator("#props .table-edit thead input").count()
    page.get_by_role("button", name="＋ Колонка").click()
    page.locator("#props .table-edit thead input").nth(2).fill("План")
    page.get_by_role("button", name="− Колонка").click()
    assert cols() == 3, "колонка с текстом ушла с первого нажатия"
    page.get_by_role("button", name="Убрать колонку с текстом?").click()
    assert cols() == 2
    page.get_by_role("button", name="＋ Колонка").click()
    page.get_by_role("button", name="− Колонка").click()
    assert cols() == 2
    print("ok: колонка с текстом — со второго нажатия, пустая — сразу")

    # подтверждение сбросилось по таймеру — следующее одно нажатие снова только спрашивает
    page.get_by_role("button", name="＋ Колонка").click()
    page.locator("#props .table-edit thead input").nth(2).fill("План")
    page.get_by_role("button", name="− Колонка").click()
    page.wait_for_timeout(4000)
    expect(page.get_by_role("button", name="− Колонка")).to_be_visible()
    page.get_by_role("button", name="− Колонка").click()
    assert cols() == 3, "после сброса подтверждения колонка ушла с одного нажатия"
    # подтверждение взведено, колонку очистили — одно нажатие убирает одну колонку, не две
    page.locator("#props .table-edit thead input").nth(2).fill("")
    page.get_by_role("button", name="Убрать колонку с текстом?").click()
    assert cols() == 2, f"ушло больше одной колонки: {cols()}"
    print("ok: подтверждение не залипает, одно нажатие — одна колонка")

    # повторный выбор того же слайда и вкладки не стирает ввод
    page.locator("#props .table-edit tbody input").first.fill("Запад")
    page.locator(".thumb-item").nth(2).click()  # таблица после ↑ — третья
    page.locator('.tabs button[data-tab="slide"]').click()
    expect(page.locator("#props .table-edit tbody input").first).to_have_value("Запад")
    print("ok: повторный выбор слайда и вкладки не стёр ввод")

    # слайд изменился на сервере, пока человек правил: сохраняется слияние
    sid = page.evaluate("""async (deck) => {
      const d = await (await fetch(`api/decks/${deck}`)).json();
      const t = d.deck.slides.find((s) => s.type === "table");
      const rows = t.rows.map((r) => [...r]); rows[1][1] = "99";
      await fetch(`api/decks/${deck}/slides/${t.id}`, { method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify({ patch: { rows } }) });
      return t.id;
    }""", DECK)
    page.locator(".thumb-item").nth(0).hover()
    page.locator(".thumb-item").nth(0).locator("button[title=Ниже]").click()  # applyResult без смены выбора
    expect(page.locator("#props .stale")).to_be_visible()
    expect(page.locator("#props .table-edit tbody input").first).to_have_value("Запад")
    page.locator("#props button[type=submit]").click()
    expect(page.locator(".toast").last).to_contain_text("Сохранено")
    rows = page.evaluate("async ([deck, sid]) => (await (await fetch(`api/decks/${deck}`)).json()).deck.slides.find((s) => s.id === sid).rows", [DECK, sid])
    assert rows[0][0] == "Запад" and rows[1][1] == "99", rows
    print("ok: устаревшая форма не затёрла правку с сервера")
    assert not errors, errors
