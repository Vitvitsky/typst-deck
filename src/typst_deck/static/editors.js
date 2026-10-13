// Редакторы составных полей панели «Слайд». Вверху — чистые функции разбора и
// проверки: их гоняет node --test (tests/js/editors.test.mjs); ниже — DOM-редакторы.
// Пределы — те же, что в model.py: сервер проверит всё равно, а здесь человек
// узнаёт об ошибке до отправки и по-русски, без пути поля.
import { el, KIND_RU } from "./api.js";

export const LIMITS = {
  items: [3, 7], blocks: [2, 3], metrics: [2, 4], images: [2, 4], header: [2, 6], rows: [1, 8],
  series: [1, 4], sideSeries: [1, 3], sideBullets: [1, 5],
};

export const lines = (text) => String(text).split("\n").map((s) => s.trim()).filter(Boolean);

// «12,5», «1 200», «1 200,75»: запятая — десятичная, пробелы внутри числа — разряды
export function parseNumber(s) {
  const t = String(s).replace(/[\s ]/g, "").replace(",", ".");
  return t === "" ? NaN : Number(t);
}
// значения ряда разделяет «;» — запятая занята десятичной дробью
export const parseValues = (text) => String(text).split(";").map((s) => s.trim()).filter(Boolean).map(parseNumber);
export const formatValues = (values) => values.map((v) => String(v).replace(".", ",")).join("; ");

export function countError(n, [min, max], what) {
  if (n < min) return `${what}: нужно не меньше ${min}`;
  if (n > max) return `${what}: можно не больше ${max}`;
  return null;
}

const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
};

export function seriesError(series, nLabels) {
  for (const s of series) {
    const name = s.name || "без названия";
    if (s.values.some((v) => Number.isNaN(v))) return `Ряд «${name}»: не число среди значений`;
    if (s.values.length !== nLabels) {
      return `Ряд «${name}»: ${s.values.length} ${plural(s.values.length, "значение", "значения", "значений")}`
        + ` при ${nLabels} ${plural(nLabels, "подписи", "подписях", "подписях")}`;
    }
  }
  return null;
}

export const dropBlank = (rows) => rows.filter((r) => Object.values(r).some((v) => String(v ?? "").trim() !== ""));

export function tableFrom(header, rows) {
  const body = rows.filter((r) => r.some((c) => String(c).trim()));
  return { header: header.map((h) => h.trim()), rows: body.map((r) => r.map((c) => String(c).trim())) };
}

export const linkError = (url) => /^https?:\/\/\S+$/i.test(String(url).trim())
  ? null : "Ссылка должна начинаться с http:// или https://";

// Плеер собирается из распознанного id, а не из исходной строки: в iframe не
// попадает ничего, кроме адреса встраивания известной платформы (ADR 0022).
// Хост сверяется целиком: youtube.com.evil.ru — не YouTube.
const host = (u) => u.hostname.replace(/^(www\.|m\.)/, "");
export function embedUrl(url) {
  let u;
  try { u = new URL(String(url).trim()); } catch { return null; }
  if (!/^https?:$/.test(u.protocol)) return null;
  const h = host(u), path = u.pathname;
  let m;
  if (h === "youtube.com" || h === "youtube-nocookie.com") {
    const id = path === "/watch" ? u.searchParams.get("v") : (path.match(/^\/(?:shorts|embed|live)\/([^/]+)/) || [])[1];
    return /^[\w-]{11}$/.test(id || "") ? `https://www.youtube-nocookie.com/embed/${id}` : null;
  }
  if (h === "youtu.be") {
    const id = path.slice(1);
    return /^[\w-]{11}$/.test(id) ? `https://www.youtube-nocookie.com/embed/${id}` : null;
  }
  if (h === "rutube.ru" && (m = path.match(/^\/(?:video|play\/embed)\/([0-9a-f]{32})\/?$/))) {
    return `https://rutube.ru/play/embed/${m[1]}`;
  }
  if ((h === "vk.com" || h === "vkvideo.ru" || h === "vk.ru") && (m = path.match(/^\/video(-?\d+)_(\d+)\/?$/))) {
    return `https://vk.com/video_ext.php?oid=${m[1]}&id=${m[2]}`;
  }
  if (h === "vimeo.com" && (m = path.match(/^\/(\d+)\/?$/))) return `https://player.vimeo.com/video/${m[1]}`;
  return null;
}

export function changed(fragment, slide) {
  return Object.fromEntries(Object.entries(fragment).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(slide[k])));
}

// ---------------- DOM. Договор редактора: {node, read()}; read асинхронен (может
// грузить файлы), возвращает фрагмент правки и бросает Error с текстом для человека.
const fail = (msg) => { if (msg) throw new Error(msg); };
const label = (text) => el("label", { class: "f" }, text);

