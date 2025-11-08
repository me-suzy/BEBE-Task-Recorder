@echo off
echo ========================================
echo BEBE Task Recorder - Build Executable
echo ========================================
echo.

cd /d "%~dp0"

REM Ruleaza scriptul Python de build
python build_exe_advanced.py

if errorlevel 1 (
    echo.
    echo [EROARE] Build esuat!
    pause
    exit /b 1
)

pause

