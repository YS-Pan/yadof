@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose_pool.ps1"
echo.
echo Diagnosis log saved to:
echo %~dp0diagnose_pool_%COMPUTERNAME%.txt
pause
