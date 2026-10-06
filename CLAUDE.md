# Audio Finder

場面の説明（自然文）から、手持ちのBGM・SEと国内フリー素材サイトの探し先を提案する、自分専用のローカルツール。

- 仕様：[SPEC.md](SPEC.md)（何を作るか・やらないこと）
- 計画：[PLAN.md](PLAN.md)（作業の順番・進み具合）
- 作業前に両方を読むこと

## 技術スタック
Python 3.12+ / FastAPI + uvicorn / mutagen / 画面は素のHTML・CSS・JS（ビルドなし・外部ライブラリなし）/ AIは `claude -p` / テストは pytest
データ構造は SPEC.md 9章に従う（項目名・型を勝手に変えない）
依存は `requirements.txt`（動かす用）と `requirements-dev.txt`（テスト用）に分け、バージョンは `==` で固定する

## 実行方法
- `start.bat` をダブルクリック（初回は `.venv` 作成と依存のインストールも行う）→ `http://127.0.0.1:8765` が開く
- 前提：Python 3.12以上と、ログイン済みの Claude Code

## テスト方法
- 自動：初回だけ `.venv\Scripts\python -m pip install -r requirements-dev.txt`、その後 `.venv\Scripts\python -m pytest`（`claude -p` は偽物に差し替える。本物は呼ばない）
- 手動：画面操作・試聴・エクスプローラー連携・本物の `claude -p` との接続は、起動して実際に確かめる

## 作業ルール
- 作業は PLAN.md のタスクごとに1本の feature ブランチで行う（例：`feature/task2-settings`）。master では直接作業しない
- 1タスク終わるごとに動作確認してからコミットする
- コミットメッセージは日本語で「何をしたか」を1行で書く
- push とブランチ削除は、必ず実行前にユーザーに確認する
- SPEC.md にないことは勝手に実装しない。必要だと思ったら提案する
