@echo off
chcp 65001 >nul
title 三国知识库 - 启动中...

echo ========================================
echo   三国历史知识库 - 一键启动
echo ========================================
echo.

:: 启动后端
echo [1/3] 启动后端服务 (端口 8000)...
start "后端服务" cmd /k "cd /d %~dp0backend && uv run uvicorn app.main:app --reload --port 8000"
timeout /t 3 /nobreak >nul

:: 启动前端
echo [2/3] 启动前端服务 (端口 5173)...
start "前端服务" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 3 /nobreak >nul

:: 启动 Cloudflare 命名隧道（配置文件在 ~/.cloudflared/config.yml）
echo [3/3] 启动公网隧道 (jinligame.fun)...
start "Cloudflare隧道" cmd /k "tools\cloudflare\cloudflared.exe tunnel run || echo 隧道启动失败，但本地访问仍可用"

echo.
echo ========================================
echo   服务已启动！
echo ========================================
echo.
echo   本地访问: http://localhost:5173
echo   公网访问: https://jinligame.fun
echo.
echo   关闭各窗口即可停止对应服务
echo ========================================
pause
