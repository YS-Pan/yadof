@echo off
setlocal

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator privileges...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_pool_setup_elevated.ps1" -Role Worker -MachineLabel 6
    exit /b
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_htcondor_pool.ps1" -Role Worker -MachineLabel 6
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo HTCondor worker setup failed with exit code %RC%.
    echo Run setup_machine_1_manager.cmd first so manager_ip.txt exists in this folder.
) else (
    echo HTCondor worker setup finished.
)
pause
exit /b %RC%
