// Обёртка над fetch: относительные пути (работают под префиксом за Nginx), ошибки API → Error.
export async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) {
    init.method = init.method || "POST";
    init.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
    init.body = JSON.stringify(opts.json);
    delete init.json;
  }
  const r = await fetch(path, init);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    const msg = data && data.error ? `${data.error.message}` : `HTTP ${r.status}`;
    const e = new Error(msg);
    e.status = r.status;
    throw e;
  }
  return data;
}

export async function upload(path, file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return api(path, { method: "POST", body: fd });
}

export const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

// Ждёт завершения задачи; onTick(job) вызывается на каждом опросе.
export async function waitJob(jobId, onTick) {
  for (;;) {
    const job = await api(`api/jobs/${jobId}`);
    if (onTick) onTick(job);
    if (job.status === "done" || job.status === "failed") return job;
    await sleep(1000);
  }
}

export function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    n.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return n;
}
