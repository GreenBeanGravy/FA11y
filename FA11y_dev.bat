@echo off
REM FA11y Developer Mode Launcher
REM
REM This script launches FA11y developer tools
REM Usage: FA11y_dev.bat [tool_name]
REM Example: FA11y_dev.bat pixel_inspector

echo FA11y Developer Mode
echo ====================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

REM Run the dev mode launcher
if "%1"=="" (
    python FA11y_dev.py pixel_inspector
) else (
    python FA11y_dev.py %*
)

REM Pause if there was an error
if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
)
