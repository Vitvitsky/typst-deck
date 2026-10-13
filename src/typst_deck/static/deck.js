import { api, upload, waitJob, sleep, el, toast, armConfirm, TYPE_RU, FIELD_RU, SIZE_RU, KIND_RU, fileKind, errorText, fmtDate, fmtElapsed, fmtTokens } from "./api.js";
import { mountShell } from "./shell.js";
import { PANEL, compositeEditor, changed, embedUrl, linkError } from "./editors.js";

const deckId = location.pathname.split("/").filter(Boolean).pop();
mountShell({ active: "decks", deckId, defaultCollapsed: true });
const $ = (id) => document.getElementById(id);
const NEW_SLIDE = {
  title: { type: "title", title: "Заголовок", subtitle: "" },
  agenda: { type: "agenda", title: "Повестка", items: ["Первый раздел", "Второй раздел", "Третий раздел"] },
  section: { type: "section", title: "Раздел" },
  text: { type: "text", title: "Заголовок", bullets: ["Первый тезис"] },
  image: { type: "image", title: "Заголовок", bullets: ["Первый тезис"], image: null },
  columns: { type: "columns", title: "Блоки", blocks: [{ heading: "Первый", text: "Текст" }, { heading: "Второй", text: "Текст" }] },
  comparison: { type: "comparison", title: "Было и стало", left: { heading: "Было", bullets: ["Пункт"] }, right: { heading: "Стало", bullets: ["Пункт"] } },
  quote: { type: "quote", text: "Одна мысль", author: "" },
  chart: { type: "chart", title: "График", kind: "line", labels: ["Q1", "Q2", "Q3"], series: [{ name: "Ряд", values: [1, 2, 3] }] },
  "dual-chart": { type: "dual-chart", title: "Два графика", left: { caption: "Слева", kind: "line", labels: ["Q1", "Q2"], series: [{ name: "Ряд", values: [1, 2] }] }, right: { caption: "Справа", kind: "bar", labels: ["A", "B"], series: [{ name: "Ряд", values: [2, 1] }] } },
  metrics: { type: "metrics", title: "Числа", items: [{ value: "12,5 млн", label: "выручка", delta: "+12 %" }, { value: "17", label: "проектов", delta: "" }] },
  table: { type: "table", title: "Таблица", header: ["Регион", "Выручка"], rows: [["Центр", "42"], ["Север", "17"]] },
  gallery: { type: "gallery", title: "Галерея", images: [{ image: null, caption: "" }, { image: null, caption: "" }] },
  video: { type: "video", title: "Видео", url: "", caption: "" },  // ссылку спрашивает askVideoLink
  final: { type: "final" },
};
// image и gallery не проходят валидацию без картинки (модель требует её), поэтому
// «Добавить слайд» для них сперва открывает выбор файла и грузит его в assets —
// иначе POST .../slides ответил бы 422; для остальных типов заготовка идёт как есть
const NEEDS_PICTURE = { image: { multiple: false }, gallery: { multiple: true } };
const CHIPS = ["Сократи текст на всех слайдах", "Добавь слайд с выводами в конце", "Разбей на разделы", "Сделай заголовки короче"];
const PHASES = [["reading", "Читаю материалы"], ["model", "Собираю структуру"], ["render", "Верстаю слайды"]];

const state = { info: null, positions: [], page: { w: 453.54, h: 255.12 }, selected: null, changed: new Set(), tab: "chat", polling: false, timer: null, lastUser: "", templates: [] };

// ============ загрузка
async function refresh() {
  const info = await api(`api/decks/${deckId}`);
  state.info = info;
  renderTopbar();
  if (info.status === "generating") {
    renderGenerating();
    if (!state.polling) pollUntilReady();
    return;
  }
  stopTimer();
  state.page = info.page || state.page;
  if (info.has_build) state.positions = await api(`api/decks/${deckId}/positions`);
  if (state.selected && !info.deck.slides.some((s) => s.id === state.selected)) state.selected = null;
  renderStage();
  renderRail();
  if (state.tab === "slide") renderProps();
  setLock(false);
}

async function pollUntilReady() {
  state.polling = true;
  try {
    for (;;) {
      await sleep(1000);
      const info = await api(`api/decks/${deckId}`);
      state.info = info;
      if (info.status !== "generating") break;
      renderProgressOnly();
    }
  } finally { state.polling = false; }
  await Promise.all([refresh(), loadChat()]);
}

