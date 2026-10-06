const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// メニューで画面を切り替える
document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b === button));
    document.querySelectorAll(".screen").forEach((s) => {
      s.classList.toggle("active", s.id === `screen-${button.dataset.screen}`);
    });
  });
});

// API呼び出し。失敗したらサーバーのメッセージ（detail）を持った Error を投げる
async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `エラーが発生しました（${res.status}）`);
  return data;
}

// type: "error"（赤）／"warn"（黄）。text が空なら消す
function showMsg(el, type, text) {
  el.innerHTML = text ? `<div class="band ${type} msg-band">${type === "error" ? "✖" : "⚠"}<div class="msg">${esc(text)}</div></div>` : "";
}

const fmtDate = (iso) => iso.slice(0, 16).replace("T", " ");

/* ---------- 設定：検索対象フォルダ ---------- */

let rootsCache = [];
let indexSummary = null; // GET /api/scan の index（まだスキャンしていなければ null）

async function loadRoots() {
  try {
    const { roots } = await api("GET", "/api/roots");
    rootsCache = roots;
    renderRoots();
  } catch (e) {
    showMsg($("#roots-msg"), "error", e.message);
  }
}

function statusCell(r) {
  if (!r.enabled) return [`<td class="hint">無効</td>`, `<td class="num">—</td>`];
  const st = indexSummary && indexSummary.roots.find((x) => x.id === r.id);
  // 目録にないフォルダ（追加後・有効に戻した後にまだ再スキャンしていない）
  if (!st) return [`<td class="hint">未スキャン</td>`, `<td class="num">—</td>`];
  return [
    `<td>${st.status === "ok" ? `<span class="status-ok">● OK</span>` : `<span class="status-missing">● 見つかりません</span>`}</td>`,
    `<td class="num">${st.file_count.toLocaleString()}</td>`,
  ];
}

function renderRoots() {
  $("#stat-roots").textContent = rootsCache.length;
  if (rootsCache.length === 0) {
    $("#roots").innerHTML = `<tr><td colspan="5" class="hint">まだフォルダが登録されていません。下の「フォルダを追加」から登録してください。</td></tr>`;
    return;
  }
  $("#roots").innerHTML = rootsCache.map((r) => `<tr data-id="${esc(r.id)}">
      <td><button type="button" class="toggle ${r.enabled ? "on" : ""}" title="${r.enabled ? "有効（クリックで無効に）" : "無効（クリックで有効に）"}" aria-pressed="${r.enabled}"></button></td>
      <td><b>${esc(r.label)}</b><div class="path">${esc(r.path)}</div></td>
      ${statusCell(r).join("")}
      <td><button type="button" class="btn small danger">削除</button></td>
    </tr>`).join("");
}

/* ---------- 設定：目録（再スキャン） ---------- */

let scanTimer = null;

function renderScan(s) {
  indexSummary = s.index;
  $("#stat-files").textContent = s.index ? s.index.file_count.toLocaleString() : "—";
  $("#stat-scanned").textContent = s.index ? fmtDate(s.index.scanned_at) : "—";
  $("#rescan").disabled = s.running;

  let pct = 0;
  let text = "まだスキャンしていません";
  if (s.running) {
    pct = s.total ? (s.done / s.total) * 100 : 0;
    text = s.total ? `スキャン中… <span class="num">${s.done.toLocaleString()} / ${s.total.toLocaleString()}</span> ファイル` : "スキャン中… ファイルを数えています";
  } else if (s.index) {
    pct = 100;
    text = `スキャン完了：<span class="num">${s.index.file_count.toLocaleString()}</span> ファイル`;
  }
  $("#scan-bar").style.width = `${pct}%`;
  $("#scan-text").innerHTML = text;
  if (s.error) showMsg($("#scan-msg"), "error", s.error);
  renderRoots();
}

async function pollScan() {
  clearTimeout(scanTimer);
  try {
    const s = await api("GET", "/api/scan");
    renderScan(s);
    if (s.running) scanTimer = setTimeout(pollScan, 300);
  } catch (e) {
    showMsg($("#scan-msg"), "error", e.message);
  }
}

$("#rescan").addEventListener("click", async () => {
  showMsg($("#scan-msg"), "", "");
  try {
    await api("POST", "/api/scan");
  } catch (e) {
    showMsg($("#scan-msg"), "error", e.message);
  }
  pollScan();
});

$("#roots").addEventListener("click", async (ev) => {
  const row = ev.target.closest("tr[data-id]");
  if (!row) return;
  const id = row.dataset.id;
  showMsg($("#roots-msg"), "", "");
  try {
    if (ev.target.classList.contains("toggle")) {
      await api("PATCH", `/api/roots/${encodeURIComponent(id)}`, { enabled: !ev.target.classList.contains("on") });
    } else if (ev.target.classList.contains("danger")) {
      const label = row.querySelector("b").textContent;
      if (!confirm(`「${label}」を検索対象から外しますか？\n（フォルダの中のファイルは消えません）`)) return;
      await api("DELETE", `/api/roots/${encodeURIComponent(id)}`);
    } else {
      return;
    }
  } catch (e) {
    showMsg($("#roots-msg"), "error", e.message);
  }
  loadRoots();
});

$("#add-root").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const msg = $("#add-root-msg");
  try {
    const { warning } = await api("POST", "/api/roots", { path: form.elements.path.value, label: form.elements.label.value });
    form.reset();
    showMsg(msg, warning ? "warn" : "", warning || "");
    loadRoots();
  } catch (e) {
    showMsg(msg, "error", e.message);
  }
});

loadRoots();
pollScan();
