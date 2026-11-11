@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0"
if "%~1"=="" (
    python -m src.main
) else (
    python -m src.main %*
)
set APP_EXIT=%ERRORLEVEL%
popd
exit /b %APP_EXIT%
