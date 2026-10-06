# Audio Finder 仕様書（SPEC）

ゲーム制作用のBGM・SEを、場面の説明から探して提案するローカルツール。

- 作成日：2026-10-06
- 状態：仕様確定（実装前）

---

## 1. 概要

自然文で場面を説明すると（例：「ボス戦、緊迫感あり、オーケストラ系、ループ前提」）、AIがそれを解釈し、次の2つを返す。

1. **手持ちのローカル素材**から合う候補（その場で試聴できる）
2. **国内フリー素材サイト**の「どこを・どんなキーワードで探すか」のリンク（試聴やダウンロードはサイト側で行う）

## 2. 利用者

- **自分ひとりだけ**。自分のPC上でのみ動かす
- ログイン機能・複数人での利用・外部公開はしない

## 3. 入力

- **自然文の場面説明を1件ずつ**入力する（日本語前提。英語が混じってもよい）
- 例：「カードを引くときの軽い音」「ショップ画面、落ち着いた木管」

## 4. 出力（1回の検索結果）

画面には上から順に、次の3ブロックを表示する。

### 4.1 AIが読み取った条件
解釈がずれていないか確認するための表示。例：`BGM／緊迫／オーケストラ／ループ推奨／テンポ速め`

### 4.2 ローカル候補（最大10件）
| 項目 | 内容 |
|---|---|
| ファイル名 | |
| フォルダ | 登録フォルダからの相対パス（例：`Fantasy RPG Music Pack/Battle/`） |
| 長さ | mm:ss |
| ▶ 試聴 | ブラウザ内で再生。再生できないファイルはボタンを無効にする |
| 📂 開く | エクスプローラーで、そのファイルを選択した状態で開く |

### 4.3 国内サイトへの誘導（各サイト1〜3件）
| 項目 | 内容 |
|---|---|
| サイト名 | |
| 探す場所 | カテゴリ名、または検索キーワード |
| リンク | クリックすると既定のブラウザで開く |

- 「なぜ合うか」の説明文は**出さない**（ローカル候補・サイト誘導の両方とも）

## 5. 情報の取得元

### 5.1 ローカル素材（ツールが実際に検索する）
- 設定画面で**検索対象フォルダを登録**する（複数可）
- 対象の形式：**wav / mp3 / ogg**
- 「再スキャン」ボタンで目録（`index.json`）を作り直す。**自動更新・フォルダ監視はしない**

### 5.2 国内フリー素材サイト（ツールはアクセスしない）
- 対象：**魔王魂 / 効果音ラボ / OpenTracks（旧DOVA-SYNDROME）**
- ツールは各サイトに**一切アクセスしない**。AIが `sites.json` をもとに、カテゴリページや検索ページへのリンクを組み立てるだけ
- リンクをクリックして検索するのは利用者本人（人）なので、robots.txtの対象外

## 6. AI部分

### 6.1 動かし方
- サーバーから **`claude -p`（Claude Codeのヘッドレスモード）を子プロセスとして呼ぶ**。出力形式はJSON（`--output-format json`）
- 今ログインしているClaude Codeのアカウントの**利用枠で動く**（API用の別会計・APIキーは使わない）
- 前提：PCにClaude Codeが入っていて、ログイン済みであること
- まずは**検索のたびに毎回起動**する。遅いと感じたら、Agent SDKでセッションをつなぎっぱなしにする方式へ切り替えを検討する（11章「将来の拡張候補」参照）

### 6.2 目録の検索方法
- `claude -p` には**読み取り専用の道具（ファイルを読む・文字列を検索する・ファイルを一覧する）だけを許可**する。書き込みやコマンド実行は禁止する
- AIが `index.json` の中を自分で検索して、候補を選ぶ（目録をまるごと渡すことはしない）
- 作業フォルダはツールの `data/` にする
- 許可する道具を指定する具体的なフラグは、実装時に公式ドキュメントで確認する

### 6.3 AIに守らせること（プロンプトの制約）
- 返すのは決められたJSONだけにする（9.4参照）
- ローカル候補は、`index.json` に**実在するIDだけ**を返す
- **サイトはURLを返さない**。`sites.json` の `site_id` と、カテゴリID（`category_id`）か検索語（`q`）だけを返す。URLはサーバーが組み立てる（存在しないURLが構造的に出ない）
- `sites.json` の `kinds` に合わないサイト（SEを探しているのにBGM専門のサイトなど）は選ばない
- 音源データそのものは扱わない（渡すのはファイル名やフォルダ名などの文字情報だけ）

