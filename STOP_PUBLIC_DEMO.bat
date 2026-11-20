@echo off
title FormWise AI – Stop Demo
echo =====================================================================
echo          FormWise AI – Stopping Public Demo
echo =====================================================================
echo.

echo Stopping Flask backend...
taskkill /FI "WINDOWTITLE eq FormWise AI - Backend*" /T /F >nul 2>&1

echo Stopping ngrok tunnel...
taskkill /FI "WINDOWTITLE eq FormWise AI - ngrok Tunnel*" /T /F >nul 2>&1

:: Also kill any lingering python / ngrok processes on port 5000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo [DONE] All FormWise AI demo servers stopped.
echo Your public link is no longer active.
echo.
pause
