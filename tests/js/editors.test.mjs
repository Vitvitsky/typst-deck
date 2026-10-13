import { test } from "node:test";
import assert from "node:assert/strict";
import { LIMITS, lines, parseNumber, parseValues, formatValues, countError, seriesError, dropBlank,
  tableFrom, columnEmpty, linkError, embedUrl, changed } from "../../src/typst_deck/static/editors.js";

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
  assert.equal(embedUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42"), yt);
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
