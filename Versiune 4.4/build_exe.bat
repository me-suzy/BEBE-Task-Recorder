@echo off
set "APP_VERSION=4.4"
set "OUTPUT_EXE=dist\BEBE_Task_Recorder.exe"
set "VERSIONED_EXE=dist\Bebe - Task Recorder - Version %APP_VERSION%.exe"
echo ========================================
echo BEBE Task Recorder - Build Executable v%APP_VERSION%
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

REM Creeaza folderul pentru build (folosind path scurt pentru a evita probleme)
set "TEMP_BUILD_DIR=C:\Temp\BEBE_Build"
set "ORIGINAL_DIR=%CD%"

echo [INFO] Folosesc folder temporar pentru build: %TEMP_BUILD_DIR%
if exist "%TEMP_BUILD_DIR%" rmdir /S /Q "%TEMP_BUILD_DIR%"
mkdir "%TEMP_BUILD_DIR%"

REM Copiaza fisierele necesare in folder temporar
echo [INFO] Copiez fisierele in folder temporar...
xcopy /Y /Q "bebe_gui.py" "%TEMP_BUILD_DIR%\" >nul
xcopy /Y /Q "i18n.py" "%TEMP_BUILD_DIR%\" >nul
if exist "BEBE_Task_Recorder.spec" xcopy /Y /Q "BEBE_Task_Recorder.spec" "%TEMP_BUILD_DIR%\" >nul
if exist "admin_manifest.xml" xcopy /Y /Q "admin_manifest.xml" "%TEMP_BUILD_DIR%\" >nul
if exist "tasks" xcopy /E /I /Y /Q "tasks" "%TEMP_BUILD_DIR%\tasks" >nul
if exist "upx-5.0.2-win64" xcopy /E /I /Y /Q "upx-5.0.2-win64" "%TEMP_BUILD_DIR%\upx-5.0.2-win64" >nul

cd /D "%TEMP_BUILD_DIR%"

if not exist "build" mkdir build
if not exist "dist" mkdir dist

echo [INFO] Construiesc executabilul cu privilegii de administrator...
echo.

REM Verifica daca UPX este disponibil
if exist "upx-5.0.2-win64\upx.exe" (
    echo [OK] UPX gasit - executabilul va fi comprimat!
) else (
    echo [INFO] UPX nu este gasit - executabilul va fi mai mare
)

REM Verifica daca exista .spec file
if exist "BEBE_Task_Recorder.spec" (
    echo [INFO] Folosesc fisierul .spec cu manifest de administrator si UPX...
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
    cd /D "%ORIGINAL_DIR%"
    pause
    exit /b 1
)

REM Copiaza executabilul inapoi in folderul original
echo.
echo [INFO] Copiez executabilul in folderul proiectului...
cd /D "%ORIGINAL_DIR%"

if not exist "dist" mkdir dist

if exist "%TEMP_BUILD_DIR%\dist\BEBE_Task_Recorder.exe" (
    REM Copiaza direct cu numele versiunii
    copy /Y "%TEMP_BUILD_DIR%\dist\BEBE_Task_Recorder.exe" "dist\Bebe - Task Recorder - Version %APP_VERSION%.exe" >nul
    echo [OK] Copiat: dist\Bebe - Task Recorder - Version %APP_VERSION%.exe
) else (
    echo [EROARE] Executabilul nu a fost gasit!
    pause
    exit /b 1
)

REM Curata folderul temporar
echo [INFO] Curatare folder temporar...
if exist "%TEMP_BUILD_DIR%" rmdir /S /Q "%TEMP_BUILD_DIR%"

echo.
echo ========================================
echo BUILD COMPLET!
echo ========================================
echo.
echo Executabilul se afla in:
echo   %ORIGINAL_DIR%\dist\BEBE_Task_Recorder.exe
echo   %ORIGINAL_DIR%\dist\Bebe - Task Recorder - Version %APP_VERSION%.exe
echo.
echo IMPORTANT:
echo - Acest .exe va cere automat privilegii de administrator!
echo - Functia 'Save Task as EXE' functioneaza DOAR din 'python bebe_gui.py'
echo - Executabilul poate salva task-uri ca JSON si poate reda task-uri
echo.
pause