// ============ шапка
async function ensureTemplates() {
  if (state.templates.length || state.templatesLoading) return;
  state.templatesLoading = true;
  // при ошибке список остаётся пустым, флаг снимается — следующий refresh попробует снова
  try { state.templates = await api("api/templates"); } catch { state.templates = []; }
  finally { state.templatesLoading = false; }
  renderTplSelect();
}

function currentTemplateId() {
  return state.info && state.info.deck ? state.info.deck.template : "";
}

function renderTplSelect() {
  const sel = $("tplname");
  const cur = currentTemplateId();
  let known = state.templates.find((t) => t.id === cur);
  // Шаблона колоды может не быть в списке: закрытый корень не примонтирован или
  // GET /api/templates упал. Без запасного пункта select оказался бы пустым и
  // пользователь перестал бы видеть даже текущее оформление — берём его из payload.
  if (!known && cur) known = { id: cur, name: (state.info && state.info.template && state.info.template.name) || cur };
  const opts = known && !state.templates.some((t) => t.id === cur) ? [...state.templates, known] : state.templates;
  sel.replaceChildren(...opts.map((t) => el("option", { value: t.id }, t.name)));
  sel.value = cur;
  sel.title = cur && known ? `Шаблон оформления: ${known.name}` : "Шаблон оформления";
  sel.disabled = state.info ? state.info.status === "generating" : false;
}

async function changeTemplate(tid) {
  const prev = currentTemplateId();
  if (!tid || tid === prev) { renderTplSelect(); return; }
  const sel = $("tplname");
  sel.disabled = true;
  try {
    await applyResult(api(`api/decks/${deckId}/template`, { json: { template: tid } }));
    toast(`Шаблон сменён на «${(state.templates.find((t) => t.id === tid) || {}).name || tid}»`);
  } catch (e) {
    toast(e.message, { error: true });
    renderTplSelect();
  }
  sel.disabled = false;
}

function renderTopbar() {
  const { deck } = state.info;
  const h = $("title");
  if (!h.querySelector("input")) h.textContent = deck.title;
  document.title = `${deck.title} — typst-deck`;
  ensureTemplates();  // повторная попытка, если первая загрузка списка не удалась
  renderTplSelect();
  const pdf = $("pdf");
  pdf.href = `api/decks/${deckId}/deck.pdf`;
  pdf.classList.toggle("hidden", !state.info.has_build);
  // PPTX собирается из модели на лету и сборки не ждёт; есть только у шаблона с PowerPoint-мастером
  const pptx = $("pptx");
  pptx.href = `api/decks/${deckId}/deck.pptx`;
  pptx.classList.toggle("hidden", !(state.info.template.pptx && state.info.slide_count > 0));
}

$("tplname").addEventListener("change", (e) => changeTemplate(e.target.value));
ensureTemplates();

$("title").addEventListener("click", () => {
  const h = $("title");
  if (h.querySelector("input")) return;
  const input = el("input", { type: "text", value: state.info.deck.title, "aria-label": "Название презентации" });
  h.replaceChildren(input);
  input.focus(); input.select();
  const done = async (save) => {
    const v = input.value.trim();
    if (save && v && v !== state.info.deck.title) {
      try { await applyResult(api(`api/decks/${deckId}`, { method: "PATCH", json: { title: v } })); toast("Название сохранено"); }
      catch (e) { toast(e.message, { error: true }); }
    }
    h.textContent = state.info.deck.title;
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); });
  input.addEventListener("blur", () => done(true));
});

$("copylink").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(location.href); toast("Ссылка скопирована"); }
  catch { toast(location.href); }
});

$("history").addEventListener("click", async () => {
  const box = $("versions");
  if (!box.classList.contains("hidden")) { box.classList.add("hidden"); return; }
  const versions = (await api(`api/decks/${deckId}/versions`)).reverse();
  box.replaceChildren(...versions.map((v) => el("div", { class: "v" },
    el("span", { class: "num" }, `Версия ${v.version}`),
    el("span", { class: "muted" }, `${v.slide_count} сл. · ${fmtDate(v.updated_at)}`),
    el("span", { class: "sp" }),
    v.version === state.info.version ? el("span", { class: "muted tiny" }, "текущая")
      : el("button", { class: "sm", onclick: async () => {
          try { await applyResult(api(`api/decks/${deckId}/revert`, { json: { version: v.version } })); box.classList.add("hidden"); toast(`Возвращена версия ${v.version}`); }
          catch (e) { toast(e.message, { error: true }); }
        } }, "Вернуть"))));
  box.classList.remove("hidden");
});

