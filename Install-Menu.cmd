@echo off
cd /d "%~dp0.."
python -X utf8 ThaiPatch\tools\build_menu_test.py --install
pause
