@echo off
REM Quick launcher script for Motor Control GUI (Windows)

echo ======================================
echo   SciGlob Motor Control Launcher
echo ======================================
echo.

REM Check if sciglob is installed
python -c "import sciglob" 2>nul
if errorlevel 1 (
    echo WARNING: SciGlob library not found!
    echo Installing sciglob...
    pip install sciglob
    echo.
)

echo Starting Motor Control GUI...
python motor_control_gui.py
pause
