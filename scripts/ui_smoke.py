"""Дымовая проверка редакторов в браузере: python ui_smoke.py <адрес сервиса> <id колоды>.

Запуск — в контейнере Playwright на сети хоста (на хосте нет библиотек Chromium):
  podman run --rm --network host -v "$PWD/scripts:/s:ro" mcr.microsoft.com/playwright/python:v1.49.0-noble \\
    python /s/ui_smoke.py http://127.0.0.1:8011 <id>
Колода — образец контракта без слайдов с картинками; правится каждое составное поле.
Колода нужна свежая: правки сценария сохраняются, и на повторном прогоне
сохранять уже нечего («Изменений нет»).
"""
import json
import sys
import urllib.request

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1].rstrip("/")


def call(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read())


def main(deck_id: str):
    slides = call(f"/api/decks/{deck_id}")["deck"]["slides"]
    by_type = {s["type"]: i for i, s in enumerate(slides)}
    with sync_playwright() as p:
        page = p.chromium.launch().new_page(viewport={"width": 1366, "height": 850})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{BASE}/d/{deck_id}")
        page.wait_for_selector(".thumb-item")

        def open_slide(t):
            page.locator(".thumb-item").nth(by_type[t]).click()
            page.locator('.tabs button[data-tab="slide"]').click()

        def clear_toasts():
            # старый тост «Сохранено» от прошлого слайда засчитал бы сохранение,
            # которое ещё идёт, и его поздняя перерисовка стёрла бы следующий ввод
            page.evaluate("document.querySelectorAll('.toast').forEach((t) => t.remove())")

        def save_ok():
            clear_toasts()
            page.locator("#props button[type=submit]").click()
            expect(page.locator(".toast").last).to_have_text("Сохранено")

        open_slide("agenda")  # повестка: пункт добавлен
        page.get_by_label("Пункты повестки").fill("Итоги\nПланы\nРиски\nВопросы")
        save_ok()
        open_slide("table")  # таблица: строка добавлена (в образце их три)
        page.get_by_role("button", name="＋ Строка").click()
        page.get_by_label("Строка 4, колонка 1").fill("Запад")
        page.get_by_label("Строка 4, колонка 2").fill("9")
        page.get_by_label("Строка 4, колонка 3").fill("9 %")
        save_ok()
        open_slide("chart")  # значений меньше, чем подписей, — ошибка до отправки
        page.get_by_label("Значения ряда 1").fill("1; 2")
        page.locator("#props button[type=submit]").click()
        expect(page.locator("#props .error")).to_contain_text("2 значения при 3 подписях")
        page.get_by_label("Значения ряда 1").fill("12,5; 17; -3")
        save_ok()
        for t in ("comparison", "metrics", "columns", "dual-chart"):  # редакторы читаются и сохраняются
            open_slide(t)
            page.locator("#props input[type=text]").first.fill(f"Правка {t}")
            save_ok()
        open_slide("video")  # видео: ссылка YouTube → плеер на странице
        page.get_by_label("Ссылка на видео").fill("https://youtu.be/dQw4w9WgXcQ")
        save_ok()
        page.get_by_role("button", name="▶ Смотреть").click()
        expect(page.locator("#player-frame")).to_have_attribute("src", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ")
        page.get_by_role("button", name="Закрыть").click()
        # клик по зоне составного поля открывает вкладку «Слайд» на его редакторе
        page.locator(f"#slide-{slides[by_type['table']]['id']} .zone").last.click()
        expect(page.locator(".f-group.flash")).to_be_visible()
        assert not errors, errors
    print("ok")


if __name__ == "__main__":
    main(sys.argv[2])
