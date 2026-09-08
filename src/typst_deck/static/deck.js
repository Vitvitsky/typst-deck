import { api, upload, waitJob, sleep, el } from "./api.js";

const deckId = location.pathname.split("/").filter(Boolean).pop();
const $ = (id) => document.getElementById(id);
const TEXT_FIELDS = new Set(["title", "subtitle", "caption", "contact", "unit", "notes"]);
const LINE_FIELDS = new Set(["bullets", "labels"]);
const JSON_FIELDS = new Set(["data", "series"]);
const NEW_SLIDE = {
  title: { type: "title", title: "Заголовок", subtitle: "" },
  section: { type: "section", title: "Раздел" },
  image: { type: "image", title: "Заголовок", bullets: ["Тезис"] },
  "bar-chart": { type: "bar-chart", title: "Диаграмма", data: [{ label: "A", value: 1 }, { label: "B", value: 2 }] },
  chart: { type: "chart", title: "График", labels: ["1", "2", "3"], series: [{ name: "Ряд", values: [1, 2, 3] }] },
  final: { type: "final" },
};

const state = { info: null, positions: [], page: { w: 453.54, h: 255.12 }, polling: false };

// --- загрузка и отрисовка
async function refresh() {
  const info = await api(`api/decks/${deckId}`);
  state.info = info;
  $("title").textContent = info.deck.title;
  document.title = `${info.deck.title} — typst-deck`;
  $("pdf").href = `api/decks/${deckId}/deck.pdf`;
  showBanner(info);
  if (info.status === "generating") {
    if (!state.polling) pollUntilReady();
    if (!info.has_build) return;
  }
  if (!info.has_build) { $("pages").replaceChildren(); return; }
  state.positions = await api(`api/decks/${deckId}/positions`);
  await readPageSize();
  renderPages();
}

async function pollUntilReady() {
  state.polling = true;
  try {
    for (;;) {
      await sleep(1000);
      const info = await api(`api/decks/${deckId}`);
      if (info.status !== "generating") break;
    }
  } finally {
    state.polling = false;
  }
  await Promise.all([refresh(), loadChat()]);
}

function showBanner(info) {
  const b = $("banner");
  b.className = "banner";
  if (info.status === "generating") {
    b.classList.add("busy");
    b.replaceChildren(el("span", { class: "spinner" }), "Модель работает над слайдами…");
  } else if (info.status === "failed" && info.last_error) {
    b.replaceChildren(`Последняя генерация не удалась: ${info.last_error}`);
  } else if (info.warnings && info.warnings.length) {
    b.replaceChildren(info.warnings.join("; "));
  } else if (!info.slide_count) {
    b.replaceChildren("Слайдов пока нет. Опишите презентацию в чате или добавьте слайд кнопкой слева.");
  } else {
    b.classList.add("hidden");
  }
}

async function readPageSize() {
  try {
    const r = await fetch(`api/decks/${deckId}/slides/1.svg?v=${state.info.version}`);
    const m = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(await r.text());
    if (m) state.page = { w: +m[1], h: +m[2] };
  } catch { /* остаётся размер по умолчанию */ }
}

function renderPages() {
  const { deck, version } = state.info;
  const wraps = deck.slides.map((slide, i) => {
    const n = i + 1;
    const overlay = el("div", { class: "overlay", onclick: (e) => { if (e.target === overlay) openSlidePanel(slide, page); } });
    for (const p of state.positions.filter((p) => p.page === n)) {
      const z = el("div", {
        class: "zone", title: `Изменить: ${p.field}`,
        style: `left:${(p.x / state.page.w) * 100}%;top:${(p.y / state.page.h) * 100}%;width:${(p.w / state.page.w) * 100}%;height:${(p.h / state.page.h) * 100}%`,
        onclick: () => openFieldEditor(slide, p.field, z, page),
      });
      overlay.append(z);
    }
    const page = el("div", { class: "page" },
      el("img", { src: `api/decks/${deckId}/slides/${n}.svg?v=${version}`, alt: `Слайд ${n}` }), overlay);
    const bar = el("div", { class: "pagebar" },
      `${n}. ${slide.type}`, el("span", { class: "sp" }),
      el("button", { class: "small", title: "Выше", onclick: () => move(slide.id, i - 1), disabled: i === 0 ? "" : null }, "↑"),
      el("button", { class: "small", title: "Ниже", onclick: () => move(slide.id, i + 1), disabled: i === deck.slides.length - 1 ? "" : null }, "↓"),
      el("button", { class: "small", title: "Удалить слайд", onclick: () => removeSlide(slide) }, "✕"));
    return el("div", { class: "pagewrap", id: `slide-${slide.id}` }, bar, page);
  });
  $("pages").replaceChildren(...wraps);
}

