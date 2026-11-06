@echo off
setlocal
cd /d "%~dp0"
title PDF to Box - 3ds Max Packaging Builder

python -c "import PyQt6, pymupdf, cv2, PIL, win32gui" >nul 2>&1
if errorlevel 1 (
    echo [NOTICE] Required dependencies are missing.
    echo Running setup.bat to install required packages...
    echo.
    call setup.bat
    echo.
)

python main.py
if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
