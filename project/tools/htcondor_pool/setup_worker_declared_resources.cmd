@echo off
setlocal EnableExtensions

rem Edit these values per worker, then double-click this file.
rem MEMORY is in MB. DISK is in MB and should not exceed the R: RAM disk size.
set "DECLARE_CPUS=6"
set "DECLARE_MEMORY_MB=32000"
set "DECLARE_DISK_MB=24000"
set "EXECUTE_DIR=R:\condor_execute"
set "WORKER_PYTHON_EXE=C:\ProgramData\miniconda3\envs\yadof\python.exe"
set "PARTITIONABLE_SLOT=1"
set "RESTART_CONDOR=1"

if /i "%~1"=="__elevated" goto :RunElevated

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator privileges...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%ComSpec%' -ArgumentList '/c','\"%~f0\" __elevated' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

:RunElevated
set "NO_RESTART_ARG="
if "%RESTART_CONDOR%"=="0" set "NO_RESTART_ARG=-NoRestart"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_worker_declared_resources.ps1" ^
    -DeclaredCpus "%DECLARE_CPUS%" ^
    -DeclaredMemoryMb "%DECLARE_MEMORY_MB%" ^
    -DeclaredDiskMb "%DECLARE_DISK_MB%" ^
    -ExecuteDir "%EXECUTE_DIR%" ^
    -WorkerPythonExe "%WORKER_PYTHON_EXE%" ^
    -PartitionableSlot "%PARTITIONABLE_SLOT%" ^
    %NO_RESTART_ARG%

set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
    echo Worker declared resource setup failed with exit code %RC%.
) else (
    echo Worker declared resource setup finished.
)
pause
exit /b %RC%
