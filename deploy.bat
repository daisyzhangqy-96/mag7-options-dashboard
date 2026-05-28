@echo off
REM ============================================================
REM 一键生成数据 + 推送到 GitHub Pages
REM 运行前请先执行一次性初始化（见 README 「云端部署」章节）
REM ============================================================

cd /d "%~dp0"

echo [1/3] 调富途API生成 data.json ...
python generate.py
if errorlevel 1 (
    echo 数据生成失败，已中止
    pause
    exit /b 1
)

echo.
echo [2/3] 提交到 git ...
git add data.json index.html
git commit -m "refresh data %date% %time%"

echo.
echo [3/3] 推送到 GitHub Pages ...
git push

echo.
echo 完成！约 1 分钟后同事可访问最新数据。
echo 访问地址见 README.md 「云端部署」章节
pause
