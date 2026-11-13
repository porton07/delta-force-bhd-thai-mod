@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x86
if errorlevel 1 exit /b 1
cl /nologo /LD /EHsc /O2 /DWIN32 /D_WINDOWS "ThaiPatch\tools\thai_runtime.cpp" /link /MACHINE:X86 /DEF:"ThaiPatch\tools\thai_runtime.def" /OUT:"ThaiPatch\build-full-thai\d3d8.dll"
exit /b %errorlevel%
