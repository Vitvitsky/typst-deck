import { api, el } from "./api.js";
import { mountShell } from "./shell.js";

mountShell({ active: "templates" });
const $ = (id) => document.getElementById(id);
const TYPES = ["Заглавный", "Раздел", "Текст и картинка", "Диаграмма", "График", "Финальный"];

api("api/templates").then((list) => {
  if (!list.length) { $("list").replaceChildren(el("div", { class: "empty" }, "Шаблонов нет: положите deck.typ в template/ или templates/<имя>/.")); return; }
  $("list").replaceChildren(...list.map((t) => {
    const cover = el("img", { src: `api/templates/${t.id}/preview/1.svg`, alt: `${t.name}: заглавный слайд` });
    const caption = el("span", { class: "muted tiny" }, TYPES[0]);
    const strip = el("div", { class: "strip" }, ...[2, 3, 4, 5, 6].map((n) => el("img", { src: `api/templates/${t.id}/preview/${n}.svg`, alt: TYPES[n - 1], title: TYPES[n - 1],
      onclick: (e) => { cover.src = e.target.src; caption.textContent = TYPES[n - 1]; strip.querySelectorAll("img").forEach((i) => i.classList.toggle("active", i === e.target)); } })));
    return el("article", { class: "tpl" },
      el("div", { class: "cover" }, cover), strip,
      el("div", { class: "meta" },
        el("div", { style: "display:flex;justify-content:space-between;gap:8px" }, el("strong", {}, t.name), caption),
        el("div", { class: "muted small" }, t.description || `Каталог ${t.id}`),
        el("div", { class: "row" }, el("a", { class: "btn sm primary", href: `./?template=${encodeURIComponent(t.id)}` }, "Создать с этим шаблоном"), el("span", { class: "sp" }), el("span", { class: "muted tiny" }, t.id))));
  }));
}).catch((e) => $("list").replaceChildren(el("div", { class: "error" }, e.message)));
