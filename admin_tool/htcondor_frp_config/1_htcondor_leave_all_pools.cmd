@echo off
setlocal
rem Avoid inheriting PowerShell 7 module paths when launched from a PS7 terminal.
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules;%ProgramFiles%\WindowsPowerShell\Modules"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp01_htcondor_leave_all_pools.ps1" %*
exit /b %errorlevel%
