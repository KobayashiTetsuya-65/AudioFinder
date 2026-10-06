@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
rem 最後にインストールしたときの requirements.txt の写し。中身が変わったら入れ直す目印にする
set "INSTALLED=.venv\requirements.installed.txt"

if not exist "%PY%" (
    echo 初回セットアップ中です。ライブラリをインストールしています...
    py -3 -m venv .venv
    if errorlevel 1 python -m venv .venv
    if not exist "%PY%" (
        echo Python が見つかりません。Python 3.12 以上をインストールしてください。
        pause
        exit /b 1
    )
)

rem Python 3.12 以上か確かめる（古いと、起動したときにわかりにくいエラーになるため）
"%PY%" -c "import sys; sys.exit(sys.version_info < (3, 12))"
if errorlevel 1 (
    for /f "delims=" %%v in ('"%PY%" --version') do echo .venv の Python が古すぎます（%%v）。Python 3.12 以上が必要です。
    echo Python 3.12 以上をインストールしてから、もう一度起動してください。
    rmdir /s /q .venv
    pause
    exit /b 1
)

rem 初回と、requirements.txt が前回のインストールから変わったときだけ入れる
fc /b requirements.txt "%INSTALLED%" >nul 2>&1
if errorlevel 1 (
    echo ライブラリをインストールしています...
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ライブラリのインストールに失敗しました。ネット接続を確認して、もう一度起動してください。
        rmdir /s /q .venv
        pause
        exit /b 1
    )
    copy /y requirements.txt "%INSTALLED%" >nul
)

"%PY%" -m app
if errorlevel 1 pause
