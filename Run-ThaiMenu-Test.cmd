@echo off
cd /d "%~dp0.."
python -X utf8 ThaiPatch\tools\run_menu_test.py
if errorlevel 1 pause
