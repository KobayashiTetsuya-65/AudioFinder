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

/* ---------- 設定：検索対象フォルダ ---------- */

async function loadRoots() {
  try {
    const { roots } = await api("GET", "/api/roots");
    renderRoots(roots);
  } catch (e) {
    showMsg($("#roots-msg"), "error", e.message);
  }
}

function renderRoots(roots) {
  if (roots.length === 0) {
    $("#roots").innerHTML = `<tr><td colspan="5" class="hint">まだフォルダが登録されていません。下の「フォルダを追加」から登録してください。</td></tr>`;
    return;
  }
  // 状態とファイル数は再スキャン（目録）ができてから表示する
  $("#roots").innerHTML = roots.map((r) => `<tr data-id="${esc(r.id)}">
      <td><button type="button" class="toggle ${r.enabled ? "on" : ""}" title="${r.enabled ? "有効（クリックで無効に）" : "無効（クリックで有効に）"}" aria-pressed="${r.enabled}"></button></td>
      <td><b>${esc(r.label)}</b><div class="path">${esc(r.path)}</div></td>
      <td class="hint">未スキャン</td>
      <td class="num">—</td>
      <td><button type="button" class="btn small danger">削除</button></td>
    </tr>`).join("");
}

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
