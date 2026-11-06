@echo off
setlocal
cd /d "%~dp0"
title PDF to Box - Environment Setup

echo ===================================================
echo   PDF to Box - Dependency ^& Environment Setup
echo ===================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in your system PATH!
    echo Please install Python 3.10 or newer from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [1/3] Python installation detected:
python --version
echo.

:: 2. Upgrade pip
echo [2/3] Upgrading pip...
python -m pip install --upgrade pip
echo.

:: 3. Install required packages
echo [3/3] Installing required packages from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Package installation encountered an issue!
    echo Please check your internet connection and python permissions.
    echo.
    pause
    exit /b 1
)

:: 4. Verify imports
echo.
echo Verifying core dependencies...
python -c "import PyQt6, pymupdf, cv2, numpy, PIL, win32gui; print('  [OK] PyQt6, PyMuPDF, OpenCV, NumPy, Pillow, and pywin32 verified successfully!')"
if errorlevel 1 (
    echo [WARNING] One or more packages could not be imported cleanly.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   Setup completed successfully!
echo   You can now launch the application via run_app.bat
echo ===================================================
echo.
pause
