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
