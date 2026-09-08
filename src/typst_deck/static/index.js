import { api, upload, waitJob, el } from "./api.js";

const $ = (id) => document.getElementById(id);
const picked = [];

// --- создание
$("files").addEventListener("change", (e) => {
  for (const f of e.target.files) picked.push(f);
  e.target.value = "";
  renderFiles();
});

function renderFiles() {
  $("filelist").replaceChildren(...picked.map((f, i) => el("li", {},
    el("span", {}, f.name, " ", el("span", { class: "muted" }, `${Math.round(f.size / 1024)} КБ`)),
    el("button", { class: "small", onclick: () => { picked.splice(i, 1); renderFiles(); } }, "убрать"))));
}

$("create").addEventListener("click", async () => {
  const btn = $("create");
  $("error").textContent = "";
  if (!$("brief").value.trim() && !picked.length) {
    $("error").textContent = "Опишите презентацию или приложите хотя бы один файл.";
    return;
  }
  btn.disabled = true;
  try {
    const ids = [];
    for (const f of picked) {
      $("status").textContent = `Загружаю ${f.name}…`;
      ids.push((await upload("api/uploads", f)).upload_id);
    }
    $("status").textContent = "Открываю презентацию…";
    const { deck_id } = await api("api/decks", { json: { brief: $("brief").value, upload_ids: ids } });
    // генерация идёт в фоне; страница колоды покажет прогресс и слайды по готовности
    location.href = `d/${deck_id}`;
  } catch (e) {
    $("error").textContent = e.message;
    $("status").textContent = "";
    btn.disabled = false;
  }
});

// --- каталог
const fmt = (iso) => new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
const STATUS = { generating: "генерируется…", failed: "ошибка генерации", ready: "" };

async function loadCatalog() {
  let decks;
  try { decks = await api("api/decks"); } catch (e) { $("decks").replaceChildren(el("div", { class: "error" }, e.message)); return; }
  $("count").textContent = decks.length ? `(${decks.length})` : "";
  if (!decks.length) {
    $("decks").replaceChildren(el("p", { class: "muted empty" }, "Пока ни одной. Первая появится здесь после создания."));
    return;
  }
  $("decks").replaceChildren(...decks.map((d) => el("a", { class: "card", href: `d/${d.id}` },
    el("div", { class: "thumb" }, d.has_build
      ? el("img", { src: `api/decks/${d.id}/slides/1.svg?v=${d.version}`, alt: "", loading: "lazy" })
      : el("div", { class: "nothumb muted" }, d.status === "generating" ? el("span", { class: "spinner" }) : null, d.status === "generating" ? "собирается" : "нет слайдов")),
    el("div", { class: "meta" },
      el("div", { class: "name" }, d.title),
      el("div", { class: "muted small" }, `${d.slide_count} сл. · ${fmt(d.updated_at)}`,
        STATUS[d.status] ? el("span", { class: d.status === "failed" ? "error" : "muted" }, ` · ${STATUS[d.status]}`) : null),
      el("div", { class: "actions" },
        el("span", { class: "link" }, "Открыть"),
        d.has_build ? el("a", { href: `api/decks/${d.id}/deck.pdf`, download: "", onclick: (e) => e.stopPropagation() }, "PDF") : null)))));
  if (decks.some((d) => d.status === "generating")) setTimeout(loadCatalog, 3000);
}
loadCatalog();
