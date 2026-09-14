// Обёртка над fetch с относительными путями (работает под /deck/ за Nginx), ошибки API → Error, мелкие утилиты.
export async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) {
    init.method = init.method || "POST";
    init.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
    init.body = JSON.stringify(opts.json);
    delete init.json;
  }
  const r = await fetch(path, init);
  if (r.status === 204) return null;
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    const e = new Error(data && data.error ? data.error.message : `HTTP ${r.status}`);
    e.status = r.status;
    e.code = data && data.error ? data.error.code : "http";
    throw e;
  }
  return data;
}

export async function upload(path, file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return api(path, { method: "POST", body: fd });
}

export const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

export async function waitJob(jobId, onTick) {
  for (;;) {
    const job = await api(`api/jobs/${jobId}`);
    if (onTick) onTick(job);
    if (job.status === "done" || job.status === "failed") return job;
    await sleep(1000);
  }
}

export function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v === true) n.setAttribute(k, "");
    else n.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    n.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return n;
}

// --- тосты: одно действие, 4 секунды
let toastRoot = null;
export function toast(text, { action, onAction, error } = {}) {
  if (!toastRoot) { toastRoot = el("div", { class: "toasts" }); document.body.append(toastRoot); }
  const t = el("div", { class: `toast${error ? " err" : ""}`, role: "status" }, text,
    action ? el("button", { onclick: () => { onAction && onAction(); t.remove(); } }, action) : null);
  toastRoot.append(t);
  setTimeout(() => t.remove(), error ? 7000 : 4000);
}

// --- встроенное подтверждение: кнопка спрашивает сама себя, без confirm()
export function armConfirm(btn, label, onConfirm) {
  const orig = btn.textContent;
  if (btn.dataset.armed) return;
  btn.dataset.armed = "1";
  btn.textContent = label;
  btn.classList.add("confirm");
  const reset = () => { delete btn.dataset.armed; btn.textContent = orig; btn.classList.remove("confirm"); };
  const timer = setTimeout(reset, 3500);
  btn.addEventListener("click", () => { clearTimeout(timer); reset(); onConfirm(); }, { once: true });
}

export const TYPE_RU = {
  title: "Заглавный", agenda: "Повестка", section: "Раздел", text: "Тезисы", image: "Текст и картинка",
  columns: "Блоки текста", comparison: "Сравнение", quote: "Цитата", chart: "График", "dual-chart": "Два графика",
  metrics: "Метрики", table: "Таблица", gallery: "Галерея", video: "Видео", final: "Финальный",
};
// Те же слова, что в slots.FIELD_RU (src/typst_deck/slots.py) — человек видит одно
// и то же название везде: на кнопке зоны, в подписи поля, в тексте правки.
export const FIELD_RU = {
  title: "Заголовок", subtitle: "Подзаголовок", bullets: "Тезисы", caption: "Подпись к картинке", contact: "Контакты",
  author: "Автор", department: "Подразделение",
  unit: "Единица измерения", notes: "Заметки докладчика", data: "Данные диаграммы", labels: "Подписи по оси",
  series: "Ряды данных", image: "Картинка", image_size: "Размер картинки",
  items: "Пункты", blocks: "Блоки текста", left: "Левая колонка", right: "Правая колонка",
  text: "Текст", header: "Шапка таблицы", rows: "Строки таблицы", images: "Картинки",
  video: "Видео", url: "Ссылка", poster: "Обложка", kind: "Вид графика",
};
export const SIZE_RU = { small: "маленькая", medium: "средняя", large: "крупная" };
export const fileKind = (name) => /\.(png|jpe?g|svg)$/i.test(name) ? "image" : /\.mp4$/i.test(name) ? "video" : /\.(xlsx|csv)$/i.test(name) ? "table" : /\.(txt|md|docx)$/i.test(name) ? "text" : "bad";
export const KIND_ICON = { image: "▨", video: "▶", table: "▦", text: "Т", bad: "?" };
export const fmtSize = (b) => b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} КБ` : `${(b / 1024 / 1024).toFixed(1)} МБ`;
export const fmtTokens = (n) => Number(n || 0).toLocaleString("ru-RU");
export const fmtDate = (iso) => new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
export const fmtElapsed = (fromIso) => { const s = Math.max(0, Math.floor((Date.now() - new Date(fromIso)) / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
export const errorText = (e) => {
  const m = String(e && e.message || e);
  if (/max_tokens|лимит/i.test(m)) return "Ответ модели обрезан по лимиту токенов. Повторите запрос или сократите материалы.";
  if (/LLM недоступна|LLM вернула|llm_unavailable/i.test(m)) return "Модель недоступна. Повторите позже или сообщите администратору.";
  if (/render|шаблон|компиляц/i.test(m)) return "Слайды не собрались в шаблоне: " + m.replace(/^[^:]*:\s*/, "").slice(0, 300);
  return m;
};
