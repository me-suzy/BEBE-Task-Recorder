@echo off
echo ========================================
echo BEBE Task Recorder - Build Executable
echo ========================================
echo.

REM Verifica daca PyInstaller este instalat
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] Instalez PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo [EROARE] Nu am putut instala PyInstaller!
        pause
        exit /b 1
    )
)

echo [OK] PyInstaller instalat
echo.

REM Creeaza folderul pentru build
if not exist "build" mkdir build
if not exist "dist" mkdir dist

echo [INFO] Construiesc executabilul cu privilegii de administrator...
echo.

REM Verifica daca exista .spec file
if exist "BEBE_Task_Recorder.spec" (
    echo [INFO] Folosesc fisierul .spec cu manifest de administrator...
    pyinstaller --clean BEBE_Task_Recorder.spec
) else (
    echo [INFO] Creez executabil cu privilegii de administrator...
    pyinstaller --onefile ^
        --windowed ^
        --name "BEBE_Task_Recorder" ^
        --add-data "tasks;tasks" ^
        --uac-admin ^
        --clean ^
        bebe_gui.py
)

if errorlevel 1 (
    echo.
    echo [EROARE] Build esuat!
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD COMPLET!
echo ========================================
echo.
echo Executabilul se afla in: dist\BEBE_Task_Recorder.exe
echo.
echo Acest .exe va cere automat privilegii de administrator!
echo.
pause

