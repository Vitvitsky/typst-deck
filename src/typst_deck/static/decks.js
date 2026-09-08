import { api, el, toast, armConfirm, fmtDate } from "./api.js";
import { mountShell } from "./shell.js";

mountShell({ active: "decks" });
const $ = (id) => document.getElementById(id);
let all = [];
const STATUS = { generating: "собирается", failed: "ошибка генерации", ready: "готова" };

async function load() {
  try { all = await api("api/decks"); } catch (e) { $("decks").replaceChildren(el("div", { class: "error" }, e.message)); return; }
  render();
  if (all.some((d) => d.status === "generating")) setTimeout(load, 3000);
}

function render() {
  const q = $("search").value.trim().toLowerCase();
  const decks = all.filter((d) => !q || d.title.toLowerCase().includes(q));
  $("count").textContent = all.length ? `(${all.length})` : "";
  if (!all.length) { $("decks").replaceChildren(el("div", { class: "empty" }, "Пока ни одной презентации. ", el("a", { href: "./" }, "Создать первую"))); return; }
  if (!decks.length) { $("decks").replaceChildren(el("div", { class: "empty" }, `По запросу «${q}» ничего не найдено.`)); return; }
  $("decks").replaceChildren(...decks.map((d) => {
    const del = el("button", { class: "quiet sm danger", type: "button", "aria-label": "Удалить презентацию" }, "Удалить");
    del.addEventListener("click", () => armConfirm(del, "Точно удалить?", async () => {
      try { await api(`api/decks/${d.id}`, { method: "DELETE" }); all = all.filter((x) => x.id !== d.id); render(); toast(`«${d.title}» удалена`); }
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
$("search").addEventListener("input", render);
load();
