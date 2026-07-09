@echo off
setlocal EnableExtensions

rem User-configurable launch constants.
set "CONDA_ENV_NAME=yadof"
set "GENERATION_COUNT=50"
set "START_GENERATION=0"

cd /d "%~dp0"
echo Working directory: %CD%
echo Conda environment: %CONDA_ENV_NAME%
echo Generations: %GENERATION_COUNT%
echo Start generation: %START_GENERATION%
echo.

call :FindConda
if not defined CONDA_BAT (
    echo ERROR: Could not find conda.bat.
    echo Install Anaconda/Miniconda, or add conda to PATH, then run this file again.
    goto :Fail
)

echo Using conda: %CONDA_BAT%

call :FindCondor
if not defined CONDOR_BIN (
    echo ERROR: Could not find condor_submit.exe.
    echo Install HTCondor and make condor_submit available on PATH, then run this file again.
    goto :Fail
)
set "PATH=%CONDOR_BIN%;%PATH%"
if not defined CONDOR_CONFIG (
    if exist "%CONDOR_ROOT%\condor_config" set "CONDOR_CONFIG=%CONDOR_ROOT%\condor_config"
)

echo Using HTCondor bin: %CONDOR_BIN%
echo CONDOR_CONFIG: %CONDOR_CONFIG%
echo HTCondor pool status:
condor_status -af Name Machine Cpus Memory Disk State Activity YADOF_RAMDISK YADOF_EXECUTE_DIR
if errorlevel 1 (
    echo ERROR: HTCondor pool is not reachable from this submit machine.
    goto :Fail
)
echo.
echo HTCondor queue before start:
condor_q
if errorlevel 1 (
    echo ERROR: HTCondor schedd is not reachable from this submit machine.
    goto :Fail
)
echo.

call "%CONDA_BAT%" activate "%CONDA_ENV_NAME%"
if errorlevel 1 (
    echo ERROR: Failed to activate conda environment "%CONDA_ENV_NAME%".
    goto :Fail
)

echo Python in active environment:
python -c "import sys; print(sys.executable); print(sys.version)"
if errorlevel 1 (
    echo ERROR: Python self-check failed after activating "%CONDA_ENV_NAME%".
    goto :Fail
)

set "YADOF_GENERATIONS=%GENERATION_COUNT%"
set "YADOF_START_GENERATION=%START_GENERATION%"
set "YADOF_PROGRESS=1"
set "YADOF_FAIL_ON_ALL_INF=1"
python -u "%~dp0start_optimization_from_config.py"
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo ERROR: Optimization failed with exit code %RC%.
    goto :Fail
)

echo.
echo Optimization finished successfully.
pause
exit /b 0

:FindConda
if defined CONDA_BAT (
    if exist "%CONDA_BAT%" exit /b 0
)
set "CONDA_BAT="
for %%F in (
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\mambaforge\condabin\conda.bat"
    "%USERPROFILE%\miniforge3\condabin\conda.bat"
    "%LOCALAPPDATA%\miniconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
    "%ProgramData%\miniconda3\condabin\conda.bat"
    "%ProgramData%\anaconda3\condabin\conda.bat"
    "%ProgramData%\mambaforge\condabin\conda.bat"
    "%ProgramData%\miniforge3\condabin\conda.bat"
) do (
    if exist "%%~F" (
        set "CONDA_BAT=%%~F"
        exit /b 0
    )
)

for /f "delims=" %%F in ('where conda 2^>nul') do (
    if /i "%%~nxF"=="conda.bat" (
        set "CONDA_BAT=%%~F"
        exit /b 0
    )
    if /i "%%~nxF"=="conda.exe" (
        if exist "%%~dpF..\condabin\conda.bat" (
            for %%G in ("%%~dpF..\condabin\conda.bat") do set "CONDA_BAT=%%~fG"
            exit /b 0
        )
        if exist "%%~dpFconda.bat" (
            set "CONDA_BAT=%%~dpFconda.bat"
            exit /b 0
        )
    )
)
exit /b 0

:FindCondor
if defined CONDOR_LOCATION (
    if exist "%CONDOR_LOCATION%\bin\condor_submit.exe" (
        set "CONDOR_ROOT=%CONDOR_LOCATION%"
        set "CONDOR_BIN=%CONDOR_LOCATION%\bin"
        exit /b 0
    )
)
set "CONDOR_ROOT="
set "CONDOR_BIN="
for %%D in (
    "%ProgramFiles%\HTCondor"
    "%ProgramFiles%\Condor"
) do (
    if exist "%%~D\bin\condor_submit.exe" (
        set "CONDOR_ROOT=%%~D"
        set "CONDOR_BIN=%%~D\bin"
        exit /b 0
    )
)
for /f "delims=" %%F in ('where condor_submit 2^>nul') do (
    for %%G in ("%%~dpF..") do set "CONDOR_ROOT=%%~fG"
    set "CONDOR_BIN=%%~dpF"
    exit /b 0
)
exit /b 0

:Fail
echo.
echo Press any key to close.
pause >nul
exit /b 1