### 6.4 サーバー側での検証
- 返ってきたローカル候補のIDが目録にないものは捨てる
- `site_id` や `category_id` が `sites.json` にないもの、`search_url` が `null` のサイトへの検索案内は捨てる
- 応答がJSONとして読めなければ、**1回だけ自動で再試行**する（10章参照）

## 7. 技術構成

### 7.1 構成
| 部分 | 採用するもの |
|---|---|
| 言語 | **Python 3.12以上** |
| サーバー | FastAPI ＋ uvicorn |
| 音声ファイルの情報読み取り | mutagen |
| 画面 | 素のHTML・CSS・JavaScript（ビルド作業なし、外部ライブラリなし） |
| AI | `claude -p`（子プロセス） |
| テスト | pytest（FastAPIの TestClient を使う） |
| 依存の管理 | `requirements.txt` ＋ 仮想環境 `.venv` |
| 待ち受け | **`127.0.0.1:8765`**（自分のPCの中からしか開けない。ポートは `config.json` で変更可） |

前提：PCにPython 3.12以上と、ログイン済みのClaude Codeが入っていること（2026-10-06時点ではPython未インストール）。

#### 選定の経緯
次の3つを比べた。条件は「ブラウザで動く、使いやすさ重視」。

| 候補 | 判断 |
|---|---|
| **Python ＋ FastAPI ＋ 素のHTML/JS** | **採用**。コードが最も少なく、音声の長さ読み取りがmutagen 1つで済み、ビルド作業もない |
| C# ＋ Blazor Server | C#だけで書けるのが利点。比較したうえで不採用 |
| TypeScript ＋ React ＋ Node.js | 新しく覚えることが多すぎ、自分専用の小さなツールには大げさなので不採用 |

### 7.2 テスト方針
- **自動テスト（pytest）**：画面を通さずに確かめられる処理が対象。単語への分解（`words`）、ID生成、目録の作成、AIの応答の検証、URLの組み立て、履歴の50件上限、各エラーのときの動き
- `claude -p` は自動テストでは**呼ばない**。決まった応答を返す偽物に差し替えてテストする
- **手動確認**：画面の操作、試聴、エクスプローラーで開く、本物の `claude -p` との接続は、`start.bat` で起動して実際に操作して確かめる

### 7.3 起動
- **`start.bat` をダブルクリック**すると、次の順に動く
  1. `.venv` がなければ作り、`requirements.txt` の中身をインストールする（初回だけ）
  2. サーバーを立ち上げ、ブラウザで `http://127.0.0.1:8765` を開く
- 終了はコンソールウィンドウを閉じる
- 常駐・自動起動はしない

### 7.4 AIの応答JSON
9.4を参照。

### 7.5 ファイル構成（案）
```
audio-finder/
├─ SPEC.md
├─ start.bat
├─ requirements.txt
├─ app/
│  ├─ main.py          … FastAPI本体（APIと画面の配信）
│  ├─ scanner.py       … フォルダをスキャンして目録を作る
│  ├─ ai.py            … claude -p の呼び出し・応答の検証
│  └─ prompts/         … AIへの指示文
├─ static/             … HTML / CSS / JS
├─ tests/              … pytest のテスト
└─ data/
   ├─ config.json      … 設定
   ├─ index.json       … 目録
   ├─ history.json     … 検索履歴
   └─ sites.json       … 誘導先サイトの一覧
```

## 8. 画面

### 8.1 検索画面（メイン）
- 場面説明の入力欄と「探す」ボタン
- 検索中の表示（経過秒数つき）
- 結果の3ブロック（4章）
- エラーは画面上部に帯で表示（10章）

### 8.2 設定画面
- 検索対象フォルダの一覧と、追加・削除。追加は**パスを文字で入力**する（ブラウザのフォルダ選択では絶対パスが取れないため）
- 「再スキャン」ボタン。進行状況・ファイル数・最後にスキャンした日時を表示する

### 8.3 履歴
- 直近50件の場面説明を一覧で表示する
- クリックすると、**AIを呼ばずに**そのときの結果を再表示する
- 今の目録にないファイルは「見つかりません」と表示し、試聴ボタンを無効にする

