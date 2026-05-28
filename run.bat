@echo off
REM ============================================================
REM MAG7 期权策略雷达 - 启动脚本
REM 1. 立即生成一次数据
REM 2. 启动本地HTTP服务（http://localhost:8765）
REM 3. 在后台每 10 分钟刷新一次 data.json
REM ============================================================

cd /d "%~dp0"

echo [1/3] 首次生成数据...
python generate.py

echo.
echo [2/3] 启动后台定时刷新（每10分钟）...
start "options-refresh" /min cmd /c refresh-loop.bat

echo.
echo [3/3] 启动本地 HTTP 服务 http://localhost:8765 ...
start "" http://localhost:8765/index.html
python server.py
