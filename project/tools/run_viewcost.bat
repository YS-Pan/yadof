@echo off
set "SCRIPT_NAME=%~n0"
set "PYTHON_FILE=%SCRIPT_NAME:run_=%.py"
pushd "%~dp0"

REM --- Activate conda environment: yadof ---
set "ENV_NAME=yadof"
for /f "delims=" %%i in ('conda info --base 2^>nul') do set "CONDA_BASE=%%i"
if not defined CONDA_BASE (
    echo [ERROR] conda not found in PATH. Please run this from Anaconda Prompt or add conda to PATH.
    pause
    popd
    exit /b 1
)
call "%CONDA_BASE%\Scripts\activate.bat" "%ENV_NAME%"

python "%PYTHON_FILE%"
popd
pause