// версия слайда для URL: хеш его содержимого, чтобы правка одного слайда
// не сбрасывала кеш остальных; на сборках до pages.json — версия колоды
function slideVer(i) {
  const pages = state.info && state.info.pages;
  return (pages && pages[i]) || (state.info && state.info.version);
}

// ============ сцена: сборка / пусто / слайды
function renderGenerating() {
  const inner = $("stage-inner");
  inner.replaceChildren(progressCard(), el("div", { class: "skeleton" }), el("div", { class: "skeleton" }), el("div", { class: "skeleton" }));
  $("rail").replaceChildren(el("div", { class: "muted tiny", style: "padding:6px" }, "Слайды появятся после сборки"));
  setLock(true, "Дождитесь окончания сборки, потом можно продолжить в чате.");
  startTimer();
}

function progressCard() {
  const job = state.info.job || {};
  const idx = Math.max(0, PHASES.findIndex(([k]) => k === job.phase));
  return el("div", { class: "progress", id: "progress" },
    el("div", { class: "steps" }, ...PHASES.map(([k, label], i) => el("div", { class: `step ${i < idx ? "done" : i === idx ? "now" : ""}` },
      i < idx ? el("span", { class: "mark" }, "✓") : i === idx ? el("span", { class: "spinner" }) : el("span", { class: "mark" }), label))),
    el("span", { class: "time", id: "elapsed" }, job.created_at ? fmtElapsed(job.created_at) : ""));
}

function renderProgressOnly() {
  const old = $("progress");
  if (old) old.replaceWith(progressCard());
}

function startTimer() {
  stopTimer();
  state.timer = setInterval(() => { const e = $("elapsed"); const job = state.info && state.info.job; if (e && job) e.textContent = fmtElapsed(job.created_at); }, 1000);
}
function stopTimer() { if (state.timer) clearInterval(state.timer); state.timer = null; }

function renderStage() {
  const { deck, warnings, status, last_error } = state.info;
  const inner = $("stage-inner");
  const parts = [];
  if (status === "failed" && last_error && !deck.slides.length) {
    parts.push(el("div", { class: "notice err inline" }, `Не удалось собрать: ${errorText(last_error)}`));
  }
  if (warnings && warnings.length) parts.push(el("div", { class: "notice warn inline" }, warnings.join("; ")));
  if (!deck.slides.length) {
    parts.push(el("div", { class: "empty-stage" },
      el("p", {}, "Слайдов пока нет."),
      el("div", { class: "row" },
        el("button", { class: "primary", onclick: () => { switchTab("chat"); $("input").focus(); } }, "Описать в чате"),
        el("button", { onclick: () => $("add").click() }, "Добавить слайд вручную"))));
    inner.replaceChildren(...parts);
    return;
  }
  deck.slides.forEach((slide, i) => {
    const n = i + 1;
    const overlay = el("div", { class: "overlay" });
    overlay.addEventListener("click", (e) => { if (e.target === overlay) { select(slide.id); switchTab("slide"); } });
    for (const p of state.positions.filter((p) => p.page === n)) {
      overlay.append(el("button", {
        class: "zone", type: "button", "aria-label": `Изменить: ${FIELD_RU[p.field] || p.field}, слайд ${n}`,
        style: `left:${(p.x / state.page.w) * 100}%;top:${(p.y / state.page.h) * 100}%;width:${(p.w / state.page.w) * 100}%;height:${(p.h / state.page.h) * 100}%`,
        onclick: (e) => { e.stopPropagation(); select(slide.id); openFieldEditor(slide, n, p.field, e.currentTarget, page); },
      }));
    }
    const play = slide.type === "video" && slide.url
      ? el("button", { type: "button", class: "play", onclick: (e) => { e.stopPropagation(); playVideo(slide); } }, "▶ Смотреть")
      : null;
    const page = el("div", { class: "page" }, el("img", { src: `api/decks/${deckId}/slides/${n}.svg?v=${slideVer(i)}`, alt: `Слайд ${n}` }), overlay, play);
    parts.push(el("div", { class: `pagewrap${state.selected === slide.id ? " selected" : ""}`, id: `slide-${slide.id}` },
      el("div", { class: "pagebar" }, el("span", { class: "n num" }, n), el("span", {}, TYPE_RU[slide.type]),
        el("span", { class: "hint" }, "Нажмите на текст, чтобы изменить")),
      page));
  });
  inner.replaceChildren(...parts);
}

