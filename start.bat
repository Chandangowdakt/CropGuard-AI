@echo off
title CropGuard AI Launcher
color 0A

echo.
echo  ========================================
echo   CropGuard AI is starting...
echo  ========================================
echo.

cd /d "%~dp0"

REM Window 1 — FastAPI backend (port 8001)
start "CropGuard Backend" cmd /k "cd /d "%~dp0backend" && echo Starting CropGuard API... && python main.py"

REM Window 2 — Frontend static server (port 5500)
start "CropGuard Frontend" cmd /k "cd /d "%~dp0frontend" && echo Serving frontend on port 5500... && python -m http.server 5500"

echo  Waiting 3 seconds for backend to start...
timeout /t 3 /nobreak >nul

echo  Opening browser tabs...
start "" "http://localhost:8001"
start "" "http://localhost:5500"

echo.
echo  CropGuard AI is running!
echo    Backend API : http://localhost:8001
echo    API Docs    : http://localhost:8001/docs
echo    Frontend UI : http://localhost:5500
echo.
echo  Login: admin@cropguard.ai / admin123
echo.
echo  Close the Backend and Frontend windows to stop the servers.
echo.
pause
