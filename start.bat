@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo 初回セットアップ中です。ライブラリをインストールしています...
    py -3 -m venv .venv
    if errorlevel 1 python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo Python が見つかりません。Python 3.12 以上をインストールしてください。
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ライブラリのインストールに失敗しました。ネット接続を確認して、もう一度起動してください。
        rmdir /s /q .venv
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m app
if errorlevel 1 pause
