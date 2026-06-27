@echo off
chcp 65001 >nul
title Three Kingdoms Knowledge Base

echo ========================================
echo   Three Kingdoms - Quick Start
echo ========================================
echo.

set "PATH=%USERPROFILE%\.local\bin;%PATH%"

echo [1/3] Starting backend (port 8000)...
start "Backend" cmd /k "cd /d %~dp0backend && uv run uvicorn app.main:app --reload --port 8000"

echo       Waiting for backend...
set /a count=0
:wait_loop
timeout /t 2 /nobreak >nul
set /a count+=1
curl -s http://localhost:8000/docs >nul 2>&1
if %errorlevel%==0 (
    echo       Backend ready!
    goto :backend_ready
)
if %count% geq 15 (
    echo       Backend slow, continue anyway...
    goto :backend_ready
)
goto :wait_loop

:backend_ready

echo [2/3] Starting frontend (port 5173)...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 3 /nobreak >nul

echo [3/3] Starting Cloudflare tunnel...
start "Cloudflare" cmd /k "tools\cloudflare\cloudflared.exe tunnel run"

echo.
echo ========================================
echo   All services started!
echo ========================================
echo.
echo   Local:  http://localhost:5173
echo   Public: https://jinligame.fun
echo.
echo   Close each window to stop that service
echo ========================================
pause