## 9. 保存とデータ構造

すべて `data/` 内のJSONファイルに保存する。中身はテキストなので、壊れたときは手で直せる。

| ファイル | 中身 | 書き込むのは |
|---|---|---|
| `config.json` | 設定 | 設定画面（手で編集してもよい） |
| `index.json` | 目録 | 再スキャン |
| `history.json` | 直近50件の検索履歴 | 検索が成功したとき |
| `sites.json` | 誘導先サイトの一覧 | **手で編集のみ**（編集画面は作らない） |

- お気に入り・採用管理は持たない

### 9.1 共通ルール
- 文字コードはUTF-8。各ファイルの先頭に `"version": 1` を持たせる（将来データの形を変えるときの目印）
- 日時はISO 8601形式で日本時間（例：`2026-10-06T21:30:00+09:00`）
- 項目名は英語の小文字とアンダースコア。選択肢になる値（`bgm` / `se` など）も英語で持ち、画面に出すときに日本語へ変換する
- 書き込みは、一時ファイルに書いてから置き換える（書いている途中で落ちてもファイルが壊れないように）

### 9.2 `config.json`（設定）

| 項目 | 型 | 説明 |
|---|---|---|
| `server.host` / `server.port` | string / int | `127.0.0.1` / `8765` |
| `ai.timeout_sec` | int | AIの応答を待つ秒数（60） |
| `ai.retry_on_invalid_json` | int | 応答がJSONとして読めないときの再試行回数（1） |
| `scan.extensions` | string[] | 目録に入れる形式 |
| `scan.bgm_threshold_sec` | number | この秒数以上ならBGM候補の印をつける（30） |
| `history.max_entries` | int | 履歴の最大件数（50） |
| `roots[]` | object[] | 検索対象フォルダ |
| `roots[].id` | string | 変わらない短いID（例：`r_7f3a`）。表示名を変えても目録が壊れないようにするため |
| `roots[].label` | string | 画面に出す名前 |
| `roots[].path` | string | Windowsの絶対パス |
| `roots[].enabled` | bool | 一時的に検索対象から外したいとき用 |
| `roots[].added_at` | string | 追加した日時 |

```json
{
  "version": 1,
  "server": { "host": "127.0.0.1", "port": 8765 },
  "ai": { "timeout_sec": 60, "retry_on_invalid_json": 1 },
  "scan": { "extensions": [".wav", ".mp3", ".ogg"], "bgm_threshold_sec": 30 },
  "history": { "max_entries": 50 },
  "roots": [
    {
      "id": "r_7f3a",
      "label": "Fantasy RPG Music Pack",
      "path": "D:\\GameAssets\\Audio\\FantasyRPG",
      "enabled": true,
      "added_at": "2026-10-06T21:00:00+09:00"
    }
  ]
}
```

### 9.3 `index.json`（目録）

| 項目 | 型 | 説明 |
|---|---|---|
| `scanned_at` | string | 最後にスキャンした日時 |
| `roots[]` | object[] | スキャンしたときの各フォルダの状態（`id`、`status`：`ok` か `missing`、`file_count`） |
| `files[].id` | string | `root_id` と `rel_path` から作るハッシュの先頭12文字。再スキャンしても同じファイルなら同じIDになる |
| `files[].root_id` | string | どの登録フォルダのファイルか |
| `files[].rel_path` | string | 登録フォルダからの相対パス。区切りは `/` |
| `files[].filename` | string | ファイル名 |
| `files[].folder` | string | 親フォルダの相対パス（ルート直下なら `""`） |
| `files[].ext` | string | `wav` / `mp3` / `ogg` |
| `files[].duration_sec` | number \| null | 長さ（秒、小数1桁）。読めなければ `null` |
| `files[].likely_bgm` | bool \| null | 長さが `bgm_threshold_sec` 以上なら `true`。長さが分からなければ `null` |
| `files[].size_bytes` | int | ファイルサイズ |
| `files[].mtime` | string | 最終更新日時 |
| `files[].readable` | bool | 長さを読めたかどうか。`false` なら試聴ボタンを無効にする |
| `files[].words` | string | 検索用の単語の並び（下記） |

