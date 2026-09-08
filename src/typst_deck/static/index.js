import { api, upload, el, toast, armConfirm, fileKind, KIND_ICON, fmtSize, fmtDate } from "./api.js";

const $ = (id) => document.getElementById(id);
const picked = [];
const EXAMPLES = [
  "Итоги квартала для руководства, 8 слайдов, график выручки из таблицы",
  "Онбординг новичка в отдел: кто мы, как работаем, первые 30 дней",
  "Статус проекта для стейкхолдеров: сделано, риски, следующие шаги",
];

// --- LLM доступна?
api("api/health").then((h) => {
  if (!h.llm) { $("notice").textContent = "Генерация недоступна: на сервере не настроен ключ модели. Можно открывать и править готовые презентации."; $("notice").classList.remove("hidden"); $("create").disabled = true; }
}).catch(() => {});

// --- примеры
$("examples").replaceChildren(...EXAMPLES.map((t) => el("button", { class: "chip", type: "button", onclick: () => { $("brief").value = t; $("brief").focus(); } }, t)));

// --- файлы: дропзона
const drop = $("drop");
drop.addEventListener("click", (e) => { if (e.target.closest("button")) return; $("files").click(); });
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("files").click(); } });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
$("files").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });

function addFiles(list) {
  for (const f of list) picked.push(f);
  renderFiles();
}

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
    for (const f of picked) {
      $("status").textContent = `Загружаю ${f.name}…`;
      ids.push((await upload("api/uploads", f)).upload_id);
    }
    $("status").textContent = "Открываю…";
    const { deck_id } = await api("api/decks", { json: { brief: $("brief").value, upload_ids: ids } });
    location.href = `d/${deck_id}`;
  } catch (e) {
    $("error").textContent = e.message;
    $("status").textContent = "";
    btn.disabled = false;
  }
});

// --- каталог
let all = [];
const STATUS = { generating: "собирается", failed: "ошибка генерации", ready: "готова" };

async function loadCatalog() {
  try { all = await api("api/decks"); } catch (e) { $("decks").replaceChildren(el("div", { class: "error" }, e.message)); return; }
  renderCatalog();
  if (all.some((d) => d.status === "generating")) setTimeout(loadCatalog, 3000);
}

function renderCatalog() {
  const q = $("search").value.trim().toLowerCase();
  const decks = all.filter((d) => !q || d.title.toLowerCase().includes(q));
  $("count").textContent = all.length ? `(${all.length})` : "";
  if (!all.length) { $("decks").replaceChildren(el("div", { class: "empty" }, "Пока ни одной презентации. Первая появится здесь после создания.")); return; }
  if (!decks.length) { $("decks").replaceChildren(el("div", { class: "empty" }, `По запросу «${q}» ничего не найдено.`)); return; }
  $("decks").replaceChildren(...decks.map((d) => {
    const del = el("button", { class: "quiet sm danger", type: "button", "aria-label": "Удалить презентацию" }, "Удалить");
    del.addEventListener("click", () => armConfirm(del, "Точно удалить?", async () => {
      try { await api(`api/decks/${d.id}`, { method: "DELETE" }); all = all.filter((x) => x.id !== d.id); renderCatalog(); toast(`«${d.title}» удалена`); }
      catch (e) { toast(e.message, { error: true }); }
    }));
    return el("article", { class: "card" },
      el("a", { class: "thumb", href: `d/${d.id}`, "aria-label": `Открыть ${d.title}` },
        d.has_build ? el("img", { src: `api/decks/${d.id}/slides/1.svg?v=${d.version}`, alt: "", loading: "lazy" })
          : el("div", { class: "nothumb" }, d.status === "generating" ? el("span", { class: "spinner" }) : "нет слайдов")),
      el("div", { class: "meta" },
        el("a", { class: "name", href: `d/${d.id}`, title: d.title }, d.title),
        el("div", { class: "muted tiny num" }, el("span", { class: `status-dot ${d.status}` }), `${STATUS[d.status]} · ${d.slide_count} сл. · ${fmtDate(d.updated_at)}`),
        el("div", { class: "row" },
          el("a", { class: "btn sm primary", href: `d/${d.id}` }, "Открыть"),
          d.has_build ? el("a", { class: "btn sm", href: `api/decks/${d.id}/deck.pdf`, download: true }, "PDF") : null,
          el("span", { class: "sp" }), del)));
  }));
}
$("search").addEventListener("input", renderCatalog);
loadCatalog();
