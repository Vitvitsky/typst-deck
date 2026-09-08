// Общая оболочка: боковое меню как в DeepSeek — новая презентация, разделы, недавние колоды, статус модели.
import { api, el } from "./api.js";

const NAV = [
  ["decks", "decks", "Мои презентации", "▤"],
  ["history", "history", "История обращений", "⟲"],
  ["templates", "templates", "Мои шаблоны", "◫"],
];
const KEY = "typst-deck:sidebar";

function stored() { try { return localStorage.getItem(KEY); } catch { return null; } }
function store(v) { try { localStorage.setItem(KEY, v); } catch { /* приватный режим */ } }

function dayGroup(iso) {
  const d = new Date(iso), now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff <= 0) return "Сегодня";
  if (diff === 1) return "Вчера";
  if (diff < 7) return "На этой неделе";
  return "Раньше";
}

export function mountShell({ active = "", deckId = null, defaultCollapsed = false } = {}) {
  const root = document.getElementById("sidebar");
  if (!root) return;
  const saved = stored();
  let collapsed = saved === null ? defaultCollapsed : saved === "1";
  const apply = () => { document.documentElement.classList.toggle("sb-collapsed", collapsed); root.setAttribute("aria-expanded", String(!collapsed)); };
  apply();

  const toggle = el("button", { class: "sb-toggle quiet icon", title: "Свернуть меню", "aria-label": "Свернуть или развернуть меню",
    onclick: () => { collapsed = !collapsed; store(collapsed ? "1" : "0"); apply(); } }, "‹");
  const brand = el("a", { class: "sb-brand", href: "./", title: "typst-deck" }, el("span", { class: "sb-logo" }, "td"), el("span", { class: "sb-text" }, "typst-deck"));
  const newBtn = el("a", { class: "btn primary sb-new", href: "./", title: "Новая презентация" }, el("span", { class: "sb-ico" }, "＋"), el("span", { class: "sb-text" }, "Новая презентация"));
  const nav = el("nav", { class: "sb-nav", "aria-label": "Разделы" }, ...NAV.map(([key, href, label, ico]) =>
    el("a", { class: `sb-item${active === key ? " active" : ""}`, href, title: label }, el("span", { class: "sb-ico" }, ico), el("span", { class: "sb-text" }, label))));
  const recent = el("div", { class: "sb-recent" });
  const status = el("div", { class: "sb-status muted tiny" });
  root.replaceChildren(el("div", { class: "sb-head" }, brand, toggle), newBtn, nav, recent, status);

  api("api/decks").then((decks) => {
    if (!decks.length) { recent.replaceChildren(el("div", { class: "sb-text tiny muted", style: "padding:6px 10px" }, "Недавних презентаций нет")); return; }
    const groups = new Map();
    for (const d of decks.slice(0, 20)) { const g = dayGroup(d.updated_at); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(d); }
    const parts = [el("div", { class: "sb-label sb-text" }, "Недавние")];
    for (const [g, items] of groups) {
      parts.push(el("div", { class: "sb-group sb-text" }, g));
      for (const d of items) parts.push(el("a", { class: `sb-deck${d.id === deckId ? " active" : ""}`, href: `d/${d.id}`, title: d.title },
        el("span", { class: `sb-dot ${d.status}` }), el("span", { class: "sb-text t" }, d.title)));
    }
    if (decks.length > 20) parts.push(el("a", { class: "sb-deck sb-text muted", href: "decks" }, `Все ${decks.length} →`));
    recent.replaceChildren(...parts);
  }).catch(() => {});

  api("api/health").then((h) => {
    status.replaceChildren(el("span", { class: `sb-dot ${h.llm ? "ready" : "failed"}` }), el("span", { class: "sb-text" }, h.llm ? `Модель: ${h.model}` : "Модель не подключена"));
    status.title = h.llm ? `Подключена модель ${h.model}` : "Ключ модели не настроен";
  }).catch(() => {});
}