// YouTube, Rutube, VK Видео, Vimeo играют здесь же; остальное — в новой вкладке (ADR 0022)
function playVideo(slide) {
  const src = embedUrl(slide.url);
  if (!src) { window.open(slide.url, "_blank", "noopener"); return; }
  const dlg = $("player"), frame = $("player-frame");
  frame.src = src;
  dlg.showModal();
  dlg.addEventListener("close", () => { frame.src = "about:blank"; }, { once: true });
}

// ============ лента миниатюр
function renderRail() {
  const { deck } = state.info;
  const rail = $("rail");
  if (!deck.slides.length) { rail.replaceChildren(el("div", { class: "muted tiny", style: "padding:6px" }, "Слайдов нет")); return; }
  rail.replaceChildren(...deck.slides.map((slide, i) => {
    const item = el("div", { class: `thumb-item${state.selected === slide.id ? " selected" : ""}`, role: "button", tabindex: 0,
      "aria-label": `Слайд ${i + 1}: ${slide.title || TYPE_RU[slide.type]}` },
      state.info.has_build ? el("img", { src: `api/decks/${deckId}/slides/${i + 1}.svg?v=${slideVer(i)}`, alt: "" }) : el("div", { class: "skeleton" }),
      el("div", { class: "cap" }, el("span", { class: "n num" }, i + 1), el("span", { class: "t" }, slide.title || TYPE_RU[slide.type])),
      state.changed.has(slide.id) ? el("span", { class: "dot", title: "Изменён моделью" }) : null,
      el("div", { class: "ops" },
        el("button", { title: "Выше", disabled: i === 0, onclick: (e) => { e.stopPropagation(); move(slide.id, i - 1); } }, "↑"),
        el("button", { title: "Ниже", disabled: i === deck.slides.length - 1, onclick: (e) => { e.stopPropagation(); move(slide.id, i + 1); } }, "↓"),
        el("button", { title: "Удалить", class: "danger", onclick: (e) => { e.stopPropagation(); removeSlide(slide); } }, "✕")));
    const go = () => { select(slide.id); const t = $(`slide-${slide.id}`); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); };
    item.addEventListener("click", go);
    item.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    return item;
  }));
}

function select(id) {
  state.selected = id;
  document.querySelectorAll(".pagewrap").forEach((p) => p.classList.toggle("selected", p.id === `slide-${id}`));
  document.querySelectorAll(".thumb-item").forEach((t, i) => t.classList.toggle("selected", state.info.deck.slides[i] && state.info.deck.slides[i].id === id));
  if (state.tab === "slide") renderProps();
}

// ============ правки
async function applyResult(promise) {
  // пока правка шла, человек мог перейти на другой слайд и начать печатать: его
  // форму уже нарисовал select() — перерисовка стёрла бы ввод
  const sel = state.selected;
  const info = await promise;
  state.info = info;
  state.page = info.page || state.page;
  if (info.has_build) state.positions = await api(`api/decks/${deckId}/positions`);
  renderTopbar(); renderStage(); renderRail();
  if (state.tab === "slide" && state.selected === sel) renderProps();
  return info;
}
const patchSlide = (id, patch) => api(`api/decks/${deckId}/slides/${id}`, { method: "PATCH", json: { patch } });
async function move(id, to) { try { await applyResult(api(`api/decks/${deckId}/slides/${id}/move`, { json: { to_index: to } })); } catch (e) { toast(e.message, { error: true }); } }
async function removeSlide(slide) {
  const n = state.info.deck.slides.findIndex((s) => s.id === slide.id) + 1;
  const snapshot = state.info.version;
  try {
    await applyResult(api(`api/decks/${deckId}/slides/${slide.id}`, { method: "DELETE" }));
    toast(`Слайд ${n} удалён`, { action: "Вернуть", onAction: () => applyResult(api(`api/decks/${deckId}/revert`, { json: { version: snapshot } })).catch((e) => toast(e.message, { error: true })) });
  } catch (e) { toast(e.message, { error: true }); }
}
$("add").addEventListener("click", async () => {
  const type = $("addtype").value;
  try {
    const slide = type in NEEDS_PICTURE ? await pickPictureSlide(type)
      : type === "video" ? await videoSlide() : JSON.parse(JSON.stringify(NEW_SLIDE[type]));
    if (!slide) return;  // выбор файла или ввод ссылки отменили
    const info = await applyResult(api(`api/decks/${deckId}/slides`, { json: { slide, after: state.selected } }));
    const idx = state.selected ? info.deck.slides.findIndex((s) => s.id === state.selected) + 1 : info.deck.slides.length - 1;
    const added = info.deck.slides[idx];
    if (added) { select(added.id); const t = $(`slide-${added.id}`); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); switchTab("slide"); }
  } catch (e) { toast(e.message, { error: true }); }
});

