import { api, upload, el, fileKind, KIND_ICON, fmtSize } from "./api.js";
import { mountShell } from "./shell.js";

mountShell({ active: "" });
const $ = (id) => document.getElementById(id);
const picked = [];
let template = new URLSearchParams(location.search).get("template") || "default";
const EXAMPLES = [
  "Итоги квартала для руководства, 8 слайдов, график выручки из таблицы",
  "Онбординг новичка в отдел: кто мы, как работаем, первые 30 дней",
  "Статус проекта для стейкхолдеров: сделано, риски, следующие шаги",
];

api("api/health").then((h) => {
  if (!h.llm) { $("notice").textContent = "Генерация недоступна: на сервере не настроен ключ модели. Готовые презентации можно открывать и править."; $("notice").classList.remove("hidden"); $("create").disabled = true; }
}).catch(() => {});

$("examples").replaceChildren(...EXAMPLES.map((t) => el("button", { class: "chip", type: "button", onclick: () => { $("brief").value = t; $("brief").focus(); } }, t)));

// --- выбор шаблона
api("api/templates").then((list) => {
  if (!list.some((t) => t.id === template)) template = list[0] ? list[0].id : "default";
  const render = () => $("tpl-pick").replaceChildren(...list.map((t) => el("button", { type: "button", class: `tpl-opt${t.id === template ? " active" : ""}`, title: t.description || t.name,
    onclick: () => { template = t.id; render(); } },
    el("img", { src: `api/templates/${t.id}/preview/1.svg`, alt: "" }), t.name)),
    el("a", { class: "btn sm quiet", href: "templates" }, "Все шаблоны →"));
  render();
}).catch(() => { $("tpl-pick").replaceChildren(el("span", { class: "muted small" }, "Шаблон по умолчанию")); });

// --- файлы
const drop = $("drop");
drop.addEventListener("click", (e) => { if (e.target.closest("button")) return; $("files").click(); });
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("files").click(); } });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
$("files").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
function addFiles(list) { for (const f of list) picked.push(f); renderFiles(); }
function renderFiles() {
  $("drophint").textContent = picked.length ? "Добавить ещё файлы" : "Перетащите файлы сюда или нажмите, чтобы выбрать";
  $("filelist").replaceChildren(...picked.map((f, i) => {
    const kind = fileKind(f.name);
    return el("li", { class: kind === "bad" ? "bad" : "" },
      el("span", { class: "kind", title: kind }, KIND_ICON[kind]),
      el("span", { class: "name", title: f.name }, f.name),
      el("span", { class: "muted tiny" }, kind === "bad" ? "формат не поддерживается" : fmtSize(f.size)),
      el("button", { class: "quiet sm", type: "button", "aria-label": `Убрать ${f.name}`, onclick: () => { picked.splice(i, 1); renderFiles(); } }, "✕"));
  }));
}

// --- создание
$("create").addEventListener("click", async () => {
  const btn = $("create");
  $("error").textContent = "";
  const bad = picked.filter((f) => fileKind(f.name) === "bad");
  if (bad.length) { $("error").textContent = `Уберите файлы неподдерживаемого формата: ${bad.map((f) => f.name).join(", ")}`; return; }
  if (!$("brief").value.trim() && !picked.length) { $("error").textContent = "Опишите презентацию или приложите хотя бы один файл."; $("brief").focus(); return; }
  btn.disabled = true;
  try {
    const ids = [];
    for (const f of picked) { $("status").textContent = `Загружаю ${f.name}…`; ids.push((await upload("api/uploads", f)).upload_id); }
    $("status").textContent = "Открываю…";
    const { deck_id } = await api("api/decks", { json: { brief: $("brief").value, upload_ids: ids, template } });
    location.href = `d/${deck_id}`;
  } catch (e) {
    $("error").textContent = e.message; $("status").textContent = ""; btn.disabled = false;
  }
});
