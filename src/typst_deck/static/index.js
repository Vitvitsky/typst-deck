import { api, upload, waitJob, el } from "./api.js";

const $ = (id) => document.getElementById(id);
const picked = [];

$("files").addEventListener("change", (e) => {
  for (const f of e.target.files) picked.push(f);
  e.target.value = "";
  renderFiles();
});

function renderFiles() {
  const ul = $("filelist");
  ul.replaceChildren(...picked.map((f, i) => el("li", {},
    el("span", {}, f.name, " ", el("span", { class: "muted" }, `${Math.round(f.size / 1024)} КБ`)),
    el("button", { class: "small", onclick: () => { picked.splice(i, 1); renderFiles(); } }, "убрать"))));
}

$("create").addEventListener("click", async () => {
  const btn = $("create");
  $("error").textContent = "";
  btn.disabled = true;
  try {
    const ids = [];
    for (const f of picked) {
      $("status").textContent = `Загружаю ${f.name}…`;
      ids.push((await upload("api/uploads", f)).upload_id);
    }
    $("status").textContent = "Собираю презентацию…";
    const { deck_id, job_id } = await api("api/decks", { json: { brief: $("brief").value, upload_ids: ids } });
    const job = await waitJob(job_id, (j) => { $("status").textContent = j.status === "running" ? "Модель собирает слайды…" : "В очереди…"; });
    if (job.status === "failed") $("error").textContent = `Генерация не удалась: ${job.error}`;
    location.href = `d/${deck_id}`;
  } catch (e) {
    $("error").textContent = e.message;
    $("status").textContent = "";
  } finally {
    btn.disabled = false;
  }
});