- **`files` は1件を1行で書き出す**。AIは文字列検索で目録を探すので（6.2）、検索に当たった1行だけで、そのファイルの情報がすべて手に入るようにする。この書き方でもJSONとして正しい
- **`words`**：登録フォルダの表示名と `rel_path` を、区切り文字（`/` `_` `-` 空白など）、大文字の切れ目、数字の切れ目で単語に分解し、小文字にして空白でつなげたもの。拡張子は含めない。`Boss_Theme_Loop` や `CardDraw01` を「boss」「card draw」で検索して当たるようにするため

```json
{
  "version": 1,
  "scanned_at": "2026-10-06T21:30:00+09:00",
  "roots": [ { "id": "r_7f3a", "status": "ok", "file_count": 2 } ],
  "files": [
{"id":"3f9a1c2e7b04","root_id":"r_7f3a","rel_path":"Battle/Boss_Theme_Loop.ogg","filename":"Boss_Theme_Loop.ogg","folder":"Battle","ext":"ogg","duration_sec":95.4,"likely_bgm":true,"size_bytes":1843200,"mtime":"2025-03-02T10:15:00+09:00","readable":true,"words":"fantasy rpg music pack battle boss theme loop"},
{"id":"b81d04f9c2aa","root_id":"r_7f3a","rel_path":"SE/UI/CardDraw01.wav","filename":"CardDraw01.wav","folder":"SE/UI","ext":"wav","duration_sec":0.6,"likely_bgm":false,"size_bytes":52920,"mtime":"2025-03-02T10:15:00+09:00","readable":true,"words":"fantasy rpg music pack se ui card draw 01"}
  ]
}
```

### 9.4 AIの応答（`claude -p` が返すJSON）

| 項目 | 型 | 説明 |
|---|---|---|
| `conditions.kind` | `"bgm"` \| `"se"` \| `"ambient"` | 種類 |
| `conditions.mood` | string[] | 雰囲気（日本語。例：`["緊迫", "壮大"]`） |
| `conditions.genre` | string[] | ジャンル（日本語） |
| `conditions.tempo` | `"slow"` \| `"medium"` \| `"fast"` \| null | テンポ。SEなどで関係なければ `null` |
| `conditions.loop` | bool \| null | ループ前提かどうか |
| `local[]` | object[] | 最大10件。`{ "id": "..." }` |
| `sites[]` | object[] | 各サイト1〜3件 |
| `sites[].site_id` | string | `sites.json` のID |
| `sites[].type` | `"category"` \| `"search"` | カテゴリページへの案内か、サイト内検索への案内か |
| `sites[].category_id` | string | `type` が `category` のとき。`sites.json` のカテゴリID |
| `sites[].q` | string | `type` が `search` のときの検索語 |

- **URLは含めない**。サーバーが `sites.json` から組み立てる（6.3、6.4）

```json
{
  "conditions": { "kind": "bgm", "mood": ["緊迫", "壮大"], "genre": ["オーケストラ"], "tempo": "fast", "loop": true },
  "local": [ { "id": "3f9a1c2e7b04" } ],
  "sites": [
    { "site_id": "maou", "type": "category", "category_id": "bgm_battle" },
    { "site_id": "opentracks", "type": "search", "q": "ボス 戦闘" }
  ]
}
```

### 9.5 `history.json`（履歴）

| 項目 | 型 | 説明 |
|---|---|---|
| `entries[]` | object[] | 新しい順。`max_entries` を超えたら最も古いものから消す |
| `entries[].id` | string | 例：`h_20261006213012` |
| `entries[].created_at` | string | 検索した日時 |
| `entries[].query` | string | 入力した場面説明 |
| `entries[].elapsed_sec` | number | AIの応答にかかった秒数 |
| `entries[].conditions` | object | 9.4と同じ形 |
| `entries[].local[]` | object[] | `id` に加えて、`filename`・`rel_path`・`root_label`・`duration_sec` の**写し** |
| `entries[].sites[]` | object[] | `site_id`、`site_name`、`label`（例：「BGM > 戦闘」「検索：ボス 戦闘」）、組み立て済みの `url` |

- 写しを残すのは、再スキャンや `sites.json` の編集のあとでも過去の結果を読めるようにするため
- **エラーになった検索は残さない**

