@echo off
setlocal EnableExtensions
chcp 65001 >nul

echo ================================================================
echo   Delta Force: Black Hawk Down + Team Sabre - Thai Mod Installer
echo ================================================================
echo.

set "MOD_DIR=%~dp0ModFiles"
if not exist "%MOD_DIR%\d3d8.dll" (
    echo [ERROR] ModFiles folder not found next to this script.
    pause
    exit /b 1
)

set "GAME_DIR="
if exist "%~dp0..\dfbhd.exe" if exist "%~dp0..\localres.pff" set "GAME_DIR=%~dp0.."
if not defined GAME_DIR (
    for %%D in (
        "C:\GOG Games\Delta Force Black Hawk Down"
        "C:\Program Files (x86)\Steam\steamapps\common\Delta Force Black Hawk Down"
        "C:\Program Files\NovaLogic\Delta Force Black Hawk Down"
        "C:\Program Files (x86)\NovaLogic\Delta Force Black Hawk Down"
    ) do (
        if not defined GAME_DIR if exist "%%~D\dfbhd.exe" set "GAME_DIR=%%~D"
    )
)

if defined GAME_DIR (
    echo Found game folder: "%GAME_DIR%"
    set /p "ANS=Install Thai Mod to this folder? [Y/N]: "
    if /i not "%ANS%"=="Y" set "GAME_DIR="
)

if not defined GAME_DIR (
    echo.
    echo Drag and drop your Delta Force Black Hawk Down folder here, then press Enter:
    set /p "GAME_DIR=Game folder path: "
)

set "GAME_DIR=%GAME_DIR:"=%"
if "%GAME_DIR:~-1%"=="\" set "GAME_DIR=%GAME_DIR:~0,-1%"

if not exist "%GAME_DIR%\dfbhd.exe" (
    echo [ERROR] dfbhd.exe not found in "%GAME_DIR%"
    pause
    exit /b 1
)

set "BACKUP=%GAME_DIR%\Backup_Original"
if not exist "%BACKUP%" mkdir "%BACKUP%"

echo.
echo [1/2] Backing up original files to "%BACKUP%"...
for %%F in (dfbhd.exe d3d8.dll localres.pff EXP1.pff resource.pff dgVoodoo.conf) do (
    if exist "%GAME_DIR%\%%F" if not exist "%BACKUP%\%%F" (
        copy /Y "%GAME_DIR%\%%F" "%BACKUP%\%%F" >nul
    )
)

echo [2/2] Installing Thai Mod files...
xcopy "%MOD_DIR%\*" "%GAME_DIR%\" /E /Y /I >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy mod files. Make sure the game is closed and run as Administrator if needed.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo   Thai Mod installed successfully!
echo   Launch the game via dfbhd.exe or your GOG/Desktop shortcut.
echo ================================================================
pause
