@echo off
setlocal

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator privileges...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0configure_worker_ramdisk_execute.ps1\"' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_worker_ramdisk_execute.ps1"
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo Worker R: execute setup failed with exit code %RC%.
    echo Make sure R: exists on this machine, then run this file again.
) else (
    echo Worker R: execute setup finished.
)
pause
exit /b %RC%
