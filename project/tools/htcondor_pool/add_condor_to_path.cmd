@echo off
setlocal

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator privileges...
    if "%~1"=="" (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    ) else (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList @('%~1') -Verb RunAs"
    )
    exit /b
)

if "%~1"=="" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0add_condor_to_path.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0add_condor_to_path.ps1" -CondorLocation "%~1"
)
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo Failed to add HTCondor to PATH. Exit code: %RC%.
) else (
    echo HTCondor PATH setup finished.
    echo Open a new Command Prompt before running condor commands.
)
pause
exit /b %RC%