```json
{
  "version": 1,
  "entries": [
    {
      "id": "h_20261006213012",
      "created_at": "2026-10-06T21:30:12+09:00",
      "query": "ボス戦、緊迫感あり、オーケストラ系、ループ前提",
      "elapsed_sec": 12.3,
      "conditions": { "kind": "bgm", "mood": ["緊迫", "壮大"], "genre": ["オーケストラ"], "tempo": "fast", "loop": true },
      "local": [
        { "id": "3f9a1c2e7b04", "filename": "Boss_Theme_Loop.ogg", "rel_path": "Battle/Boss_Theme_Loop.ogg", "root_label": "Fantasy RPG Music Pack", "duration_sec": 95.4 }
      ],
      "sites": [
        { "site_id": "maou", "site_name": "魔王魂", "label": "BGM > 戦闘", "url": "https://maou.audio/..." }
      ]
    }
  ]
}
```

### 9.6 `sites.json`（誘導先サイト、手で編集する）

| 項目 | 型 | 説明 |
|---|---|---|
| `sites[].id` | string | `maou` / `soundeffect_lab` / `opentracks` |
| `sites[].name` | string | 表示名 |
| `sites[].top_url` | string | トップページのURL |
| `sites[].search_url` | string \| null | 検索URLの型。`{q}` に検索語（URLエンコード済み）が入る。サイト内検索がなければ `null` |
| `sites[].kinds` | string[] | このサイトで扱う種類（`bgm` / `se` / `ambient`） |
| `sites[].categories[]` | object[] | `id`、`name`、`kind`、`url` |
| `sites[].note` | string | AIへの補足（例：「ジャンル別のカテゴリが細かい」） |

```json
{
  "version": 1,
  "sites": [
    {
      "id": "maou",
      "name": "魔王魂",
      "top_url": "https://maou.audio/",
      "search_url": "https://maou.audio/?s={q}",
      "kinds": ["bgm", "se"],
      "categories": [
        { "id": "bgm_battle", "name": "BGM > 戦闘", "kind": "bgm", "url": "https://maou.audio/..." }
      ],
      "note": ""
    }
  ]
}
```

- `search_url` とカテゴリの `url` はサンプル。**実際のURLは実装時に各サイトを見て確認して書き込む**

## 10. エラー時の動き

| 状況 | 動き |
|---|---|
| Claude Codeが入っていない／未ログイン | 赤い帯で「Claude Codeにログインしてください」と、その手順を表示 |
| 利用枠の上限に達した | 「利用上限です」と表示。リセット時刻が分かればそれも表示 |
| AIの応答が60秒以内に返らない | 中断して「時間切れ」を表示し、再試行ボタンを出す |
| AIの応答がJSONとして読めない | 1回だけ自動で再試行。それでもダメならエラー表示 |
| 登録フォルダが見つからない（外付けドライブを外しているなど） | そのフォルダだけ飛ばして続行し、「○○が見つかりません」と注意表示 |
| 音声ファイルが壊れている／再生できない | その候補の▶ボタンだけ無効にする |
| 候補が0件 | 「該当なし」と表示し、入力の言い換え例を出す |

- **AIが使えないときに、AIなしの簡易検索へ切り替えることはしない**

### 安全面
- 試聴とエクスプローラーで開く機能は、**目録のIDを受け取る形**にする。パスを直接受け取らない。登録フォルダの外にあるファイルには触らない
- ローカル素材のファイルは**読み取るだけ**（書き換え・移動・削除はしない）

## 11. やらないこと

| # | やらないこと | 理由 |
|---|---|---|
| 1 | 国内サイトへのアクセス（スクレイピング、サイト内検索の自動実行、サイトマップ取得） | 規約とrobots.txtのグレーゾーンを避ける |
| 2 | 国内サイトの音源の試聴・ダウンロード・直リンク | 3サイトとも規約でNG。必ずサイト側で行う |
| 3 | 音源データをAIに渡すこと、AIの学習に使うこと | 3サイトの規約でNG |
| 4 | Freesoundなど海外サイトの検索 | 対象は国内サイトとローカル素材のみ |
| 5 | 音の中身の解析（テンポ、明るさなど） | 手間が大きい |
| 6 | AIが使えないときの簡易検索 | 結果の質が低く、保守の手間に見合わない |
| 7 | 「なぜ合うか」の説明文 | 不要 |
| 8 | お気に入り・採用管理 | 別の「素材管理ツール」になってしまう |
| 9 | 選んだ素材をUnityなどへ自動コピーする機能 | 誤コピーや上書きを防ぐ |
| 10 | 複数人での利用、ログイン、外部公開、APIキー方式 | 自分専用 |
| 11 | シーン一覧からのまとめて提案 | まずは1件ずつ |
| 12 | ローカル素材ファイルの書き換え・移動・削除 | 読み取り専用 |
| 13 | 目録の自動更新（フォルダの監視） | 手動の再スキャンのみ |

