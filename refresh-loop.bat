@echo off
REM 后台定时刷新数据（每 10 分钟）
cd /d "%~dp0"
:loop
timeout /t 600 /nobreak >nul
echo [%date% %time%] refreshing data.json ...
python generate.py >> refresh.log 2>&1
goto loop
