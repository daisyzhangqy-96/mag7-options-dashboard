@echo off
REM ============================================================
REM 静默版 deploy（供 Windows 计划任务调用，无 pause）
REM 日志写入 deploy.log
REM ============================================================

cd /d "%~dp0"

echo [%date% %time%] === auto deploy start === >> deploy.log

python generate.py >> deploy.log 2>&1
if errorlevel 1 (
    echo [%date% %time%] generate.py failed, abort >> deploy.log
    exit /b 1
)

git add data.json index.html >> deploy.log 2>&1
git commit -m "auto refresh %date% %time%" >> deploy.log 2>&1
git push >> deploy.log 2>&1

echo [%date% %time%] === auto deploy done === >> deploy.log
