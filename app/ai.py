"""`claude -p`（Claude Codeのヘッドレスモード）の呼び出しと、応答の検証（SPEC 6章）。

`claude -p` を呼ぶのはこのファイルの run_claude だけ。テストでは run_claude の代わりに偽物を渡す。
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "search.md"
MAX_LOCAL = 10  # SPEC 4.2
MAX_PER_SITE = 3  # SPEC 4.3

KINDS = ("bgm", "se", "ambient")
TEMPOS = ("slow", "medium", "fast")

# 応答の形（SPEC 9.4）
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "conditions": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(KINDS)},
                "mood": {"type": "array", "items": {"type": "string"}},
                "genre": {"type": "array", "items": {"type": "string"}},
                "tempo": {"type": ["string", "null"], "enum": [*TEMPOS, None]},
                "loop": {"type": ["boolean", "null"]},
            },
            "required": ["kind", "mood", "genre", "tempo", "loop"],
        },
        "local": {
            "type": "array",
            "items": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        },
        "sites": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "site_id": {"type": "string"},
                    "type": {"type": "string", "enum": ["category", "search"]},
                    "category_id": {"type": "string"},
                    "q": {"type": "string"},
                },
                "required": ["site_id", "type"],
            },
        },
    },
    "required": ["conditions", "local", "sites"],
}


class AIError(Exception):
    """AIを呼べなかった、または応答が使えなかった。メッセージはそのまま画面に出す（SPEC 10章）。

    kind：画面の帯の出し分けに使う。"login"（未インストール・未ログイン）／"limit"（利用上限）／
    "timeout"（時間切れ。再試行ボタンを出す）／"invalid_json"（JSONとして読めない）／"error"（その他）
    hint：帯の下に小さく出す説明（手順など）。
    """

    def __init__(self, message: str, kind: str = "error", hint: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.hint = hint


class InvalidJSON(AIError):
    """応答がJSONとして読めない。設定の回数（既定1回）だけ自動で再試行する（SPEC 10章）。"""

    def __init__(self):
        super().__init__("AIの応答をJSONとして読み取れませんでした", "invalid_json",
                         "自動で再試行しましたが読み取れませんでした。もう一度「探す」を押してください。")


LOGIN_MESSAGE = "Claude Code にログインしてください"
LOGIN_HINT = "ターミナルで「claude」を起動してログインしてから、もう一度「探す」を押してください。"
JST = timezone(timedelta(hours=9))

# claude -p のエラー文の見分け方。未ログインは実物で確認した（"Not logged in · Please run /login"）。
# 利用上限は手元で起こせないので、知られている言い方（"Claude AI usage limit reached|<リセットのUNIX時刻>"、
# "You've hit your limit · resets 11pm (Asia/Tokyo)" など）と HTTP 429 で見分ける
_LIMIT = re.compile(r"limit reached|hit your limit|usage limit|rate limit|rate_limit", re.I)
_LOGIN = re.compile(r"not logged in|/login|invalid api key|authenticat|oauth|credential", re.I)


def _limit_reset(text: str) -> str | None:
    """エラー文からリセット時刻を取り出し、帯に出す一文にする。分からなければ None。"""
    m = re.search(r"\|\s*(\d{10})\b", text)
    if m:
        return datetime.fromtimestamp(int(m.group(1)), JST).strftime("%H:%M ごろ回復する見込みです。")
    m = re.search(r"resets?\s+(?:at\s+)?([^·∙|\n]+)", text, re.I)
    if m:
        return f"リセット：{m.group(1).strip()}"
    return None


def error_from_claude(text: str, api_status=None) -> AIError:
    """claude -p が返したエラー文を、画面に出すエラーに置き換える。"""
    text = text.strip()
    if api_status == 429 or _LIMIT.search(text):
        return AIError("利用上限に達しました", "limit",
                       _limit_reset(text) or "しばらく待ってから、もう一度「探す」を押してください。")
    if api_status in (401, 403) or _LOGIN.search(text):
        return AIError(LOGIN_MESSAGE, "login", LOGIN_HINT)
    return AIError(f"AIがエラーを返しました：{text or '不明なエラー'}")


def build_command(claude_path: str) -> list:
    """`claude -p` のコマンドライン。フラグは公式ドキュメント（CLI reference / headless）で確認したもの。"""
    return [
        claude_path, "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(RESPONSE_SCHEMA),
        "--append-system-prompt-file", str(PROMPT_PATH),
        # 使える道具を読み取り系だけにする（書き込み・コマンド実行の道具はそもそも渡さない）
        "--tools", "Read,Grep,Glob",
        # 確認が要る操作（作業フォルダの外を読むなど）は、聞かずにすべて断る
        "--permission-mode", "dontAsk",
        "--permission-prompts", "none",
        # ユーザー設定のMCP・フック・CLAUDE.md・スキルを読み込まない
        "--strict-mcp-config",
        "--safe-mode",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]


def run_claude(prompt: str, cwd: Path, timeout_sec: float) -> str:
    """`claude -p` を子プロセスで1回呼び、標準出力（JSON）を返す。"""
    claude_path = shutil.which("claude")
    if claude_path is None:
        raise AIError(LOGIN_MESSAGE, "login",
                      "Claude Code が見つかりません。インストールしてから、" + LOGIN_HINT)
    try:
        proc = subprocess.run(
            build_command(claude_path),
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=timeout_sec,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,  # 黒い窓を出さない
        )
    except subprocess.TimeoutExpired:
        raise AIError(f"時間切れ（{timeout_sec:g}秒以内に応答がありませんでした）", "timeout")
    if not proc.stdout.strip():
        err = error_from_claude(proc.stderr)
        if err.kind == "error":
            err = AIError(f"AIの呼び出しに失敗しました：{proc.stderr.strip() or f'終了コード {proc.returncode}'}")
        raise err
    return proc.stdout


def _parse_answer(stdout: str) -> dict:
    """`--output-format json` の出力から、AIの答え（SPEC 9.4 の形）を取り出す。"""
    try:
        outer = json.loads(stdout)
    except json.JSONDecodeError:
        raise InvalidJSON()
    if not isinstance(outer, dict):
        raise InvalidJSON()
    if outer.get("is_error"):
        raise error_from_claude(str(outer.get("result") or outer.get("subtype") or ""), outer.get("api_error_status"))

    answer = outer.get("structured_output")
    if answer is None:  # 念のため、本文にJSONが書かれている場合も読む
        text = str(outer.get("result") or "").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        try:
            answer = json.loads(text)
        except json.JSONDecodeError:
            raise InvalidJSON()
    if not isinstance(answer, dict):
        raise AIError("AIの応答の形が正しくありません")
    return answer


def _clean_conditions(c) -> dict:
    if not isinstance(c, dict) or c.get("kind") not in KINDS:
        raise AIError("AIの応答の形が正しくありません（条件が読み取れません）")

    def words(v):
        return [s.strip() for s in v if isinstance(s, str) and s.strip()] if isinstance(v, list) else []

    return {
        "kind": c["kind"],
        "mood": words(c.get("mood")),
        "genre": words(c.get("genre")),
        "tempo": c.get("tempo") if c.get("tempo") in TEMPOS else None,
        "loop": c.get("loop") if isinstance(c.get("loop"), bool) else None,
    }


def sites_for_prompt(sites: list) -> str:
    """AIに渡すサイト一覧（sites.json から URL を除いたもの）。URLはサーバーが組み立てるので見せない（SPEC 6.3）。"""
    return json.dumps([
        {
            "site_id": s["id"],
            "name": s["name"],
            "kinds": s["kinds"],
            "search": s.get("search_url") is not None,
            "categories": [{"category_id": c["id"], "name": c["name"], "kind": c["kind"]} for c in s["categories"]],
            "note": s.get("note", ""),
        }
        for s in sites
    ], ensure_ascii=False, indent=1)


def build_site_links(raw, sites: list, kind: str) -> list:
    """SPEC 6.4：AIが返した site_id＋category_id／q から、sites.json をもとに URL を組み立てる。

    次のものは捨てる：sites.json にない site_id・category_id、search_url が null のサイトへの検索、空の検索語、
    場面の種類（kind）を扱わないサイトやカテゴリ（SPEC 6.3）、同じ案内の重複。各サイト最大3件。
    """
    if not isinstance(raw, list):
        return []
    by_id = {s["id"]: s for s in sites}
    links, seen, per_site = [], set(), {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        site = by_id.get(item.get("site_id"))
        if site is None or kind not in site["kinds"]:
            continue
        if item.get("type") == "category":
            cat = next((c for c in site["categories"] if c["id"] == item.get("category_id")), None)
            if cat is None or cat["kind"] != kind:
                continue
            label, url = cat["name"], cat["url"]
        elif item.get("type") == "search":
            q = item.get("q")
            q = " ".join(q.split()) if isinstance(q, str) else ""
            if not q or site.get("search_url") is None:
                continue
            label, url = f"検索：{q}", site["search_url"].replace("{q}", quote(q, safe=""))
        else:
            continue
        if url in seen or per_site.get(site["id"], 0) >= MAX_PER_SITE:
            continue
        seen.add(url)
        per_site[site["id"]] = per_site.get(site["id"], 0) + 1
        links.append({"site_id": site["id"], "site_name": site["name"], "label": label, "url": url})
    return links


def validate(answer: dict, known_ids, sites: list = ()) -> dict:
    """SPEC 6.4：目録にないIDは捨てる。重複も除き、最大10件に切り詰める。サイトの案内は build_site_links で確かめる。"""
    local = answer.get("local")
    if not isinstance(local, list):
        raise AIError("AIの応答の形が正しくありません（候補の一覧がありません）")
    ids = []
    for item in local:
        fid = item.get("id") if isinstance(item, dict) else None
        if isinstance(fid, str) and fid in known_ids and fid not in ids:
            ids.append(fid)
    conditions = _clean_conditions(answer.get("conditions"))
    return {
        "conditions": conditions,
        "local": [{"id": i} for i in ids[:MAX_LOCAL]],
        "sites": build_site_links(answer.get("sites"), list(sites), conditions["kind"]),
    }


def search(query: str, data_dir: Path, known_ids, timeout_sec: float, runner=run_claude, sites: list = (),
           retries: int = 1, root_ids=None) -> dict:
    """場面の説明から、条件・ローカル候補・サイトへの案内を返す。作業フォルダは data/（AIはそこの index.json を検索する）。

    retries：応答がJSONとして読めなかったときに自動で呼び直す回数（config の ai.retry_on_invalid_json）。
    root_ids：候補にしてよい登録フォルダの root_id。目録には無効にしたフォルダの行も残っていることがあるので、AIに伝える。
    """
    prompt = f"場面の説明：\n{query}\n\n"
    if root_ids is not None:
        prompt += f"検索対象の登録フォルダ（root_id）：{', '.join(root_ids) or 'なし'}\n\n"
    prompt += f"誘導先サイトの一覧：\n{sites_for_prompt(list(sites))}"
    for attempt in range(retries + 1):
        try:
            answer = _parse_answer(runner(prompt, data_dir, timeout_sec))
            break
        except InvalidJSON:
            if attempt >= retries:
                raise
    return validate(answer, known_ids, sites)
