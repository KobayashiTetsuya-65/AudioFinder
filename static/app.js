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

// API呼び出し。失敗したらサーバーのメッセージ（detail）を持った Error を投げる。
// 検索のエラーは種類と説明（{ kind, hint }）も e.info に持たせる
async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : `エラーが発生しました（${res.status}）`);
    err.info = data.error || null;
    throw err;
  }
  return data;
}

// type: "error"（赤）／"warn"（黄）。text が空なら消す
function showMsg(el, type, text) {
  el.innerHTML = text ? `<div class="band ${type} msg-band">${type === "error" ? "✖" : "⚠"}<div class="msg">${esc(text)}</div></div>` : "";
}

const fmtDate = (iso) => iso.slice(0, 16).replace("T", " ");
const fmtDur = (sec) => sec == null ? "--:--" : `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

/* ---------- 探す ---------- */

const KIND = { bgm: "BGM", se: "SE", ambient: "環境音" };
const TEMPO = { slow: "ゆっくり", medium: "ふつう", fast: "速め" };

function conditionsHtml(c) {
  const chips = [`<span class="chip kind">${KIND[c.kind]}</span>`];
  c.mood.forEach((m) => chips.push(`<span class="chip mood"><span class="k">雰囲気</span>${esc(m)}</span>`));
  c.genre.forEach((g) => chips.push(`<span class="chip genre"><span class="k">ジャンル</span>${esc(g)}</span>`));
  if (c.tempo) chips.push(`<span class="chip tempo"><span class="k">テンポ</span>${TEMPO[c.tempo]}</span>`);
  if (c.loop === true) chips.push(`<span class="chip loop">ループ推奨</span>`);
  return `<div class="win"><div class="win-title">読み取った条件</div><div class="chips">${chips.join("")}</div></div>`;
}

function badge(likelyBgm) {
  if (likelyBgm === true) return `<span class="badge bgm">BGM</span>`;
  if (likelyBgm === false) return `<span class="badge se">SE</span>`;
  return `<span class="badge unk">?</span>`;
}

function tracksHtml(tracks) {
  const rows = tracks.map((t, i) => `
    <li class="track" data-id="${esc(t.id)}">
      <span class="rank num">${i + 1}</span>
      <button type="button" class="icon-btn play" title="試聴" ${t.readable ? "" : "disabled"}>▶</button>
      <div class="info">
        <div class="name">${esc(t.filename)}</div>
        <div class="path">${esc(t.root_label)} / ${esc(t.rel_path)}</div>
        ${t.readable ? "" : `<div class="note">このファイルは再生できません</div>`}
      </div>
      ${badge(t.likely_bgm)}
      <span class="dur num">${fmtDur(t.duration_sec)}</span>
      <button type="button" class="icon-btn folder" title="エクスプローラーで開く">📂</button>
    </li>`).join("");
  return `<div class="win"><div class="win-title">手持ちの素材 <span class="sub">${tracks.length}件</span></div><ul class="tracks">${rows}</ul></div>`;
}

// links: [{ site_id, site_name, label, url }]。サイトごとのカードにまとめる（並びはAIが返した順）
function sitesHtml(links) {
  const groups = new Map();
  links.forEach((l) => {
    if (!groups.has(l.site_id)) groups.set(l.site_id, { name: l.site_name, links: [] });
    groups.get(l.site_id).links.push(l);
  });
  const cards = [...groups.values()].map((g) => `
    <div class="site"><h4>${esc(g.name)}</h4>
      ${g.links.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer" title="${esc(l.url)}"><span>${esc(l.label)}</span><span class="ext">サイトで開く ↗</span></a>`).join("")}
    </div>`).join("");
  const inner = cards ? `<div class="sites">${cards}</div>` : `<div class="hint">合うサイトの探し先はありませんでした</div>`;
  return `<div class="win"><div class="win-title">国内サイトで探す <span class="sub">試聴・ダウンロードはサイト側で</span></div>${inner}</div>`;
}

/* ---------- 試聴・エクスプローラーで開く ---------- */

// 同時に鳴るのは1つだけにするため、音を出すのはこの1つの Audio だけ
const player = new Audio();
let playingBtn = null; // 再生中の▶ボタン（■になっている）

function stopPlaying() {
  player.pause();
  player.removeAttribute("src");
  player.load();
  if (playingBtn) {
    playingBtn.textContent = "▶";
    playingBtn.title = "試聴";
    playingBtn = null;
  }
}

player.addEventListener("ended", stopPlaying);

// 1行の下に、失敗したときの赤字を出す（次に押したときに消す）
function trackNote(row, text) {
  let note = row.querySelector(".note.play-error");
  if (!note && text) {
    note = document.createElement("div");
    note.className = "note play-error";
    row.querySelector(".info").append(note);
  }
  if (note) text ? (note.textContent = text) : note.remove();
}

async function togglePlay(btn, row) {
  const same = playingBtn === btn;
  stopPlaying();
  if (same) return; // 再生中の▶をもう一度押したら止めるだけ
  trackNote(row, "");
  playingBtn = btn;
  btn.textContent = "■";
  btn.title = "停止";
  player.src = `/api/audio/${encodeURIComponent(row.dataset.id)}`;
  try {
    await player.play();
  } catch (e) {
    if (e.name === "AbortError") return; // 読み込み中に別の▶が押された
    if (playingBtn === btn) stopPlaying();
    trackNote(row, "このファイルは再生できません（ファイルが移動・削除されたか、ブラウザが対応していない形式です）");
  }
}

async function reveal(row) {
  trackNote(row, "");
  try {
    await api("POST", `/api/reveal/${encodeURIComponent(row.dataset.id)}`);
  } catch (e) {
    trackNote(row, e.message);
  }
}

/* ---------- 帯（エラー・注意）と0件（SPEC 8.2・10章） ---------- */

// 検索画面の帯。small は帯の下に小さく出す説明、retry なら「再試行」ボタンをつける
function bandHtml(type, icon, title, small, retry) {
  return `<div class="band ${type}">${icon}<div class="msg">${esc(title)}${small ? `<small>${esc(small)}</small>` : ""}</div>` +
    `${retry ? `<button type="button" class="btn small retry">再試行</button>` : ""}</div>`;
}

// e.info.kind：login（未インストール・未ログイン）／limit（利用上限）／timeout（時間切れ）／invalid_json／error
function errorBandHtml(e) {
  const info = e.info || {};
  if (info.kind === "timeout") return bandHtml("error", "⌛", e.message, info.hint, true);
  return bandHtml("error", "✖", e.message, info.hint, false);
}

function missingRootsHtml(roots) {
  return roots.map((r) => bandHtml("warn", "⚠", `フォルダ「${r.label}」が見つかりません`,
    `${r.path} を飛ばして検索しました。外付けドライブが外れていないか確認してください。`, false)).join("");
}

const EMPTY_HTML = `<div class="win empty"><div class="big">該当なし</div><p>こんな言い方で試してみてください：</p><ul>
  <li>ジャンルを外す（例：「ボス戦、緊迫感」だけにする）</li>
  <li>英語で書く（例：「boss battle, epic」）</li>
  <li>近い場面に言い換える（例：「強敵との戦闘」）</li></ul></div>`;

// 結果は書き直されるので、一覧の外側で受ける
$("#search-body").addEventListener("click", (ev) => {
  if (ev.target.closest("button.retry")) {
    if (lastQuery !== null) runSearch(lastQuery);
    return;
  }
  const btn = ev.target.closest("button.icon-btn");
  const row = btn && btn.closest(".track[data-id]");
  if (!row || btn.disabled) return;
  if (btn.classList.contains("play")) togglePlay(btn, row);
  else if (btn.classList.contains("folder")) reveal(row);
});

let searchTimer = null;

function showSearching() {
  const started = Date.now();
  $("#search-body").innerHTML = `<div class="win loading"><div class="spell">サウンドを探索中<span class="dots"><span>.</span><span>.</span><span>.</span></span></div><div class="elapsed num">経過 0 秒</div></div>`;
  const elapsed = $("#search-body .elapsed");
  clearInterval(searchTimer);
  searchTimer = setInterval(() => {
    elapsed.textContent = `経過 ${Math.floor((Date.now() - started) / 1000)} 秒`;
  }, 1000);
}

let lastQuery = null; // 再試行ボタンで、同じ場面説明をもう一度探すため

async function runSearch(query) {
  const button = $("#quest button");
  const body = $("#search-body");
  if (button.disabled) return; // 検索中の二重送信を防ぐ
  lastQuery = query;
  button.disabled = true;
  stopPlaying(); // 結果を書き直すと▶ボタンが消えるので、先に止める
  showSearching();
  try {
    const r = await api("POST", "/api/search", { query });
    // 0件のときは「読み取った条件」の下に「該当なし」と言い換えの例。サイトの案内はあれば続けて出す
    const local = r.local.length ? tracksHtml(r.local) : EMPTY_HTML;
    body.innerHTML = missingRootsHtml(r.missing_roots) + conditionsHtml(r.conditions) + local + sitesHtml(r.sites);
  } catch (e) {
    body.innerHTML = errorBandHtml(e);
  } finally {
    clearInterval(searchTimer);
    button.disabled = false;
  }
}

$("#quest").addEventListener("submit", (ev) => {
  ev.preventDefault();
  runSearch(ev.target.elements.query.value);
});

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
