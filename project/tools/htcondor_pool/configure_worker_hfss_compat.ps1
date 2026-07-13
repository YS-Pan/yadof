param(
    [string]$CondorLocation = "",
    [switch]$NoReconfig
)

$ErrorActionPreference = "Stop"

$ThreadVariables = "CUBACORES GOMAXPROCS JULIA_NUM_THREADS MKL_NUM_THREADS NUMEXPR_NUM_THREADS OMP_NUM_THREADS OPENBLAS_NUM_THREADS PYTHON_CPU_COUNT ROOT_MAX_THREADS TF_LOOP_PARALLEL_ITERATIONS TF_NUM_THREADS"
$BeginMarker = "# BEGIN YADOF HFSS OPENMP COMPAT"
$EndMarker = "# END YADOF HFSS OPENMP COMPAT"

function Warn-IfNotAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Warning "PowerShell is not elevated. The config write or startd reconfiguration may be denied; use setup_worker_hfss_compat.cmd for UAC elevation."
    }
}

function Resolve-CondorRoot {
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($CondorLocation) {
        $candidates.Add($CondorLocation)
    }
    if ($env:CONDOR_LOCATION) {
        $candidates.Add($env:CONDOR_LOCATION)
    }

    $command = Get-Command condor_config_val.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        $candidates.Add((Split-Path -Parent (Split-Path -Parent $command.Source)))
    }
    $candidates.Add("C:\condor")

    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        $root = [IO.Path]::GetFullPath($candidate)
        if (Test-Path -LiteralPath (Join-Path $root "bin\condor_config_val.exe") -PathType Leaf) {
            return $root
        }
    }
    throw "Could not locate HTCondor. Pass -CondorLocation with its install root."
}

function Get-LocalConfigPath {
    param(
        [string]$CondorRoot,
        [string]$ConfigVal
    )

    $rootConfig = Join-Path $CondorRoot "condor_config"
    if (Test-Path -LiteralPath $rootConfig -PathType Leaf) {
        $env:CONDOR_CONFIG = $rootConfig
    }

    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $configured = & $ConfigVal "LOCAL_CONFIG_FILE" 2>$null | Select-Object -First 1
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    if ($configured) {
        $first = @($configured -split "," | ForEach-Object { $_.Trim().Trim('"') } | Where-Object { $_ } | Select-Object -First 1)[0]
        if ($first) {
            return [IO.Path]::GetFullPath($first)
        }
    }
    return Join-Path $CondorRoot "condor_config.local"
}

function Set-ManagedBlock {
    param([string]$TargetPath)

    $body = @(
        $BeginMarker,
        "# HFSS 2024.1 Iterative Solver crashes when HTCondor injects OMP_THREAD_LIMIT.",
        "STARTER_NUM_THREADS_ENV_VARS = $ThreadVariables",
        $EndMarker
    ) -join [Environment]::NewLine
    $block = $body + [Environment]::NewLine

    $existing = ""
    if (Test-Path -LiteralPath $TargetPath -PathType Leaf) {
        $existing = [IO.File]::ReadAllText($TargetPath)
    }
    $pattern = "(?ms)^" + [regex]::Escape($BeginMarker) + ".*?^" + [regex]::Escape($EndMarker) + "\r?\n?"
    if ($existing -match [regex]::Escape($BeginMarker)) {
        $updated = [regex]::Replace($existing, $pattern, $block)
    }
    elseif ($existing.Trim().Length -gt 0) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block
    }
    else {
        $updated = $block
    }

    $parent = Split-Path -Parent $TargetPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path -LiteralPath $TargetPath -PathType Leaf) {
        $backup = "$TargetPath.bak.$(Get-Date -Format yyyyMMdd-HHmmss)"
        Copy-Item -LiteralPath $TargetPath -Destination $backup -Force
        Write-Host "Backup written to $backup"
    }
    [IO.File]::WriteAllText($TargetPath, $updated, [Text.Encoding]::ASCII)
}

Warn-IfNotAdministrator
$condorRoot = Resolve-CondorRoot
$configVal = Join-Path $condorRoot "bin\condor_config_val.exe"
$reconfig = Join-Path $condorRoot "bin\condor_reconfig.exe"
$localConfig = Get-LocalConfigPath -CondorRoot $condorRoot -ConfigVal $configVal

Write-Host "HTCondor root: $condorRoot"
Write-Host "Local config: $localConfig"
Set-ManagedBlock -TargetPath $localConfig

if (-not $NoReconfig) {
    & $reconfig -startd | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "condor_reconfig -startd failed with exit code $LASTEXITCODE"
    }
}

$effective = & $configVal "STARTER_NUM_THREADS_ENV_VARS" | Select-Object -First 1
Write-Host "STARTER_NUM_THREADS_ENV_VARS = $effective"
if (@($effective -split "[ ,]+") -contains "OMP_THREAD_LIMIT") {
    throw "OMP_THREAD_LIMIT is still present in the effective starter thread-variable list."
}
Write-Host "HFSS OpenMP compatibility setting applied."