### 将来の拡張候補（今回はやらない）
- #9 指定フォルダ（UnityのAssets/Audioなど）へコピーするボタン
- #11 シーン一覧から、必要なBGM・SEをまとめて提案する
- 起動時間が気になる場合、Agent SDKでセッションをつなぎっぱなしにする方式

## 12. 規約・利用条件の確認メモ（2026-10-06時点）

### 国内サイト
| | 魔王魂 | 効果音ラボ | OpenTracks（旧DOVA-SYNDROME） |
|---|---|---|---|
| ページへのリンク・誘導 | どのページへのリンクでもOKと明記 | 禁止されていない | 記述なし（禁止されていない） |
| 音源ファイルへの直リンク | NG（mp3/wavのURLを直接書くのは不可） | NG | NG（音源ファイルに直接アクセスできる形での利用は不可） |
| サイト外での試聴・配布 | NG | NG（効果音を自由に鳴らせるアプリは再配布扱い） | NG |
| 自動取得 | 規約に記述なし。robots.txtは管理画面以外を許可 | 規約に記述なし。robots.txtはAIボットのmp3取得を禁止 | 規約に記述なし。**robots.txtは検索・タグ・ページ送りのURLへのボットアクセスを禁止** |
| AI | AI作曲システムへの組み込みNG | AI学習NG | AI学習NG |

- DOVA-SYNDROMEは**2026-09-15に「OpenTracks」（opentracks.com）へ名前が変わった**。旧URLは自動で転送される
- 出典：
  - https://maou.audio/rule/
  - https://soundeffect-lab.info/agreement/
  - https://opentracks.com/help/articles/license/
  - 各サイトの robots.txt
- 規約は変わることがあるので、`sites.json` を更新するときにあわせて確認する

### Claude Codeの利用枠で動かすこと
- 他の言語から使う方法として、`claude -p` を `--output-format json` 付きで子プロセスとして呼ぶ使い方が公式に案内されている
- 禁止されているのは「**他人向けの製品に**claude.aiのログインや利用枠を使わせること」。自分専用・自分のPCだけで使うなら、この制限にはかからない
- **将来公開する場合は、APIキー方式への切り替えが必須**
- 出典：https://code.claude.com/docs/en/agent-sdk/overview

## 13. 決定の経緯（質問と回答）

| # | 論点 | 決定 |
|---|---|---|
| Q1 | 誰が使うか | 自分ひとり |
| Q2 | 入力 | 自然文で場面を説明する |
| Q3 | 取得元 | 国内フリー素材サイト＋ローカル素材 |
| Q4 | 国内サイトの扱い | ツールはアクセスしない。リンクの提案のみ |
| Q5 | AIの動かし方 | `claude -p` をClaude Codeの利用枠で呼ぶ |
| Q6 | 画面 | ローカルWebアプリ |
| Q7 | ローカル素材の検索 | フォルダ登録＋目録＋手動の再スキャン |
| Q8 | 出力 | 読み取った条件＋ローカル候補＋サイト誘導。説明文なし |
| Q9 | 保存 | 設定＋目録＋履歴（直近50件）をJSONで |
| Q10 | エラー時 | 10章の表のとおり。AIなしの簡易検索への切り替えはしない |
| Q11 | 目録をAIにどう見せるか | 読み取り専用の道具で、AIが自分で検索する |
| Q12 | 言語 | Python（FastAPI） |
| Q13 | 対象形式 | wav / mp3 / ogg。30秒以上をBGM候補とする |
| Q14 | サイト一覧 | `sites.json` を手で編集する |
| Q15 | やらないこと | 11章の13項目 |
| Q16 | 起動 | `start.bat` をダブルクリック |
| 追加 | 技術スタックの再検討 | 3候補を比べたうえでPython ＋ FastAPI ＋ 素のHTML/JSのまま（7.1） |
| 追加 | データ構造 | 9章のとおり。目録は1件1行、AIにURLを作らせない、履歴に写しを残す |