// видео без ссылки модель не примет (ADR 0022): ссылка спрашивается до создания
// слайда прямо под меню «Добавить», а не заготовкой-пустышкой
function askVideoLink() {
  return new Promise((resolve) => {
    const box = document.querySelector(".rail-add");
    const keep = [...box.childNodes];
    const input = el("input", { type: "url", placeholder: "https://… — YouTube, Rutube, VK Видео, Яндекс Диск…", "aria-label": "Ссылка на видео" });
    const err = el("div", { class: "error small" });
    const done = (v) => { box.replaceChildren(...keep); resolve(v); };
    const ok = () => { const e = linkError(input.value); if (e) { err.textContent = e; input.focus(); return; } done(input.value.trim()); };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); ok(); }
      if (e.key === "Escape") done(null);
    });
    box.replaceChildren(input, err, el("div", { class: "row" },
      el("button", { type: "button", class: "sm primary", onclick: ok }, "Добавить видео"),
      el("button", { type: "button", class: "sm", onclick: () => done(null) }, "Отмена")));
    input.focus();
  });
}

async function videoSlide() {
  const url = await askVideoLink();
  return url ? { ...NEW_SLIDE.video, url } : null;
}

// GallerySlide.images ограничен 2–4 картинками (model.py) — проверяем ДО
// загрузки: иначе пять файлов уйдут на сервер через /assets, а слайд всё равно
// отклонится, оставив пять осиротевших ассетов без слайда
function pickError(files, type) {
  if (type !== "gallery") return null;
  if (files.length < 2) return "Для галереи нужно минимум две картинки";
  if (files.length > 4) return "Для галереи можно выбрать не больше четырёх картинок";
  return null;
}

// картинка(и) для image/gallery: файловый диалог → загрузка в assets → заготовка
// слайда с уже полученными asset_id; null — пользователь ничего не выбрал (отмена
// диалога или неподходящее число файлов). Input временно вставляется в DOM
// скрытым — детач в некоторых браузерах ненадёжно доставляет события input;
// убирается в cleanup независимо от исхода.
function pickPictureSlide(type) {
  return new Promise((resolve, reject) => {
    const input = el("input", { type: "file", accept: ".png,.jpg,.jpeg,.svg", multiple: NEEDS_PICTURE[type].multiple, hidden: true });
    document.body.append(input);
    const cleanup = () => { input.removeEventListener("change", onChange); input.removeEventListener("cancel", onCancel); input.remove(); };
    // «Отмена» в диалоге выбора файла НЕ порождает change (это отдельное
    // событие cancel) — без этого обработчика промис никогда бы не разрешился
    const onCancel = () => { cleanup(); resolve(null); };
    const onChange = async () => {
      cleanup();
      const files = [...input.files];
      if (!files.length) { resolve(null); return; }
      const err = pickError(files, type);
      if (err) { toast(err, { error: true }); resolve(null); return; }
      try {
        const ids = [];
        for (const f of files) ids.push((await upload(`api/decks/${deckId}/assets`, f)).asset_id);
        const slide = JSON.parse(JSON.stringify(NEW_SLIDE[type]));
        if (type === "image") slide.image = ids[0];
        else slide.images = ids.map((id) => ({ image: id, caption: "" }));
        resolve(slide);
      } catch (e) { reject(e); }
    };
    input.addEventListener("change", onChange);
    input.addEventListener("cancel", onCancel);
    input.click();
  });
}

// --- редактор поля на слайде
function closeEditors() {
  document.querySelectorAll(".editor").forEach((e) => e.remove());
  document.querySelectorAll(".zone.active").forEach((z) => z.classList.remove("active"));
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeEditors(); });

// редакторы составных полей (static/editors.js): загрузка картинок и адреса превью
const editorCtx = {
  uploadAsset: async (file) => (await upload(`api/decks/${deckId}/assets`, file)).asset_id,
  assetUrl: (id) => `api/decks/${deckId}/assets/${encodeURIComponent(id)}`,
};

