@echo off
REM ============================================================
REM 一键生成可分享的单文件 share.html
REM 产物：share.html，双击或微信/邮件发送给同事即可，无需联网
REM ============================================================

cd /d "%~dp0"

echo [1/2] 调富途API生成 data.json ...
python generate.py
if errorlevel 1 (
    echo 数据生成失败，已中止
    pause
    exit /b 1
)

echo.
echo [2/2] 打包成 share.html ...
python bundle.py
if errorlevel 1 (
    echo 打包失败
    pause
    exit /b 1
)

echo.
echo 完成！share.html 在当前目录，双击可打开，可直接发同事。
pause
