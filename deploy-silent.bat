@echo off
REM ============================================================
REM Silent deploy (called by Windows Task Scheduler, no pause)
REM Logs to deploy.log
REM ============================================================

setlocal enabledelayedexpansion
set "OPEND_DIR=C:\Users\daisyzhang\AppData\Roaming\Futu_OpenD"
set "OPEND_EXE=%OPEND_DIR%\Futu_OpenD.exe"
set "OPEND_NAME=Futu_OpenD.exe"
set "OPEND_PORT=11111"

cd /d "%~dp0"

echo [%date% %time%] === auto deploy start === >> deploy.log

REM ---- 1. Ensure Futu_OpenD is running ----
tasklist /FI "IMAGENAME eq %OPEND_NAME%" 2>nul | find /I "%OPEND_NAME%" >nul
if errorlevel 1 (
    echo [%date% %time%] %OPEND_NAME% not running, starting... >> deploy.log
    if not exist "%OPEND_EXE%" (
        echo [%date% %time%] ERROR: OpenD exe not found at %OPEND_EXE% >> deploy.log
        exit /b 2
    )
    start "" /D "%OPEND_DIR%" "%OPEND_EXE%"

    REM ---- 2. Wait up to 60s for OpenD port to listen ----
    REM Use powershell Start-Sleep (timeout/ping unreliable under schtasks non-interactive)
    set "READY="
    for /L %%i in (1,1,30) do (
        if not defined READY (
            powershell -NoProfile -Command "Start-Sleep -Seconds 2"
            netstat -an | findstr /C:":%OPEND_PORT% " | findstr /I "LISTENING" >nul
            if not errorlevel 1 set "READY=1"
        )
    )
    if not defined READY (
        echo [%date% %time%] ERROR: OpenD port %OPEND_PORT% not listening after 60s, abort >> deploy.log
        exit /b 3
    )
    echo [%date% %time%] OpenD ready on port %OPEND_PORT% >> deploy.log
) else (
    echo [%date% %time%] %OPEND_NAME% already running >> deploy.log
)

python generate.py >> deploy.log 2>&1
if errorlevel 1 (
    echo [%date% %time%] generate.py failed, abort >> deploy.log
    exit /b 1
)

git add data.json index.html >> deploy.log 2>&1
git commit -m "auto refresh %date% %time%" >> deploy.log 2>&1
git push >> deploy.log 2>&1

echo [%date% %time%] === auto deploy done === >> deploy.log
endlocal