export const PANEL = {
  agenda: ["items"], columns: ["blocks"], comparison: ["left", "right"],
  chart: ["kind", "labels", "series", "unit"], "dual-chart": ["left", "right"], metrics: ["items"],
  table: ["header", "rows"], gallery: ["images"], video: ["url", "poster"],
};

function listEditor(field, values, limits, what) {
  const t = el("textarea", { rows: Math.max(3, values.length + 1), placeholder: "По одному на строку", "aria-label": what }, values.join("\n"));
  return { node: el("div", {}, label(what), t), read: async () => { const v = lines(t.value); fail(countError(v.length, limits, what)); return { [field]: v }; } };
}

function rowsEditor(field, items, columns, limits, what) {
  const box = el("div", { class: "grid-table rows-edit" });
  const raw = () => [...box.querySelectorAll(".r")].map((r) =>
    Object.fromEntries([...r.querySelectorAll("[data-key]")].map((i) => [i.dataset.key, i.value.trim()])));
  const blank = Object.fromEntries(columns.map((c) => [c.key, ""]));
  const draw = (list) => box.replaceChildren(
    ...list.map((item, i) => el("div", { class: "r" },
      el("div", { class: "cells" }, ...columns.map((c) => c.long
        ? el("textarea", { "data-key": c.key, rows: 2, placeholder: c.label, "aria-label": `${c.label}, ${i + 1}` }, item[c.key] ?? "")
        : el("input", { type: "text", "data-key": c.key, value: item[c.key] ?? "", placeholder: c.label, "aria-label": `${c.label}, ${i + 1}` }))),
      el("button", { type: "button", class: "quiet icon sm", title: "Убрать", onclick: () => { const cur = raw(); cur.splice(i, 1); draw(cur); } }, "✕"))),
    list.length < limits[1] ? el("button", { type: "button", class: "sm", onclick: () => draw([...raw(), { ...blank }]) }, "＋ Добавить") : null);
  draw(items);
  return { node: el("div", {}, label(what), box),
    read: async () => { const v = dropBlank(raw()); fail(countError(v.length, limits, what)); return { [field]: v }; } };
}

export function blocksEditor(blocks) {
  return rowsEditor("blocks", blocks, [{ key: "heading", label: "Заголовок блока" }, { key: "text", label: "Текст", long: true }],
    LIMITS.blocks, "Блоки текста");
}

export function metricsEditor(items) {
  return rowsEditor("items", items, [{ key: "value", label: "Число" }, { key: "label", label: "Подпись" },
    { key: "delta", label: "Изменение, например +12 %" }], LIMITS.metrics, "Метрики");
}

export function comparisonEditor(slide) {
  const side = (key, what) => {
    const s = slide[key];
    const heading = el("input", { type: "text", value: s.heading, placeholder: "Заголовок колонки", "aria-label": `${what}: заголовок` });
    const bullets = el("textarea", { rows: 4, placeholder: "Пункты, по одному на строку", "aria-label": `${what}: пункты` }, s.bullets.join("\n"));
    return { node: el("fieldset", { class: "group" }, el("legend", {}, what), heading, bullets),
      read: () => { const b = lines(bullets.value); fail(countError(b.length, LIMITS.sideBullets, `${what}, пункты`)); return { heading: heading.value.trim(), bullets: b }; } };
  };
  const l = side("left", "Левая колонка"), r = side("right", "Правая колонка");
  return { node: el("div", {}, l.node, r.node), read: async () => ({ left: l.read(), right: r.read() }) };
}

function seriesEditor(series, nLabelsOf, limits) {
  const box = el("div", { class: "grid-table" });
  const raw = () => [...box.querySelectorAll(".r")].map((r) => ({
    name: r.querySelector('[data-key="name"]').value.trim(), values: parseValues(r.querySelector('[data-key="values"]').value) }));
  const draw = (items) => box.replaceChildren(
    ...items.map((s, i) => el("div", { class: "r series" },
      el("div", {},
        el("input", { type: "text", "data-key": "name", value: s.name, placeholder: "Название ряда", "aria-label": `Название ряда ${i + 1}` }),
        el("input", { type: "text", "data-key": "values", value: formatValues(s.values), placeholder: "Значения через «;», например 12,5; 17",
          "aria-label": `Значения ряда ${i + 1}`, style: "margin-top:4px" })),
      el("button", { type: "button", class: "quiet icon sm", title: "Убрать ряд", onclick: () => { const cur = raw(); cur.splice(i, 1); draw(cur); } }, "✕"))),
    items.length < limits[1] ? el("button", { type: "button", class: "sm", onclick: () => draw([...raw(), { name: "", values: [] }]) }, "＋ Ряд") : null);
  draw(series);
  return { node: box, read: () => {
    const v = raw().filter((s) => s.name || s.values.length);
    fail(countError(v.length, limits, "Ряды данных"));
    fail(seriesError(v, nLabelsOf()));
    return v;
  } };
}

