import { test } from "node:test";
import assert from "node:assert/strict";
import { LIMITS, lines, parseNumber, parseValues, formatValues, countError, seriesError, dropBlank,
  tableFrom, columnEmpty, merge3, linkError, embedUrl, startSeconds, changed, schemaError, lineLabelsError } from "../../src/typst_deck/static/editors.js";

test("числа по-русски", () => {
  assert.equal(parseNumber("12,5"), 12.5);
  assert.equal(parseNumber("1 200"), 1200);
  assert.equal(parseNumber("1 200,75"), 1200.75);
  assert.equal(parseNumber("-3"), -3);
  assert.ok(Number.isNaN(parseNumber("")));
  assert.ok(Number.isNaN(parseNumber("млн")));
});

test("значения ряда — через точку с запятой, запятая — десятичная", () => {
  assert.deepEqual(parseValues("12,5; 17;  -3 ;"), [12.5, 17, -3]);
  assert.equal(formatValues([12.5, 17, -3]), "12,5; 17; -3");
  assert.deepEqual(parseValues(formatValues([0.25, 1000])), [0.25, 1000]);
});

test("строки — по одной на строку, пустые уходят", () => {
  assert.deepEqual(lines(" раз \n\n два\n"), ["раз", "два"]);
});

test("число элементов в пределах", () => {
  assert.equal(countError(1, LIMITS.images, "Картинки"), "Картинки: нужно не меньше 2");
  assert.equal(countError(5, LIMITS.images, "Картинки"), "Картинки: можно не больше 4");
  assert.equal(countError(3, LIMITS.images, "Картинки"), null);
});

test("ряды сверяются с подписями до отправки", () => {
  assert.equal(seriesError([{ name: "Выручка", values: [1, 2] }], 3), "Ряд «Выручка»: 2 значения при 3 подписях");
  assert.equal(seriesError([{ name: "", values: [1] }], 5), "Ряд «без названия»: 1 значение при 5 подписях");
  assert.equal(seriesError([{ name: "", values: [1, NaN, 3] }], 3), "Ряд «без названия»: не число среди значений");
  assert.equal(seriesError([{ name: "x", values: [1, 2, 3] }], 3), null);
});

test("пустые строки таблиц и списков выбрасываются", () => {
  assert.deepEqual(dropBlank([{ value: "17", label: "" }, { value: " ", label: "" }]), [{ value: "17", label: "" }]);
  assert.deepEqual(tableFrom([" Регион ", "Выручка"], [["Центр", " 42 "], ["", " "]]),
    { header: ["Регион", "Выручка"], rows: [["Центр", "42"]] });
});

test("числа не склеиваются молча", () => {
  for (const bad of ["1, 2", "10 20 30", "1e999", "Infinity", "0x10", "1 20", "12,5,3"]) {
    assert.ok(Number.isNaN(parseNumber(bad)), bad);
  }
  assert.equal(parseNumber("\u22123"), -3);  // типографский минус
  assert.equal(parseNumber("12.5"), 12.5);
  assert.equal(parseNumber("12 345 678,9"), 12345678.9);
});

test("ссылка-пустышка — своя подсказка", () => {
  assert.equal(linkError("https://"), "Вставьте ссылку на ролик целиком: после https:// ничего нет");
  assert.match(linkError("https://a b"), /без пробелов/);
});