function openFieldEditor(slide, n, field, zone, page) {
  // составные поля и поля, связанные с ними (подписи графика сверяются с рядами), — во вкладке «Слайд»
  if ((PANEL[slide.type] || []).includes(field)) { switchTab("slide", field); return; }
  closeEditors();
  const patch = {};
  const form = el("form", { class: "editor" }, el("div", { class: "head" }, el("span", {}, `${FIELD_RU[field] || field} · слайд ${n}`), el("span", { class: "tiny" }, "Enter — сохранить, Esc — отмена")));
  let control = null, img = null;
  if (field === "image") { img = imageControls(slide, patch); form.append(img); }
  else { control = fieldControl(slide, field); form.append(control); }
  const err = el("div", { class: "error small" });
  form.append(err, el("div", { class: "actions" }, el("button", { type: "button", onclick: closeEditors }, "Отмена"), el("button", { class: "primary", type: "submit" }, "Сохранить")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      if (control) patch[field] = readControl(field, control);
      if (img) await img.collect();
      const result = await patchSlide(slide.id, patch);
      closeEditors();
      await applyResult(Promise.resolve(result));
      toast("Сохранено");
    } catch (ex) { err.textContent = ex.message; }
  });
  form.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); form.requestSubmit(); } });
  page.append(form);
  const top = zone.offsetTop + zone.offsetHeight + 6;
  const left = Math.max(8, Math.min(zone.offsetLeft, page.clientWidth - form.offsetWidth - 8));
  form.style.top = `${top}px`; form.style.left = `${left}px`;
  zone.classList.add("active");
  const first = form.querySelector("input, textarea, select");
  if (first) first.focus();
}

function fieldControl(slide, field) {
  const v = slide[field];
  if (field === "bullets" || field === "labels") return el("textarea", { name: field, placeholder: "По одному на строку" }, (v || []).join("\n"));
  if (field === "notes") return el("textarea", { name: field }, v || "");
  if (field === "image_size") return el("select", { name: field }, ...Object.entries(SIZE_RU).map(([k, l]) => el("option", { value: k, selected: v === k }, l)));
  // вид графика — выбор, а не поле ввода: модель принимает только bar и line
  if (field === "kind") return el("select", { name: field }, ...Object.entries(KIND_RU).map(([k, l]) => el("option", { value: k, selected: v === k }, l)));
  return el("input", { type: "text", name: field, value: v ?? "" });
}
function readControl(field, control) {
  if (field === "bullets" || field === "labels") return control.value.split("\n").map((s) => s.trim()).filter(Boolean);
  return control.value;
}

// картинка: размер, загрузка, удаление
function imageControls(slide, patch) {
  const box = el("div", { class: "image-box" });
  const size = fieldControl(slide, "image_size");
  const file = el("input", { type: "file", accept: ".png,.jpg,.jpeg,.svg", "aria-label": "Загрузить картинку" });
  const status = el("div", { class: "muted tiny" }, slide.image ? "Картинка на слайде" : "Картинки нет — загрузите файл");
  const remove = slide.image ? el("button", { type: "button", class: "sm danger", onclick: () => { patch.image = null; status.textContent = "Картинка будет убрана после сохранения"; } }, "Убрать картинку") : null;
  box.append(el("label", { class: "f" }, "Размер"), size, el("label", { class: "f" }, slide.image ? "Заменить" : "Загрузить"), file, status);
  if (remove) box.append(remove);
  box.collect = async () => {
    patch.image_size = size.value;
    if (file.files[0]) patch.image = (await upload(`api/decks/${deckId}/assets`, file.files[0])).asset_id;
  };
  return box;
}

