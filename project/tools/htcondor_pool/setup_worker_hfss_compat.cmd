@echo off
setlocal EnableExtensions

if /i "%~1"=="__elevated" goto :RunElevated

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator privileges...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%ComSpec%' -ArgumentList '/c','\"%~f0\" __elevated' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

:RunElevated
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_worker_hfss_compat.ps1"
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo Worker HFSS compatibility setup failed with exit code %RC%.
) else (
    echo Worker HFSS compatibility setup finished.
)
pause
exit /b %RC%
