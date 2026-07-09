@echo off
setlocal

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator privileges...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0configure_worker_ramdisk_execute.ps1\"' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_worker_ramdisk_execute.ps1" -ExecuteDir "%TEMP%\condor_execute"
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo Worker execute setup failed with exit code %RC%.
    echo Pass an available execute path to configure_worker_ramdisk_execute.ps1 if the default temp path is not suitable.
) else (
    echo Worker execute setup finished.
)
pause
exit /b %RC%
