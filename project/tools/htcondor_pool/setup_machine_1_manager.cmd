@echo off
setlocal

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator privileges...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_pool_setup_elevated.ps1" -Role Manager -MachineLabel 1
    exit /b
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_htcondor_pool.ps1" -Role Manager -MachineLabel 1
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo HTCondor manager setup failed with exit code %RC%.
) else (
    echo HTCondor manager setup finished.
)
pause
exit /b %RC%
