@echo off
setlocal enabledelayedexpansion
title FormWise AI – Automated Setup

echo =====================================================================
echo           FormWise AI – Teammate Environment Setup
echo =====================================================================
echo.

:: 1. Check Python installation
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    py --version >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Python is not installed or not added to your system PATH.
        echo.
        echo Please install Python 3.10, 3.11, or 3.12 from:
        echo    https://www.python.org/downloads/
        echo.
        echo IMPORTANT: Check the box "Add Python to PATH" during installation.
        echo After installing, restart this script.
        echo =====================================================================
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py
    )
) else (
    set PYTHON_CMD=python
)

for /f "tokens=*" %%i in ('%PYTHON_CMD% --version') do set PY_VER=%%i
echo       Detected %PY_VER%
echo.

:: 2. Create virtual environment
echo [2/5] Creating Python virtual environment (venv)...
if not exist "venv\Scripts\activate.bat" (
    %PYTHON_CMD% -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo Please ensure you have the 'venv' package installed.
        pause
        exit /b 1
    )
    echo       Virtual environment created successfully.
) else (
    echo       Virtual environment already exists in .\venv.
)
echo.

:: 3. Configure environment file (.env)
echo [3/5] Checking environment configuration...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo       Created .env from .env.example.
        echo       [ACTION REQUIRED] Open .env and insert your GEMINI_API_KEY.
    ) else (
        echo [WARNING] .env.example file not found.
    )
) else (
    echo       .env file already exists.
)
echo.

:: 4. Install dependencies
echo [4/5] Installing Python dependencies from requirements.txt...
echo       This may take 1-3 minutes depending on your internet connection...
call venv\Scripts\activate.bat

python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Failed to install all packages from requirements.txt.
    echo Please check your internet connection or install build tools if prompted.
    pause
    exit /b 1
)
echo       All Python dependencies installed successfully.
echo.

:: 5. System checks (Tesseract and Firebase)
echo [5/5] Checking optional external components...

:: Check Tesseract
where tesseract >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo       [OK] Tesseract OCR detected in system PATH.
) else if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo       [OK] Tesseract OCR detected at default path.
) else (
    echo       [NOTE] Tesseract OCR not found.
    echo              Native digital PDFs will work 100%% fine!
    echo              For scanned paper forms, download from:
    echo              https://github.com/UB-Mannheim/tesseract/wiki
)

:: Check Firebase service account
if exist "backend\serviceAccountKey.json" (
    echo       [OK] Firebase serviceAccountKey.json found in backend\.
) else (
    echo       [NOTE] backend\serviceAccountKey.json not yet placed.
    echo              If you have your team Firebase key, place it in:
    echo              backend\serviceAccountKey.json
)

echo.
echo =====================================================================
echo [SUCCESS] FormWise AI setup is complete!
echo.
echo Next steps:
echo   1. Edit .env and paste your GEMINI_API_KEY.
echo   2. Double-click start.bat to launch FormWise AI!
echo =====================================================================
echo.
pause
