[CmdletBinding()]
param(
    [string]$ScratchPath = (Join-Path ([IO.Path]::GetTempPath()) "yadof-pychrono-validation-$PID")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$miniforgeRoot = "C:\ProgramData\Miniforge3"
$environmentPrefix = Join-Path $miniforgeRoot "envs\pychrono-10"
$pythonPath = Join-Path $environmentPrefix "python.exe"
$expectedMachineValue = [Environment]::GetEnvironmentVariable(
    "YADOF_PYCHRONO_PYTHON",
    "Machine"
)
if ($expectedMachineValue -ne $pythonPath) {
    throw "Machine-level YADOF_PYCHRONO_PYTHON does not resolve to $pythonPath"
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Shared PyChrono interpreter is missing: $pythonPath"
}

$ScratchPath = [IO.Path]::GetFullPath($ScratchPath)
if ($ScratchPath.StartsWith($miniforgeRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "ScratchPath must be caller-owned and outside the shared prefix."
}
if (Test-Path -LiteralPath $ScratchPath) {
    throw "ScratchPath already exists: $ScratchPath"
}
New-Item -ItemType Directory -Path $ScratchPath | Out-Null

function Test-SharedWriteDenied {
    param([Parameter(Mandatory = $true)][string]$Path)

    $probePath = Join-Path $Path ".yadof-write-probe-$PID.tmp"
    try {
        $stream = [IO.File]::Open(
            $probePath,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::None
        )
        $stream.Dispose()
        Remove-Item -LiteralPath $probePath -Force
        return $false
    } catch [UnauthorizedAccessException] {
        return $true
    }
}

try {
    $runtimePathEntries = @(
        $environmentPrefix,
        (Join-Path $environmentPrefix "Library\mingw-w64\bin"),
        (Join-Path $environmentPrefix "Library\usr\bin"),
        (Join-Path $environmentPrefix "Library\bin"),
        (Join-Path $environmentPrefix "Scripts"),
        (Join-Path $environmentPrefix "bin")
    )
    $runtimePath = (($runtimePathEntries + [Environment]::GetEnvironmentVariable("Path", "Machine")) -join ";")

    $smokeScript = Join-Path $PSScriptRoot "pychrono_smoke.py"
    $standardErrorPath = Join-Path $ScratchPath "pychrono-smoke.stderr.txt"
    $standardOutputPath = Join-Path $ScratchPath "pychrono-smoke.stdout.txt"
    $smokeStartInfo = [Diagnostics.ProcessStartInfo]::new()
    $smokeStartInfo.FileName = $pythonPath
    $smokeStartInfo.Arguments = "-B -s -P `"$smokeScript`""
    $smokeStartInfo.WorkingDirectory = $ScratchPath
    $smokeStartInfo.UseShellExecute = $false
    $smokeStartInfo.CreateNoWindow = $true
    $smokeStartInfo.RedirectStandardOutput = $true
    $smokeStartInfo.RedirectStandardError = $true
    $smokeEnvironmentNames = @(
        "Path", "PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE",
        "PYTHONDONTWRITEBYTECODE", "TEMP", "TMP",
        "YADOF_EXPECTED_PYCHRONO_PYTHON", "YADOF_EXPECTED_PYCHRONO_VERSION",
        "YADOF_EXPECTED_PYCHRONO_BUILD"
    )
    $smokeEnvironmentBefore = @{}
    foreach ($name in $smokeEnvironmentNames) {
        $smokeEnvironmentBefore[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }
    try {
        [Environment]::SetEnvironmentVariable("Path", $runtimePath, "Process")
        [Environment]::SetEnvironmentVariable("PYTHONPATH", $null, "Process")
        [Environment]::SetEnvironmentVariable("PYTHONHOME", $null, "Process")
        [Environment]::SetEnvironmentVariable("PYTHONNOUSERSITE", "1", "Process")
        [Environment]::SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "1", "Process")
        [Environment]::SetEnvironmentVariable("TEMP", $ScratchPath, "Process")
        [Environment]::SetEnvironmentVariable("TMP", $ScratchPath, "Process")
        [Environment]::SetEnvironmentVariable("YADOF_EXPECTED_PYCHRONO_PYTHON", $pythonPath, "Process")
        [Environment]::SetEnvironmentVariable("YADOF_EXPECTED_PYCHRONO_VERSION", "10.0.0", "Process")
        [Environment]::SetEnvironmentVariable("YADOF_EXPECTED_PYCHRONO_BUILD", "py313h418371c_0", "Process")
        $smokeProcess = [Diagnostics.Process]::Start($smokeStartInfo)
        if (-not $smokeProcess.WaitForExit(120000)) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $smokeProcess.Id /T /F | Out-Null
            throw "Ordinary-user PyChrono mechanics smoke exceeded 120 seconds."
        }
        $smokeJson = $smokeProcess.StandardOutput.ReadToEnd().Trim()
        $standardError = $smokeProcess.StandardError.ReadToEnd().Trim()
        $smokeProcess.WaitForExit()
    } finally {
        foreach ($name in $smokeEnvironmentNames) {
            [Environment]::SetEnvironmentVariable($name, $smokeEnvironmentBefore[$name], "Process")
        }
    }
    $smokeJson | Set-Content -LiteralPath $standardOutputPath -Encoding UTF8
    $standardError | Set-Content -LiteralPath $standardErrorPath -Encoding UTF8
    if ($smokeProcess.ExitCode -ne 0) {
        throw "Ordinary-user PyChrono mechanics smoke failed with exit code $($smokeProcess.ExitCode): $standardError"
    }
    $smoke = $smokeJson | ConvertFrom-Json
    if ($smoke.pythonpath_present -or $smoke.user_site_enabled -or $smoke.yadof_importable) {
        throw "Ordinary-user smoke reported an unclean child environment."
    }

    $rootWriteDenied = Test-SharedWriteDenied -Path $miniforgeRoot
    $environmentWriteDenied = Test-SharedWriteDenied -Path $environmentPrefix
    if (-not $rootWriteDenied -or -not $environmentWriteDenied) {
        throw "The current user can modify at least one shared prefix."
    }

    [ordered]@{
        schema_version = 1
        validated_at = (Get-Date).ToString("o")
        identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        is_elevated_administrator = ([Security.Principal.WindowsPrincipal]::new(
            [Security.Principal.WindowsIdentity]::GetCurrent()
        )).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        machine_setting = $expectedMachineValue
        miniforge_root_write_denied = $rootWriteDenied
        pychrono_prefix_write_denied = $environmentWriteDenied
        smoke = $smoke
    } | ConvertTo-Json -Depth 8
} finally {
    if (Test-Path -LiteralPath $ScratchPath) {
        Remove-Item -LiteralPath $ScratchPath -Recurse -Force
    }
}
