@echo off
REM Set the title of the command prompt window
title Run FA11y

REM Install the required Python packages from requirements.txt
echo Installing required Python packages...
pip install -r requirements.txt

REM Check if pip command was successful
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Failed to install some or all requirements. Please check the error messages above.
    echo.
    pause
    exit /b
)

REM Run the FA11y.py script
echo Running FA11y.py...
python FA11y.py

REM Check if the Python script command was successful
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FA11y.py encountered an issue or has terminated unexpectedly.
    echo.
) else (
    echo.
    echo FA11y.py has launched successfully.
    echo.
)

REM Prevent the terminal from closing
echo Press any key to close this window...
pause > nul