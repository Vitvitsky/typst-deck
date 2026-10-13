// Редакторы составных полей панели «Слайд». Вверху — чистые функции разбора и
// проверки: их гоняет node --test (tests/js/editors.test.mjs); ниже — DOM-редакторы.
// Пределы — те же, что в model.py: сервер проверит всё равно, а здесь человек
// узнаёт об ошибке до отправки и по-русски, без пути поля.
import { el, armConfirm, KIND_RU, FIELD_RU } from "./api.js";

export const LIMITS = {
  items: [3, 7], blocks: [2, 3], metrics: [2, 4], images: [2, 4], header: [2, 6], rows: [1, 8],
  series: [1, 4], sideSeries: [1, 3], sideBullets: [1, 5],
};

export const lines = (text) => String(text).split("\n").map((s) => s.trim()).filter(Boolean);

// «12,5», «1 200», «1 200,75», «−3»: запятая — десятичная, пробел — только между
// разрядами по три цифры. «1, 2» и «10 20 30» — не число, а не молча 1,2 и 102030:
// значения ряда раньше вводили через запятую и пробел, и склейка дала бы неверный график.
const NUM = /^-?(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,]\d+)?$/;
export function parseNumber(s) {
  const t = String(s).trim().replace(/\u2212/g, "-");
  if (!NUM.test(t)) return NaN;
  const v = Number(t.replace(/[ \u00a0]/g, "").replace(",", "."));
  return Number.isFinite(v) ? v : NaN;
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

export const lineLabelsError = (kind, labels) =>
  kind === "line" && labels.length < 2 ? "Линейному графику нужны хотя бы две подписи по оси" : null;

// подполя вложенных моделей: метрика, блок, ряд, сторона сравнения
const SUBFIELD_RU = { heading: "Заголовок", name: "Название ряда", value: "Число", label: "Подпись", delta: "Изменение" };

// Первая ошибка длины или числа элементов в слайде по схеме шаблона
// (GET /api/templates/{id}/schema — схема модели, суженная slots). Неизвестное
// схеме не судим: последнее слово — за сервером. only — поля, которые человек
// менял; before — слайд до правки: как и сервер (slots._excess, спека §8),
// панель не отказывает, если нарушение не стало хуже прежнего.
export function schemaError(schema, slide, { only = null, before = null } = {}) {
  if (!schema || !slide) return null;
  const defs = schema.$defs || {};
  const deref = (s) => { for (let i = 0; s && s.$ref && i < 20; i++) s = defs[s.$ref.split("/").pop()]; return s; };
  const root = (schema.oneOf || []).map(deref).find((d) => d?.properties?.type?.const === slide.type);
  // у двух графиков стороны — графики, а не колонки, как в подписи их рамок
  const top = slide.type === "dual-chart" ? { left: "Левый график", right: "Правый график" } : {};
  const name = (path) => path.map((p, i) => typeof p === "number" ? `№ ${p + 1}`
    : (i === 0 ? top[p] || FIELD_RU[p] : SUBFIELD_RU[p] || FIELD_RU[p]) || p)
    .join(" · ").replace(/ · (№ \d+)/g, ", $1");
  const len = (v) => typeof v === "string" ? [...v].length : Array.isArray(v) ? v.length : -1;
  // длинных строк списка не стало больше и они не выросли — сравнение попарно, как в _excess
  const worseStrings = (now, was, max) => {
    const over = now.filter((x) => typeof x === "string" && len(x) > max).map(len).sort((a, b) => b - a);
    const kept = (Array.isArray(was) ? was : []).filter((x) => typeof x === "string" && len(x) > max).map(len).sort((a, b) => b - a);
    return over.some((n, i) => i >= kept.length || n > kept[i]);
  };
  const walk = (s, v, path, was) => {
    s = deref(s);
    if (!s || v == null) return null;
    if (s.anyOf) {
      const alt = s.anyOf.map(deref).find((a) => a && a.type !== "null");
      return alt ? walk(alt, v, path, was) : null;
    }
    if (typeof v === "string") {
      const n = len(v);  // знаки, а не UTF-16: так считает pydantic
      if (s.minLength && n < s.minLength) return `${name(path)}: пусто`;
      if (s.maxLength != null && n > s.maxLength && !(len(was) >= n)) {
        return `${name(path)}: ${n} ${plural(n, "знак", "знака", "знаков")} при пределе ${s.maxLength}`;
      }
      return null;
    }
    if (Array.isArray(v)) {
      if (s.maxItems != null && v.length > s.maxItems && !(len(was) >= v.length)) {
        return `${name(path)}: ${v.length} ${plural(v.length, "элемент", "элемента", "элементов")} при пределе ${s.maxItems}`;
      }
      const item = deref(s.items);
      const flat = item && item.type === "string" && item.maxLength != null;
      if (flat && was !== undefined && !worseStrings(v, was, item.maxLength)) {
        // длины в норме по правилу «не хуже»; пустые строки всё равно недопустимы
        const i = v.findIndex((x) => item.minLength && typeof x === "string" && len(x) < item.minLength);
        return i < 0 ? null : `${name([...path, i])}: пусто`;
      }
      for (let i = 0; i < v.length; i++) {
        const e = walk(s.items, v[i], [...path, i], Array.isArray(was) ? was[i] : undefined);
        if (e) return e;
      }
      return null;
    }
    if (typeof v === "object" && s.properties) {
      for (const [k, sub] of Object.entries(s.properties)) {
        if (path.length === 0 && only && !only.includes(k)) continue;
        const e = walk(sub, v[k], [...path, k], was && typeof was === "object" ? was[k] : undefined);
        if (e) return e;
      }
    }
    return null;
  };
  return root ? walk(root, slide, [], before && before.type === slide.type ? before : undefined) : null;
}

export const dropBlank = (rows) => rows.filter((r) => Object.values(r).some((v) => String(v ?? "").trim() !== ""));

// Трёхстороннее слияние для формы, которая устарела, пока человек правил: base —
// значение, с которого начали править, mine — из формы, theirs — свежее с сервера
// (ответ модели, возврат версии). Где человек ничего не менял — остаётся theirs;
// объекты сливаются по ключам, списки одной длины — по позициям, иначе берётся mine.
export function merge3(base, mine, theirs) {
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  if (same(mine, base)) return theirs;
  if (same(theirs, base) || theirs === undefined) return mine;
  const obj = (x) => x && typeof x === "object" && !Array.isArray(x);
  if (obj(base) && obj(mine) && obj(theirs)) {
    const out = {};
    for (const k of new Set([...Object.keys(theirs), ...Object.keys(mine)])) {
      const v = merge3(base[k], mine[k], theirs[k]);
      if (v !== undefined) out[k] = v;
    }
    return out;
  }
  if (Array.isArray(base) && Array.isArray(mine) && Array.isArray(theirs)
      && base.length === mine.length && mine.length === theirs.length) {
    return mine.map((m, i) => merge3(base[i], m, theirs[i]));
  }
  return mine;
}

// последняя колонка пуста — в шапке и во всех строках только пробелы
export function columnEmpty(header, rows) {
  return [header, ...rows].every((r) => !String(r[r.length - 1] ?? "").trim());
}

export function tableFrom(header, rows) {
  const body = rows.filter((r) => r.some((c) => String(c).trim()));
  return { header: header.map((h) => h.trim()), rows: body.map((r) => r.map((c) => String(c).trim())) };
}

// то же правило, что VIDEO_URL в model.py: схема, адрес, без пробелов и управляющих символов
export function linkError(url) {
  const u = String(url).trim();
  if (/^https?:\/\/$/i.test(u)) return "Вставьте ссылку на ролик целиком: после https:// ничего нет";
  if (!/^https?:\/\//i.test(u)) return "Ссылка должна начинаться с http:// или https://";
  return /^https?:\/\/[^\s\x00-\x1f\x7f/?#][^\s\x00-\x1f\x7f]*$/i.test(u) ? null : "Нужна ссылка на ролик целиком, без пробелов";
}

// Плеер собирается из распознанного id, а не из исходной строки: в iframe не
// попадает ничего, кроме адреса встраивания известной платформы (ADR 0022).
// Хост сверяется целиком: youtube.com.evil.ru — не YouTube.
const host = (u) => u.hostname.replace(/^(www\.|m\.)/, "");
// Отметка времени ссылки в секундах: «260», «260s», «4m20s», «1h2m3s»; иначе null.
// Без неё плеер начинал с нуля, хотя ссылка (и подпись слайда) — «с 4:20».
export function startSeconds(t) {
  const m = /^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$/.exec(String(t || "").trim());
  if (!m || !(m[1] || m[2] || m[3])) return null;
  const sec = (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0);
  return sec > 0 ? sec : null;
}

export function embedUrl(url) {
  let u;
  try { u = new URL(String(url).trim()); } catch { return null; }
  if (!/^https?:$/.test(u.protocol)) return null;
  const h = host(u), path = u.pathname;
  const at = startSeconds(u.searchParams.get("t") || u.searchParams.get("start"));
  const yt = (id) => `https://www.youtube-nocookie.com/embed/${id}${at ? `?start=${at}` : ""}`;
  let m;
  if (h === "youtube.com" || h === "youtube-nocookie.com") {
    const id = path === "/watch" ? u.searchParams.get("v") : (path.match(/^\/(?:shorts|embed|live)\/([^/]+)/) || [])[1];
    return /^[\w-]{11}$/.test(id || "") ? yt(id) : null;
  }
  if (h === "youtu.be") {
    const id = path.slice(1);
    return /^[\w-]{11}$/.test(id) ? yt(id) : null;
  }
  if (h === "rutube.ru" && (m = path.match(/^\/(?:video|play\/embed)\/([0-9a-f]{32})\/?$/))) {
    return `https://rutube.ru/play/embed/${m[1]}${at ? `?t=${at}` : ""}`;
  }
  if ((h === "vk.com" || h === "vkvideo.ru" || h === "vk.ru") && (m = path.match(/^\/video(-?\d+)_(\d+)\/?$/))) {
    return `https://vk.com/video_ext.php?oid=${m[1]}&id=${m[2]}`;
  }
  if (h === "vimeo.com" && (m = path.match(/^\/(\d+)\/?$/))) {
    const vt = startSeconds((u.hash.match(/^#t=(.+)$/) || [])[1]);
    return `https://player.vimeo.com/video/${m[1]}${vt ? `#t=${vt}s` : ""}`;
  }
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
      el("button", { type: "button", class: "quiet icon sm", title: "Убрать", "aria-label": `${what}: убрать ${i + 1}`, onclick: () => { const cur = raw(); cur.splice(i, 1); draw(cur); } }, "✕"))),
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
      el("button", { type: "button", class: "quiet icon sm", title: "Убрать ряд", "aria-label": `Убрать ряд ${i + 1}`, onclick: () => { const cur = raw(); cur.splice(i, 1); draw(cur); } }, "✕"))),
    items.length < limits[1] ? el("button", { type: "button", class: "sm", onclick: () => draw([...raw(), { name: "", values: [] }]) }, "＋ Ряд") : null);
  draw(series);
  return { node: box, read: () => {
    const v = raw().filter((s) => s.name || s.values.length);
    fail(countError(v.length, limits, "Ряды данных"));
    fail(seriesError(v, nLabelsOf()));
    return v;
  } };
}

function chartControls(src, limits, what = "") {
  const kind = el("select", { "aria-label": "Вид графика" }, ...Object.entries(KIND_RU).map(([k, l]) => el("option", { value: k, selected: src.kind === k }, l)));
  const labels = el("textarea", { rows: 3, placeholder: "По одной на строку", "aria-label": "Подписи по оси" }, src.labels.join("\n"));
  const unit = el("input", { type: "text", value: src.unit || "", "aria-label": "Единица измерения" });
  const series = seriesEditor(src.series, () => lines(labels.value).length, limits);
  return {
    nodes: [label("Вид графика"), kind, label("Подписи по оси"), labels, label("Ряды данных"), series.node, label("Единица измерения"), unit],
    read: () => {
      const e = lineLabelsError(kind.value, lines(labels.value));
      fail(e && (what ? `${what}: ${e[0].toLowerCase()}${e.slice(1)}` : e));
      return { kind: kind.value, labels: lines(labels.value), series: series.read(), unit: unit.value.trim() };
    },
  };
}

export function chartEditor(slide) {
  const c = chartControls(slide, LIMITS.series);
  return { node: el("div", {}, ...c.nodes), read: async () => c.read() };
}

export function dualChartEditor(slide) {
  const side = (key, what) => {
    const caption = el("input", { type: "text", value: slide[key].caption, placeholder: "Подпись над графиком", "aria-label": `${what}: подпись` });
    const c = chartControls(slide[key], LIMITS.sideSeries, what);
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
          el("td", {}, el("button", { type: "button", class: "quiet icon sm", title: "Убрать строку", "aria-label": `Убрать строку ${i + 1}`,
            onclick: () => { sync(); rows.splice(i, 1); draw(); } }, "✕"))))))),
      el("div", { class: "row" },
        rows.length < LIMITS.rows[1] ? act("＋ Строка", () => rows.push(header.map(() => ""))) : null,
        header.length < LIMITS.header[1] ? act("＋ Колонка", () => { header.push(""); rows.forEach((r) => r.push("")); }) : null,
        header.length > LIMITS.header[0] ? dropColumn() : null));
  }
  // последняя колонка с текстом убирается со второго нажатия: одно случайное
  // нажатие стирало шапку и ячейки целого столбца
  function dropColumn() {
    const drop = () => { sync(); header.pop(); rows.forEach((r) => r.pop()); draw(); };
    const btn = el("button", { type: "button", class: "sm" }, "− Колонка");
    btn.addEventListener("click", () => {
      if (btn.dataset.armed) return;  // второе нажатие подтверждает слушатель armConfirm — убрать один раз
      sync();
      if (!columnEmpty(header, rows)) armConfirm(btn, "Убрать колонку с текстом?", drop);
      else drop();
    });
    return btn;
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

function filePick(accept, text, onFile) {
  const input = el("input", { type: "file", accept, hidden: true });
  input.addEventListener("change", () => { if (input.files[0]) onFile(input.files[0]); input.value = ""; });
  return el("span", {}, input, el("button", { type: "button", class: "sm", onclick: () => input.click() }, text));
}

export function galleryEditor(slide, ctx) {
  const box = el("div", { class: "gallery-edit" });
  const items = slide.images.map((p) => ({ ...p }));
  const draw = () => box.replaceChildren(
    ...items.map((p, i) => el("div", { class: "r" },
      el("img", { src: p.file ? URL.createObjectURL(p.file) : ctx.assetUrl(p.image), alt: "", class: "thumb" }),
      el("input", { type: "text", value: p.caption, placeholder: "Подпись", "aria-label": `Подпись картинки ${i + 1}`,
        oninput: (e) => { p.caption = e.target.value; } }),
      el("button", { type: "button", class: "quiet icon sm", title: "Убрать картинку", "aria-label": `Убрать картинку ${i + 1}`, onclick: () => { items.splice(i, 1); draw(); } }, "✕"))),
    items.length < LIMITS.images[1] ? filePick(".png,.jpg,.jpeg,.svg", "＋ Картинка", (file) => { items.push({ file, caption: "" }); draw(); }) : null);
  draw();
  return { node: el("div", {}, label("Картинки галереи"), box), read: async () => {
    // число — до загрузки: иначе файлы уйдут на сервер, а слайд всё равно отклонится
    fail(countError(items.length, LIMITS.images, "Картинки галереи"));
    const images = [];
    for (const p of items) images.push({ image: p.file ? await ctx.uploadAsset(p.file) : p.image, caption: p.caption.trim() });
    return { images };
  } };
}

export function videoEditor(slide, ctx) {
  const url = el("input", { type: "url", value: slide.url, placeholder: "https://youtu.be/… или ссылка на Яндекс Диск", "aria-label": "Ссылка на видео" });
  const hint = el("div", { class: "muted tiny" }, "YouTube, Rutube, VK Видео, Vimeo смотрятся прямо здесь; другие ссылки откроются в новой вкладке");
  const poster = el("input", { type: "file", accept: ".png,.jpg,.jpeg,.svg", "aria-label": "Обложка" });
  const current = slide.poster ? el("img", { src: ctx.assetUrl(slide.poster), alt: "", class: "thumb" }) : null;
  const dropPoster = el("input", { type: "checkbox" });
  return {
    node: el("div", {}, label("Ссылка на видео"), url, hint, label("Обложка"), current, poster,
      slide.poster ? el("label", { class: "radio" }, dropPoster, "Убрать обложку — шаблон нарисует заглушку") : null),
    read: async () => {
      fail(linkError(url.value));
      const out = { url: url.value.trim() };
      if (dropPoster.checked) out.poster = "";
      else if (poster.files[0]) out.poster = await ctx.uploadAsset(poster.files[0]);
      return out;
    },
  };
}
