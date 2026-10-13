"""Браузерная проверка панели «Слайд»: python ui_panel.py <адрес сервиса> <id колоды>.

Запуск — как ui_smoke.py, в контейнере Playwright на сети хоста; в образе нет
пакета playwright, его ставит pip:
  podman run --rm --network host -v "$PWD/scripts:/s:ro" mcr.microsoft.com/playwright/python:v1.49.0-noble \\
    sh -c 'pip install -q --break-system-packages playwright==1.49.0 && python /s/ui_panel.py http://127.0.0.1:8011 <id>'
Колода — свежая, три слайда: text «Тезисы», table с шапкой «Регион, Выручка», metrics «Числа».
Проверяет: после отказа сервера вторая попытка не шлёт прежнее значение; ↑ в ленте
не стирает несохранённый ввод панели; колонка с текстом убирается со второго нажатия.
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
    assert not errors, errors