// ============ панель свойств выбранного слайда
function switchTab(tab, focus) {
  state.tab = tab;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("tab-chat").classList.toggle("hidden", tab !== "chat");
  $("tab-slide").classList.toggle("hidden", tab !== "slide");
  if (tab === "slide") renderProps(focus);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

function renderProps(focus) {
  const box = $("props");
  const slide = state.info && state.info.deck.slides.find((s) => s.id === state.selected);
  if (!slide) { box.replaceChildren(el("p", { class: "muted small" }, "Выберите слайд: нажмите на него в центре или в ленте слева.")); return; }
  const n = state.info.deck.slides.indexOf(slide) + 1;
  const patch = {};
  const form = el("form", {}, el("h3", {}, `Слайд ${n} · ${TYPE_RU[slide.type]}`), el("div", { class: "sub" }, "Меняются только поля — оформление задаёт шаблон колоды (его можно сменить вверху)."));
  const readers = [];
  // text выше author: у цитаты нет заголовка, и панель читалась «Автор, потом Текст»
  const ORDER = ["title", "subtitle", "text", "author", "department", "items", "bullets", "blocks",
    "left", "right", "header", "rows", "images", "kind", "labels", "series", "unit",
    "caption", "contact", "url", "poster", "video", "notes"];
  const keys = Object.keys(slide).filter((k) => !["id", "type", "image", "image_size"].includes(k))
    .sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
  const group = PANEL[slide.type] || [];
  let groupDone = false;
  for (const k of keys) {
    if (group.includes(k)) {
      if (groupDone) continue;
      groupDone = true;
      const ed = compositeEditor(slide, editorCtx);
      form.append(el("div", { class: "f-group", "data-fields": group.join(" ") }, ed.node));
      readers.push(async () => Object.assign(patch, changed(await ed.read(), slide)));
      continue;
    }
    const c = fieldControl(slide, k);
    form.append(el("label", { class: "f" }, FIELD_RU[k] || k), c);
    readers.push(async () => { const v = readControl(k, c); if (JSON.stringify(v) !== JSON.stringify(slide[k])) patch[k] = v; });
  }
  let img = null;
  if ("image" in slide) { img = imageControls(slide, patch); form.append(el("label", { class: "f" }, FIELD_RU.image), img); }
  const err = el("div", { class: "error small" });
  const del = el("button", { type: "button", class: "danger" }, "Удалить слайд");
  del.addEventListener("click", () => armConfirm(del, "Точно удалить?", () => removeSlide(slide)));
  form.append(err, el("div", { class: "actions" }, del, el("span", { class: "sp" }), el("button", { class: "primary", type: "submit" }, "Сохранить")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const save = form.querySelector("button[type=submit]");
    save.disabled = true;  // двойной щелчок не шлёт правку дважды и не грузит файлы галереи повторно
    try {
      for (const r of readers) await r();
      if (img) await img.collect();
      if (!Object.keys(patch).length) { toast("Изменений нет"); return; }
      await applyResult(patchSlide(slide.id, patch));
      toast("Сохранено");
    } catch (ex) { err.textContent = ex.message; }
    finally { save.disabled = false; }
  });
  box.replaceChildren(form);
  if (focus) {
    const target = box.querySelector(`[data-fields~="${focus}"]`);
    if (target) {
      target.scrollIntoView({ block: "start" });
      target.classList.add("flash");
      const first = target.querySelector("input, textarea, select");
      if (first) first.focus();
    }
  }
}

// ============ чат
function changesText(changes) {
  if (!changes || !changes.length) return null;
  const slides = state.info ? state.info.deck.slides : [];
  const num = (id) => { const i = slides.findIndex((s) => s.id === id); return i >= 0 ? `слайд ${i + 1}` : "слайд"; };
  const parts = changes.map((c) => {
    const name = c.title ? ` «${c.title}»` : "";
    if (c.kind === "rebuilt") return `собрано ${c.count} слайдов`;
    if (c.kind === "updated") return `изменён ${num(c.slide_id)}${name}${c.fields ? ` (${c.fields.map((f) => (FIELD_RU[f] || f).toLowerCase()).join(", ")})` : ""}`;
    if (c.kind === "added") return `добавлен ${num(c.slide_id)}${name}`;
    if (c.kind === "removed") return `удалён слайд${name}`;
    if (c.kind === "moved") return `перемещён ${num(c.slide_id)}${name}`;
    if (c.kind === "template") return `сменён шаблон на «${(state.templates.find((t) => t.id === c.template_id) || {}).name || c.template_id}»`;
    return c.kind;
  });
  return el("span", { class: "changes" }, el("b", {}, "Правки: "), parts.join("; "));
}

// расход модели под ответом: старые записи в chat.jsonl полей не имеют — тогда строки нет
function tokensText(m) {
  if (!m.tokens_in && !m.tokens_out) return null;
  const parts = [`${fmtTokens(m.tokens_in)} → ${fmtTokens(m.tokens_out)} тк`];
  if (m.tokens_cached) parts.push(`кэш ${Math.round((m.tokens_cached / m.tokens_in) * 100)}%`);
  if (m.llm_ms) parts.push(`${(m.llm_ms / 1000).toFixed(1)} с`);
  if (m.iterations > 1) parts.push(`модель ×${m.iterations}`);
  return el("div", { class: "tokens", title: "Расход модели на этот запрос" }, parts.join(" · "));
}

async function loadChat() {
  const chat = await api(`api/decks/${deckId}/chat`);
  const box = $("messages");
  const items = [];
  chat.forEach((m, i) => {
    if (m.role === "assistant" && !m.content && !(m.changes && m.changes.length)) return;
    if (m.role === "error") {
      const prevUser = [...chat.slice(0, i)].reverse().find((x) => x.role === "user");
      items.push(el("div", { class: "msg error" }, el("div", { class: "title" }, "Не удалось выполнить"), errorText(m.content),
        prevUser ? el("div", {}, el("button", { class: "sm", onclick: () => send(prevUser.content) }, "Повторить")) : null));
      return;
    }
    items.push(el("div", { class: `msg ${m.role}` }, m.content || "Готово.",
      m.role === "assistant" ? changesText(m.changes) : null,
      m.role === "assistant" ? tokensText(m) : null));
  });
  if (!items.length) items.push(el("div", { class: "chat-empty" }, "Напишите, что собрать или поправить, или попросите сменить оформление. Модель меняет только содержание — шаблон можно выбрать вверху."));
  const last = chat[chat.length - 1];
  if (last && last.role === "assistant" && last.changes) {
    state.changed = new Set(last.changes.map((c) => c.slide_id).filter(Boolean));
    setTimeout(() => { state.changed.clear(); if (state.info && state.info.status !== "generating") renderRail(); }, 10000);
    if (state.info && state.info.status !== "generating") renderRail();
  }
  if (state.info && state.info.status === "generating") items.push(el("div", { class: "msg pending" }, el("span", { class: "spinner" }), "Модель работает…"));
  box.replaceChildren(...items);
  box.scrollTop = box.scrollHeight;
}

function setLock(locked, text) {
  $("input").disabled = locked; $("send").disabled = locked; $("attach-btn").disabled = locked;
  $("lock").classList.toggle("hidden", !locked);
  $("chips").classList.toggle("hidden", locked);
  if (text) $("lock").textContent = text;
}

async function send(textArg) {
  const text = (textArg ?? $("input").value).trim();
  if (!text) return;
  state.lastUser = text;
  setLock(true, "Модель работает над ответом…");
  try {
    const { job_id } = await api(`api/decks/${deckId}/messages`, { json: { text } });
    $("input").value = ""; $("input").style.height = "";
    $("messages").append(el("div", { class: "msg user" }, text), el("div", { class: "msg pending" }, el("span", { class: "spinner" }), "Модель работает…"));
    $("messages").scrollTop = $("messages").scrollHeight;
    await waitJob(job_id);
    await Promise.all([refresh(), loadChat()]);
  } catch (e) {
    toast(errorText(e), { error: true });
    setLock(false);
  }
}
$("send").addEventListener("click", () => send());
$("input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
$("input").addEventListener("input", (e) => { e.target.style.height = "auto"; e.target.style.height = `${Math.min(160, e.target.scrollHeight)}px`; });
$("chips").replaceChildren(...CHIPS.map((t) => el("button", { class: "chip", type: "button", onclick: () => { $("input").value = t; $("input").focus(); } }, t)));

// вложения: картинка → ассет, документ → материалы
$("attach-btn").addEventListener("click", () => $("attach").click());
$("attach").addEventListener("change", async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  if (fileKind(f.name) === "bad") { toast(`Формат ${f.name} не поддерживается`, { error: true }); return; }
  try {
    const r = await upload(`api/decks/${deckId}/uploads`, f);
    const input = $("input");
    if (r.kind === "image") {
      input.value = `${input.value ? input.value + " " : ""}Поставь картинку ${r.asset_id} на слайд ${state.selected ? state.info.deck.slides.findIndex((s) => s.id === state.selected) + 1 : "…"}`;
      toast(`Картинка «${r.name}» загружена. Скажите модели, куда её поставить`);
    } else {
      toast(`«${r.name}» добавлен к материалам. Модель увидит его при следующем запросе`);
      if (!input.value) input.value = `Учти материал «${r.name}» и `;
    }
    input.focus();
  } catch (err) { toast(err.message, { error: true }); }
});

// ============ старт
refresh().then(loadChat).catch((e) => { $("stage-inner").replaceChildren(el("div", { class: "notice err inline" }, e.status === 404 ? "Презентация не найдена. Возможно, её удалили." : e.message)); });
