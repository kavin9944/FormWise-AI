@echo off
setlocal EnableDelayedExpansion
title FormWise AI - Public Demo Launcher
chcp 65001 >nul 2>&1

echo =====================================================================
echo             FormWise AI - Smart Form Filling Assistant
echo                   ONE-CLICK PUBLIC DEMO LAUNCHER
echo =====================================================================
echo.

:: 1. Check Python virtual environment
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please run setup.bat first to set up FormWise AI dependencies.
    echo.
    pause
    exit /b 1
)

:: 2. Check .env file
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [NOTICE] Created .env file from .env.example.
    )
)

:: 3. Ensure uploads folder exists
if not exist "uploads" mkdir uploads

:: 4. Locate ngrok executable
set "NGROK_BIN="
if exist "%~dp0ngrok.exe" (
    set "NGROK_BIN=%~dp0ngrok.exe"
) else (
    where ngrok >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set "NGROK_BIN=ngrok"
    ) else (
        echo [INFO] Downloading ngrok for Windows...
        powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip' -OutFile 'ngrok.zip'; Expand-Archive 'ngrok.zip' -DestinationPath '.' -Force; Remove-Item 'ngrok.zip' -Force"
        if exist "%~dp0ngrok.exe" (
            set "NGROK_BIN=%~dp0ngrok.exe"
            echo [OK] ngrok installed successfully.
        ) else (
            echo [ERROR] Could not download ngrok automatically.
            echo Please download ngrok from https://ngrok.com/download and place ngrok.exe in this folder.
            pause
            exit /b 1
        )
    )
)

:: 5. Check if ngrok authtoken is configured
"!NGROK_BIN!" config check >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo =====================================================================
    echo            FIRST-TIME SETUP: FREE NGROK AUTHTOKEN NEEDED
    echo =====================================================================
    echo  ngrok creates your free, secure public HTTPS website link.
    echo.
    echo  1. Opening https://dashboard.ngrok.com/signup in your browser...
    echo  2. Sign up or log in (100%% free).
    echo  3. Copy your authtoken from: https://dashboard.ngrok.com/get-started/your-authtoken
    echo =====================================================================
    echo.
    start https://dashboard.ngrok.com/get-started/your-authtoken
    set /p "USER_TOKEN=Paste your ngrok authtoken here and press Enter: "
    if "!USER_TOKEN!"=="" (
        echo [ERROR] No authtoken entered. Cannot start public demo.
        pause
        exit /b 1
    )
    "!NGROK_BIN!" config add-authtoken !USER_TOKEN!
    echo [OK] Authtoken saved successfully!
    echo.
)

:: 6. Clean up any previous lingering processes on port 5000 or ngrok
taskkill /IM ngrok.exe /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FormWise AI Backend*" /T /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: 7. Start Flask backend on port 5000 (serves both Frontend and API)
echo [1/3] Starting FormWise AI backend on port 5000...
start "FormWise AI Backend" /min cmd /c "call venv\Scripts\activate.bat && set FLASK_HOST=0.0.0.0 && set PORT=5000 && set FLASK_DEBUG=0 && cd backend && python app.py"

:: Wait 3 seconds for backend to start
timeout /t 3 /nobreak >nul

:: 8. Start ngrok tunnel on port 5000
echo [2/3] Starting secure public HTTPS tunnel...
start "FormWise AI ngrok Tunnel" /min cmd /c ""!NGROK_BIN!" http 5000"

:: 9. Query ngrok API for the public URL (retry loop up to 15 seconds)
echo [3/3] Generating your public link...
set "PUBLIC_URL="
for /L %%i in (1,1,15) do (
    if "!PUBLIC_URL!"=="" (
        timeout /t 1 /nobreak >nul
        for /f "delims=" %%u in ('powershell -NoProfile -Command "try { $res = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2; ($res.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1).public_url } catch {}"') do (
            set "PUBLIC_URL=%%u"
        )
    )
)

echo.
if not "!PUBLIC_URL!"=="" (
    echo =====================================================================
    echo         SUCCESS! YOUR FORMWISE AI PUBLIC LINK IS READY
    echo =====================================================================
    echo.
    echo   PUBLIC LINK:  !PUBLIC_URL!
    echo.
    echo   (This link has been automatically copied to your clipboard)
    echo =====================================================================
    echo.
    echo  SHARE THIS LINK WITH YOUR TEAMMATES:
    echo   - They can open it on their laptops, tablets, or phones.
    echo   - They do NOT need to install Python, Tesseract, or anything.
    echo   - If ngrok shows a 'Visit Site' button, they just click it once.
    echo.
    echo  IMPORTANT:
    echo   - Keep this window OPEN while teammates are using the site.
    echo   - Double-click STOP_PUBLIC_DEMO.bat when you want to stop.
    echo =====================================================================
    
    :: Copy to clipboard
    echo|set /p="!PUBLIC_URL!" | clip 2>nul
    
    :: Open in browser
    start "" "!PUBLIC_URL!"
) else (
    echo =====================================================================
    echo [NOTICE] ngrok tunnel started!
    echo Check the ngrok dashboard at: http://127.0.0.1:4040 to see your link.
    echo Or open the ngrok window in your taskbar.
    echo =====================================================================
    start http://127.0.0.1:4040
)

echo.
echo Press any key to STOP the demo and close all servers...
pause >nul

:: Stop servers
echo.
echo Stopping FormWise AI public demo...
taskkill /IM ngrok.exe /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FormWise AI Backend*" /T /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo [OK] Demo stopped cleanly.
timeout /t 2 /nobreak >nul