// --- правки
async function applyResult(promise) {
  try {
    state.info = await promise;
    state.positions = await api(`api/decks/${deckId}/positions`);
    showBanner(state.info);
    renderPages();
  } catch (e) {
    alert(e.message);
  }
}

const patchSlide = (id, patch) => api(`api/decks/${deckId}/slides/${id}`, { method: "PATCH", json: { patch } });
const move = (id, to) => applyResult(api(`api/decks/${deckId}/slides/${id}/move`, { json: { to_index: to } }));

async function removeSlide(slide) {
  if (!confirm(`Удалить слайд «${slide.title || slide.type}»?`)) return;
  await applyResult(api(`api/decks/${deckId}/slides/${slide.id}`, { method: "DELETE" }));
}

function closeEditors() {
  document.querySelectorAll(".editor").forEach((e) => e.remove());
  document.querySelectorAll(".zone.active").forEach((z) => z.classList.remove("active"));
}

function placeEditor(editor, page, anchor) {
  closeEditors();
  page.append(editor);
  const top = anchor ? anchor.offsetTop + anchor.offsetHeight + 4 : 12;
  const left = anchor ? Math.min(anchor.offsetLeft, page.clientWidth - editor.offsetWidth - 8) : 12;
  editor.style.top = `${top}px`;
  editor.style.left = `${Math.max(8, left)}px`;
  if (anchor) anchor.classList.add("active");
  const first = editor.querySelector("input, textarea, select");
  if (first) first.focus();
}

function fieldControl(slide, field) {
  const v = slide[field];
  if (LINE_FIELDS.has(field)) return el("textarea", { name: field, placeholder: "По одному пункту на строку" }, (v || []).join("\n"));
  if (JSON_FIELDS.has(field)) return el("textarea", { name: field }, JSON.stringify(v, null, 1));
  if (field === "image_size") {
    const s = el("select", { name: field }, ...["small", "medium", "large"].map((o) => el("option", { value: o, selected: v === o ? "" : null }, o)));
    return s;
  }
  if (field === "notes") return el("textarea", { name: field }, v || "");
  return el("input", { type: "text", name: field, value: v ?? "" });
}

function readControl(field, control) {
  const raw = control.value;
  if (LINE_FIELDS.has(field)) return raw.split("\n").map((s) => s.trim()).filter(Boolean);
  if (JSON_FIELDS.has(field)) return JSON.parse(raw);
  return raw;
}

function imageControls(slide, patch) {
  const box = el("div", {});
  box.append(el("label", {}, "Размер картинки"), fieldControl(slide, "image_size"));
  const file = el("input", { type: "file", accept: ".png,.jpg,.jpeg,.svg" });
  box.append(el("label", {}, slide.image ? `Картинка: ${slide.image}` : "Картинки нет"), file);
  if (slide.image) box.append(el("div", {}, el("button", { class: "small", type: "button", onclick: () => { patch.image = null; box.querySelector("label:nth-of-type(2)").textContent = "Картинка будет убрана"; } }, "Убрать картинку")));
  box.collect = async () => {
    patch.image_size = box.querySelector("select").value;
    if (file.files[0]) patch.image = (await upload(`api/decks/${deckId}/assets`, file.files[0])).asset_id;
  };
  return box;
}

function openFieldEditor(slide, field, zone, page) {
  const patch = {};
  const form = el("form", { class: "editor" }, el("div", { class: "head" }, `Слайд: ${field}`));
  let control = null, img = null;
  if (field === "image") { img = imageControls(slide, patch); form.append(img); }
  else { control = fieldControl(slide, field); form.append(control); }
  const err = el("div", { class: "error" });
  form.append(err, el("div", { class: "actions" },
    el("button", { type: "button", onclick: closeEditors }, "Отмена"),
    el("button", { class: "primary", type: "submit" }, "Сохранить")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      if (control) patch[field] = readControl(field, control);
      if (img) await img.collect();
      const result = await patchSlide(slide.id, patch);
      closeEditors();
      await applyResult(Promise.resolve(result));
    } catch (ex) { err.textContent = ex.message; }
  });
  form.addEventListener("keydown", (e) => { if (e.key === "Escape") closeEditors(); if (e.key === "Enter" && e.target.tagName === "INPUT") form.requestSubmit(); });
  placeEditor(form, page, zone);
}

