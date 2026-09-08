import { api, el } from "./api.js";
import { mountShell } from "./shell.js";

mountShell({ active: "history" });
const $ = (id) => document.getElementById(id);
let all = [];
const dayKey = (iso) => new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
const time = (iso) => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });

function render() {
  const q = $("search").value.trim().toLowerCase();
  const items = all.filter((h) => !q || h.text.toLowerCase().includes(q) || h.deck_title.toLowerCase().includes(q));
  if (!all.length) { $("list").replaceChildren(el("div", { class: "empty" }, "Обращений к модели пока не было.")); return; }
  if (!items.length) { $("list").replaceChildren(el("div", { class: "empty" }, "Ничего не найдено.")); return; }
  const parts = [];
  let day = null;
  for (const h of items) {
    const k = h.ts ? dayKey(h.ts) : "Без даты";
    if (k !== day) { day = k; parts.push(el("div", { class: "hist-group" }, k)); }
    parts.push(el("a", { class: "hist", href: `d/${h.deck_id}`, title: h.text },
      el("span", { class: "time num" }, h.ts ? time(h.ts) : ""),
      el("span", { class: "text" }, h.text),
      el("span", { class: "deck" }, h.deck_title)));
  }
  $("list").replaceChildren(...parts);
}
api("api/history").then((h) => { all = h; render(); }).catch((e) => $("list").replaceChildren(el("div", { class: "error" }, e.message)));
$("search").addEventListener("input", render);