function chartControls(src, limits) {
  const kind = el("select", { "aria-label": "Вид графика" }, ...Object.entries(KIND_RU).map(([k, l]) => el("option", { value: k, selected: src.kind === k }, l)));
  const labels = el("textarea", { rows: 3, placeholder: "По одной на строку", "aria-label": "Подписи по оси" }, src.labels.join("\n"));
  const unit = el("input", { type: "text", value: src.unit || "", "aria-label": "Единица измерения" });
  const series = seriesEditor(src.series, () => lines(labels.value).length, limits);
  return {
    nodes: [label("Вид графика"), kind, label("Подписи по оси"), labels, label("Ряды данных"), series.node, label("Единица измерения"), unit],
    read: () => ({ kind: kind.value, labels: lines(labels.value), series: series.read(), unit: unit.value.trim() }),
  };
}

export function chartEditor(slide) {
  const c = chartControls(slide, LIMITS.series);
  return { node: el("div", {}, ...c.nodes), read: async () => c.read() };
}

export function dualChartEditor(slide) {
  const side = (key, what) => {
    const caption = el("input", { type: "text", value: slide[key].caption, placeholder: "Подпись над графиком", "aria-label": `${what}: подпись` });
    const c = chartControls(slide[key], LIMITS.sideSeries);
    return { node: el("fieldset", { class: "group" }, el("legend", {}, what), caption, ...c.nodes),
      read: () => ({ caption: caption.value.trim(), ...c.read() }) };
  };
  const l = side("left", "Левый график"), r = side("right", "Правый график");
  return { node: el("div", {}, l.node, r.node), read: async () => ({ left: l.read(), right: r.read() }) };
}

export function tableEditor(slide) {
  const box = el("div", { class: "table-edit" });
  let header = [...slide.header];
  let rows = slide.rows.map((r) => [...r]);
  const sync = () => {
    header = [...box.querySelectorAll("thead input")].map((i) => i.value);
    rows = [...box.querySelectorAll("tbody tr")].map((tr) => [...tr.querySelectorAll("input")].map((i) => i.value));
  };
  const cell = (v, what) => el("input", { type: "text", value: v, "aria-label": what });
  const act = (text, fn) => el("button", { type: "button", class: "sm", onclick: () => { sync(); fn(); draw(); } }, text);
  function draw() {
    box.replaceChildren(
      el("div", { class: "scroll" }, el("table", {},
        el("thead", {}, el("tr", {}, ...header.map((h, j) => el("th", {}, cell(h, `Шапка, колонка ${j + 1}`))), el("th", {}))),
        el("tbody", {}, ...rows.map((r, i) => el("tr", {}, ...r.map((c, j) => el("td", {}, cell(c, `Строка ${i + 1}, колонка ${j + 1}`))),
          el("td", {}, el("button", { type: "button", class: "quiet icon sm", title: "Убрать строку",
            onclick: () => { sync(); rows.splice(i, 1); draw(); } }, "✕"))))))),
      el("div", { class: "row" },
        rows.length < LIMITS.rows[1] ? act("＋ Строка", () => rows.push(header.map(() => ""))) : null,
        header.length < LIMITS.header[1] ? act("＋ Колонка", () => { header.push(""); rows.forEach((r) => r.push("")); }) : null,
        header.length > LIMITS.header[0] ? act("− Колонка", () => { header.pop(); rows.forEach((r) => r.pop()); }) : null));
  }
  draw();
  return { node: el("div", {}, label("Таблица"), box),
    read: async () => { sync(); const t = tableFrom(header, rows); fail(countError(t.rows.length, LIMITS.rows, "Строки таблицы")); return t; } };
}

export function compositeEditor(slide, ctx) {
  switch (slide.type) {
    case "agenda": return listEditor("items", slide.items, LIMITS.items, "Пункты повестки");
    case "columns": return blocksEditor(slide.blocks);
    case "comparison": return comparisonEditor(slide);
    case "chart": return chartEditor(slide);
    case "dual-chart": return dualChartEditor(slide);
    case "metrics": return metricsEditor(slide.items);
    case "table": return tableEditor(slide);
    case "gallery": return galleryEditor(slide, ctx);
    case "video": return videoEditor(slide, ctx);
    default: return null;
  }
}

export function galleryEditor() { return { node: el("p", { class: "muted small" }, "Картинки галереи меняются в следующем обновлении"), read: async () => ({}) }; }
export function videoEditor() { return { node: el("p", { class: "muted small" }, "Видео меняется в следующем обновлении"), read: async () => ({}) }; }