function openSlidePanel(slide, page) {
  const patch = {};
  const form = el("form", { class: "editor" }, el("div", { class: "head" }, `Все поля слайда (${slide.type})`));
  const controls = {};
  let img = null;
  for (const [k, v] of Object.entries(slide)) {
    if (k === "id" || k === "type" || k === "image" || k === "image_size") continue;
    form.append(el("label", {}, k));
    controls[k] = fieldControl(slide, k);
    form.append(controls[k]);
  }
  if ("image" in slide) { img = imageControls(slide, patch); form.append(img); }
  const err = el("div", { class: "error" });
  form.append(err, el("div", { class: "actions" },
    el("button", { type: "button", class: "del", onclick: () => removeSlide(slide) }, "Удалить слайд"),
    el("button", { type: "button", onclick: closeEditors }, "Отмена"),
    el("button", { class: "primary", type: "submit" }, "Сохранить")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      for (const [k, c] of Object.entries(controls)) {
        const val = readControl(k, c);
        if (JSON.stringify(val) !== JSON.stringify(slide[k])) patch[k] = val;
      }
      if (img) await img.collect();
      const result = await patchSlide(slide.id, patch);
      closeEditors();
      await applyResult(Promise.resolve(result));
    } catch (ex) { err.textContent = ex.message; }
  });
  form.addEventListener("keydown", (e) => { if (e.key === "Escape") closeEditors(); });
  placeEditor(form, page, null);
}

$("add").addEventListener("click", () => {
  const slide = { ...NEW_SLIDE[$("addtype").value] };
  applyResult(api(`api/decks/${deckId}/slides`, { json: { slide, after: null } })).then(() => {
    const last = document.querySelector(".pagewrap:last-child");
    if (last) last.scrollIntoView({ behavior: "smooth" });
  });
});

// --- версии
$("history").addEventListener("click", async () => {
  const box = $("versions");
  if (!box.classList.contains("hidden")) { box.classList.add("hidden"); return; }
  const versions = await api(`api/decks/${deckId}/versions`);
  box.replaceChildren(...versions.reverse().map((v) => el("div", {},
    el("span", {}, `v${v.version} · ${v.slide_count} сл. · ${new Date(v.updated_at).toLocaleTimeString()}`,
      v.version === state.info.version ? el("span", { class: "muted" }, " (текущая)") : null),
    v.version === state.info.version ? null :
      el("button", { class: "small", onclick: async () => { await applyResult(api(`api/decks/${deckId}/revert`, { json: { version: v.version } })); box.classList.add("hidden"); } }, "Вернуть"))));
  box.classList.remove("hidden");
});

// --- чат
async function loadChat() {
  const chat = await api(`api/decks/${deckId}/chat`);
  const box = $("messages");
  box.replaceChildren(...chat.map((m) => el("div", { class: `msg ${m.role}` }, m.content,
    m.ops && m.ops.length ? el("span", { class: "ops" }, `правки: ${m.ops.join(", ")}`) : null)));
  box.scrollTop = box.scrollHeight;
}

async function send() {
  const text = $("input").value.trim();
  if (!text) return;
  $("send").disabled = true;
  try {
    const { job_id } = await api(`api/decks/${deckId}/messages`, { json: { text } });
    $("input").value = "";
    $("messages").append(el("div", { class: "msg user" }, text));
    showBanner({ status: "generating" });
    await waitJob(job_id);
    await Promise.all([loadChat(), refresh()]);
  } catch (e) {
    $("messages").append(el("div", { class: "msg error" }, e.message));
  } finally {
    $("send").disabled = false;
    $("input").focus();
  }
}
$("send").addEventListener("click", send);
$("input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });

refresh().then(loadChat).catch((e) => { $("banner").className = "banner"; $("banner").textContent = e.message; });
