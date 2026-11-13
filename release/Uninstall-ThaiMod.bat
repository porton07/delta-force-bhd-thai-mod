@echo off
setlocal EnableExtensions
chcp 65001 >nul

echo ================================================================
echo   Delta Force: Black Hawk Down - Restore Original English Files
echo ================================================================
echo.

set "GAME_DIR="
if exist "%~dp0..\dfbhd.exe" set "GAME_DIR=%~dp0.."
if not defined GAME_DIR (
    echo Drag and drop your Delta Force Black Hawk Down folder here, then press Enter:
    set /p "GAME_DIR=Game folder path: "
)

set "GAME_DIR=%GAME_DIR:"=%"
if "%GAME_DIR:~-1%"=="\" set "GAME_DIR=%GAME_DIR:~0,-1%"

set "BACKUP=%GAME_DIR%\Backup_Original"
if not exist "%BACKUP%\localres.pff" (
    echo [ERROR] Backup_Original folder not found in "%GAME_DIR%".
    pause
    exit /b 1
)

echo Restoring original files...
for %%F in (dfbhd.exe localres.pff EXP1.pff resource.pff dgVoodoo.conf) do (
    if exist "%BACKUP%\%%F" copy /Y "%BACKUP%\%%F" "%GAME_DIR%\%%F" >nul
)
if exist "%BACKUP%\d3d8.dll" (
    copy /Y "%BACKUP%\d3d8.dll" "%GAME_DIR%\d3d8.dll" >nul
) else (
    if exist "%GAME_DIR%\d3d8.dll" del /Q "%GAME_DIR%\d3d8.dll"
)
if exist "%GAME_DIR%\thai_glyph_map.bin" del /Q "%GAME_DIR%\thai_glyph_map.bin"
if exist "%GAME_DIR%\thai_runtime.log" del /Q "%GAME_DIR%\thai_runtime.log"

echo.
echo Original files restored!
pause
