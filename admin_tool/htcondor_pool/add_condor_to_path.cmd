@echo off
setlocal

if "%~1"=="" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0add_condor_to_path.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0add_condor_to_path.ps1" -CondorLocation "%~1"
)
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo HTCondor PATH lookup failed. Exit code: %RC%.
) else (
    echo HTCondor lookup check finished. No system environment variables were changed.
)
pause
exit /b %RC%
