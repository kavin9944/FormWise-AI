@echo off
setlocal
title FormWise AI – Application Launcher

echo =====================================================================
echo                 Starting FormWise AI System
echo =====================================================================
echo.

:: 1. Verify virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run setup.bat first to install the required dependencies.
    echo.
    pause
    exit /b 1
)

:: 2. Verify .env file exists
if not exist ".env" (
    echo [WARNING] No .env file found.
    echo Creating .env from .env.example...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo Please open .env and add your GEMINI_API_KEY.
        echo.
    )
)

:: 3. Create uploads directory if not present
if not exist "uploads" (
    mkdir uploads
)

echo [1/3] Activating virtual environment...
call venv\Scripts\activate.bat

echo [2/3] Launching Flask Backend Server on port 5000...
start "FormWise AI - Backend Server (Port 5000)" cmd /k "call venv\Scripts\activate.bat && cd backend && python app.py"

:: Give backend 2 seconds to initialize
timeout /t 2 /nobreak >nul

echo [3/3] Launching Frontend HTTP Server on port 8000...
start "FormWise AI - Frontend Server (Port 8000)" cmd /k "cd frontend && python -m http.server 8000"

:: Give frontend 1 second to bind
timeout /t 1 /nobreak >nul

echo.
echo =====================================================================
echo [SUCCESS] Both servers are now running!
echo   - Frontend: http://localhost:8000
echo   - Backend:  http://127.0.0.1:5000
echo.
echo Opening FormWise AI in your default web browser...
echo =====================================================================
start http://localhost:8000/index.html

echo.
echo Press any key to stop all FormWise AI servers and close windows...
pause >nul

echo Stopping servers...
taskkill /FI "WINDOWTITLE eq FormWise AI - Backend Server*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FormWise AI - Frontend Server*" /T /F >nul 2>&1

echo.
echo FormWise AI has stopped cleanly.
timeout /t 2 /nobreak >nul