test("ссылка видео — только http(s)", () => {
  assert.equal(linkError(" https://disk.yandex.ru/i/abc "), null);
  for (const bad of ["", "javascript:alert(1)", "data:text/html,x", "//host/v", "youtube.com/watch?v=1"]) {
    assert.match(linkError(bad), /http:\/\/ или https:\/\//, bad);
  }
});

test("плееры платформ собираются из распознанного id", () => {
  const yt = "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ";
  assert.equal(embedUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42"), `${yt}?start=42`);
  assert.equal(embedUrl("https://youtu.be/dQw4w9WgXcQ?si=x"), yt);
  assert.equal(embedUrl("https://youtube.com/shorts/dQw4w9WgXcQ"), yt);
  assert.equal(embedUrl("https://rutube.ru/video/0123456789abcdef0123456789abcdef/"),
    "https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef");
  assert.equal(embedUrl("https://vk.com/video-22822305_456242110"), "https://vk.com/video_ext.php?oid=-22822305&id=456242110");
  assert.equal(embedUrl("https://vkvideo.ru/video-1_2"), "https://vk.com/video_ext.php?oid=-1&id=2");
  assert.equal(embedUrl("https://vimeo.com/76979871"), "https://player.vimeo.com/video/76979871");
});

test("чужое и битое открывается вкладкой", () => {
  for (const url of ["https://disk.yandex.ru/i/abc", "https://youtube.com.evil.ru/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=short", "https://rutube.ru/video/", "https://vk.com/video-1_",
    "javascript:alert(1)", "не ссылка"]) {
    assert.equal(embedUrl(url), null, url);
  }
});

test("в правку идут только изменённые поля", () => {
  const slide = { title: "Т", items: ["а", "б", "в"], left: { heading: "Было", bullets: ["x"] } };
  assert.deepEqual(changed({ items: ["а", "б", "в"], left: { heading: "Было", bullets: ["y"] } }, slide),
    { left: { heading: "Было", bullets: ["y"] } });
});

test("последняя колонка пуста — убирается без подтверждения", () => {
  assert.equal(columnEmpty(["Регион", ""], [["Центр", " "], ["Север", ""]]), true);
  assert.equal(columnEmpty(["Регион", "Выручка"], [["Центр", ""]]), false);
  assert.equal(columnEmpty(["Регион", ""], [["Центр", "42"]]), false);
});

test("слияние устаревшей формы: поверх свежего — только то, что менял человек", () => {
  // человек правил заголовок левой колонки, модель тем временем — её пункты
  const base = { heading: "Было", bullets: ["а"] };
  assert.deepEqual(merge3(base, { heading: "Раньше", bullets: ["а"] }, { heading: "Было", bullets: ["б", "в"] }),
    { heading: "Раньше", bullets: ["б", "в"] });
  // человек ничего не менял — остаётся свежее
  assert.deepEqual(merge3(base, base, { heading: "Новое", bullets: [] }), { heading: "Новое", bullets: [] });
  // сервер не менял — уходит ввод
  assert.equal(merge3("Было", "Стало", "Было"), "Стало");
  // списки одной длины — по позициям: метрики, где человек правил первую, модель вторую
  const items = [{ value: "1", label: "а" }, { value: "2", label: "б" }];
  assert.deepEqual(merge3(items, [{ value: "10", label: "а" }, items[1]], [items[0], { value: "2", label: "бб" }]),
    [{ value: "10", label: "а" }, { value: "2", label: "бб" }]);
  // разная длина — берётся ввод целиком
  assert.deepEqual(merge3(["а"], ["а", "б"], ["в"]), ["а", "б"]);
  // правили одно и то же — побеждает ввод человека
  assert.equal(merge3("Было", "Моё", "Модели"), "Моё");
});

test("отметка времени ссылки доходит до плеера", () => {
  assert.equal(startSeconds("260s"), 260);
  assert.equal(startSeconds("260"), 260);
  assert.equal(startSeconds("4m20s"), 260);
  assert.equal(startSeconds("1h2m3s"), 3723);
  for (const bad of ["", "0", "abc", "4:20", null]) assert.equal(startSeconds(bad), null, String(bad));
  // ссылка 2026-10-13: подпись «с отметки 4:20», а плеер начинал с нуля
  assert.equal(embedUrl("https://www.youtube.com/watch?v=gWotBPtsulo&t=260s"), "https://www.youtube-nocookie.com/embed/gWotBPtsulo?start=260");
  assert.equal(embedUrl("https://youtu.be/gWotBPtsulo?t=4m20s"), "https://www.youtube-nocookie.com/embed/gWotBPtsulo?start=260");
  assert.equal(embedUrl("https://rutube.ru/video/0123456789abcdef0123456789abcdef/?t=90"),
    "https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef?t=90");
  assert.equal(embedUrl("https://vimeo.com/76979871#t=1m30s"), "https://player.vimeo.com/video/76979871#t=90s");
  assert.equal(embedUrl("https://www.youtube.com/watch?v=gWotBPtsulo"), "https://www.youtube-nocookie.com/embed/gWotBPtsulo");
});

// схема в том виде, что отдаёт pydantic (и GET /api/templates/{id}/schema): oneOf по $ref,
// вложенные модели через $ref, необязательное поле — anyOf с null
const SCHEMA = {
  oneOf: [{ $ref: "#/$defs/TextSlide" }, { $ref: "#/$defs/ComparisonSlide" }],
  discriminator: { propertyName: "type", mapping: { text: "#/$defs/TextSlide", comparison: "#/$defs/ComparisonSlide" } },
  $defs: {
    TextSlide: { type: "object", properties: {
      type: { const: "text", type: "string" }, title: { maxLength: 60, type: "string" },
      bullets: { type: "array", maxItems: 6, items: { type: "string", minLength: 1, maxLength: 10 } },
      caption: { anyOf: [{ type: "string", maxLength: 5 }, { type: "null" }] } } },
    ComparisonSlide: { type: "object", properties: {
      type: { const: "comparison", type: "string" }, left: { $ref: "#/$defs/Side" }, right: { $ref: "#/$defs/Side" } } },
    Side: { type: "object", properties: { heading: { maxLength: 4, type: "string" },
      bullets: { type: "array", items: { type: "string", maxLength: 3 } } } },
  },
};

test("длины по схеме шаблона — до отправки и по-русски", () => {
  assert.equal(schemaError(SCHEMA, { type: "text", title: "x".repeat(61), bullets: [] }),
    "Заголовок: 61 знак при пределе 60");
  assert.equal(schemaError(SCHEMA, { type: "text", title: "", bullets: ["ок", "очень длинный"] }),
    "Тезисы, № 2: 13 знаков при пределе 10");
  assert.equal(schemaError(SCHEMA, { type: "text", title: "", bullets: ["", "a"] }), "Тезисы, № 1: пусто");
  assert.equal(schemaError(SCHEMA, { type: "text", title: "", bullets: Array(7).fill("a") }),
    "Тезисы: 7 элементов при пределе 6");
  assert.equal(schemaError(SCHEMA, { type: "text", title: "", bullets: [], caption: "123456" }),
    "Подпись к картинке: 6 знаков при пределе 5");
  assert.equal(schemaError(SCHEMA, { type: "text", title: "", bullets: [], caption: null }), null);
  assert.equal(schemaError(SCHEMA, { type: "comparison", left: { heading: "", bullets: ["abcd"] }, right: { heading: "", bullets: [] } }),
    "Левая колонка · Тезисы, № 1: 4 знака при пределе 3");
  // эмодзи — один знак, как у pydantic, а не две половинки суррогатной пары
  assert.equal(schemaError(SCHEMA, { type: "text", title: "😀".repeat(60), bullets: [] }), null);
  // неизвестный тип и пустая схема — не повод отказывать: сервер всё равно проверит
  assert.equal(schemaError(SCHEMA, { type: "quote", text: "x".repeat(999) }), null);
  assert.equal(schemaError(null, { type: "text" }), null);
});

test("панель судит только изменённое и не строже сервера", () => {
  const old = { type: "text", title: "x".repeat(70), bullets: [] };
  // правка заметок не упирается в давний длинный заголовок (сервер: «не стало хуже», спека §8)
  assert.equal(schemaError(SCHEMA, { ...old, notes: "н" }, { only: ["notes"], before: old }), null);
  // заголовок сократили, но всё ещё длиннее предела — сервер примет, панель тоже
  assert.equal(schemaError(SCHEMA, { ...old, title: "x".repeat(65) }, { only: ["title"], before: old }), null);
  assert.equal(schemaError(SCHEMA, { ...old, title: "x".repeat(71) }, { only: ["title"], before: old }),
    "Заголовок: 71 знак при пределе 60");
  const b = { type: "text", title: "", bullets: ["a".repeat(12), "ок"] };
  assert.equal(schemaError(SCHEMA, { ...b, bullets: ["a".repeat(12), "ок", "в"] }, { only: ["bullets"], before: b }), null);
  assert.equal(schemaError(SCHEMA, { ...b, bullets: ["ок", "a".repeat(13)] }, { only: ["bullets"], before: b }),
    "Тезисы, № 2: 13 знаков при пределе 10");
});

test("линии нужны две подписи", () => {
  assert.equal(lineLabelsError("line", ["Q1"]), "Линейному графику нужны хотя бы две подписи по оси");
  assert.equal(lineLabelsError("line", ["Q1", "Q2"]), null);
  assert.equal(lineLabelsError("bar", ["Q1"]), null);
});
