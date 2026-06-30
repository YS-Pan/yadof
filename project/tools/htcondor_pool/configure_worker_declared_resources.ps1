[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$DeclaredCpus,

    [Parameter(Mandatory = $true)]
    [int]$DeclaredMemoryMb,

    [Parameter(Mandatory = $true)]
    [int]$DeclaredDiskMb,

    [string]$ExecuteDir = "R:\condor_execute",

    [string]$WorkerPythonExe = "C:\ProgramData\miniconda3\envs\yadof\python.exe",

    [string]$PartitionableSlot = "1",

    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$script:CondorBinDir = $null
$script:CondorRootDir = $null

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an elevated Administrator shell."
    }
}

function Find-CondorBinDir {
    if ($env:CONDOR_LOCATION) {
        $candidate = Join-Path $env:CONDOR_LOCATION "bin"
        if (Test-Path -LiteralPath (Join-Path $candidate "condor_config_val.exe")) {
            return $candidate
        }
    }

    foreach ($dir in @(
        "D:\condor\bin",
        "D:\Condor\bin",
        "D:\HTCondor\bin",
        "C:\condor\bin",
        "C:\Condor\bin",
        "C:\HTCondor\bin",
        "$env:ProgramFiles\HTCondor\bin",
        "$env:ProgramFiles\Condor\bin"
    )) {
        if ($dir -and (Test-Path -LiteralPath (Join-Path $dir "condor_config_val.exe"))) {
            return $dir
        }
    }

    $command = Get-Command condor_config_val.exe -ErrorAction SilentlyContinue
    if ($command) {
        return Split-Path -Parent $command.Source
    }

    throw "Could not find condor_config_val.exe. Set CONDOR_LOCATION or install HTCondor first."
}

function Initialize-Condor {
    $script:CondorBinDir = Find-CondorBinDir
    $script:CondorRootDir = Split-Path -Parent $script:CondorBinDir
    if (($env:PATH -split ";") -notcontains $script:CondorBinDir) {
        $env:PATH = "$script:CondorBinDir;$env:PATH"
    }
    $rootConfig = Join-Path $script:CondorRootDir "condor_config"
    if (-not $env:CONDOR_CONFIG -and (Test-Path -LiteralPath $rootConfig)) {
        $env:CONDOR_CONFIG = $rootConfig
    }
    Write-Host "Using HTCondor binaries from: $script:CondorBinDir"
    Write-Host "CONDOR_CONFIG: $env:CONDOR_CONFIG"
}

function Invoke-CondorConfigVal {
    param([string]$Name)
    $exe = Join-Path $script:CondorBinDir "condor_config_val.exe"
    $value = (& $exe $Name 2>$null | Select-Object -First 1)
    if ($LASTEXITCODE -eq 0 -and $value) {
        return [string]$value
    }
    return $null
}

function Ensure-RootLoadsLocalConfig {
    param([string]$LocalConfigPath)

    $rootConfig = $env:CONDOR_CONFIG
    if (-not $rootConfig) {
        $rootConfig = Join-Path $script:CondorRootDir "condor_config"
        $env:CONDOR_CONFIG = $rootConfig
        [Environment]::SetEnvironmentVariable("CONDOR_CONFIG", $rootConfig, "Machine")
    }

    $localForCondor = $LocalConfigPath -replace "\\", "/"
    $existing = ""
    if (Test-Path -LiteralPath $rootConfig) {
        $existing = [IO.File]::ReadAllText($rootConfig)
    }
    if ($existing -match [regex]::Escape($LocalConfigPath) -or $existing -match [regex]::Escape($localForCondor)) {
        return
    }

    $begin = "# BEGIN YADOF LOCAL CONFIG INCLUDE"
    $end = "# END YADOF LOCAL CONFIG INCLUDE"
    $block = $begin + [Environment]::NewLine +
        "LOCAL_CONFIG_FILE = $localForCondor" + [Environment]::NewLine +
        $end + [Environment]::NewLine

    $pattern = "(?ms)^# BEGIN YADOF LOCAL CONFIG INCLUDE\r?\n.*?^# END YADOF LOCAL CONFIG INCLUDE\r?\n?"
    if ($existing -match "# BEGIN YADOF LOCAL CONFIG INCLUDE") {
        $updated = [regex]::Replace($existing, $pattern, $block)
    }
    elseif ($existing.Trim().Length -gt 0) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block
    }
    else {
        $updated = $block
    }

    $parent = Split-Path -Parent $rootConfig
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path -LiteralPath $rootConfig) {
        Copy-Item -LiteralPath $rootConfig -Destination "$rootConfig.bak.$(Get-Date -Format yyyyMMdd-HHmmss)" -Force
    }
    [IO.File]::WriteAllText($rootConfig, $updated, [Text.Encoding]::ASCII)
}

function Get-LocalConfigPath {
    $raw = Invoke-CondorConfigVal "LOCAL_CONFIG_FILE"
    if ($raw) {
        $first = @($raw -split "," | ForEach-Object { $_.Trim().Trim('"') } | Where-Object { $_ } | Select-Object -First 1)[0]
        if ($first) {
            $parent = Split-Path -Parent $first
            if ($parent) {
                New-Item -ItemType Directory -Force -Path $parent | Out-Null
            }
            return $first
        }
    }

    $fallback = Join-Path $script:CondorRootDir "condor_config.local"
    Ensure-RootLoadsLocalConfig -LocalConfigPath $fallback
    return $fallback
}

function Set-ManagedBlock {
    param(
        [string]$TargetPath,
        [string]$Body
    )

    $begin = "# BEGIN YADOF WORKER DECLARED RESOURCES"
    $end = "# END YADOF WORKER DECLARED RESOURCES"
    $block = $begin + [Environment]::NewLine + $Body.TrimEnd() + [Environment]::NewLine + $end + [Environment]::NewLine

    $existing = ""
    if (Test-Path -LiteralPath $TargetPath) {
        $existing = [IO.File]::ReadAllText($TargetPath)
    }
    $pattern = "(?ms)^# BEGIN YADOF WORKER DECLARED RESOURCES\r?\n.*?^# END YADOF WORKER DECLARED RESOURCES\r?\n?"
    if ($existing -match "# BEGIN YADOF WORKER DECLARED RESOURCES") {
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
    if (Test-Path -LiteralPath $TargetPath) {
        Copy-Item -LiteralPath $TargetPath -Destination "$TargetPath.bak.$(Get-Date -Format yyyyMMdd-HHmmss)" -Force
    }
    [IO.File]::WriteAllText($TargetPath, $updated, [Text.Encoding]::ASCII)
}

function Ensure-ExecuteDirectory {
    param([string]$PathText)

    $root = [IO.Path]::GetPathRoot($PathText)
    if (-not $root -or -not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "Required execute drive is not available: $root"
    }
    New-Item -ItemType Directory -Force -Path $PathText | Out-Null
    $icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
    $aclOutput = & $icacls $PathText /grant "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-11:(OI)(CI)M" /T
    $aclOutput | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed while granting access to $PathText"
    }
}

function Ensure-WorkerPythonAccess {
    param([string]$PythonExe)

    if (-not $PythonExe) {
        return
    }
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "Worker Python executable does not exist: $PythonExe"
    }

    $envRoot = Split-Path -Parent $PythonExe
    Write-Host "Granting execute/read access for worker Python environment: $envRoot"

    $icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
    $aclOutput = & $icacls $envRoot /grant "*S-1-5-11:(OI)(CI)RX" "*S-1-5-32-545:(OI)(CI)RX" /T
    $aclOutput | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed while granting access to $envRoot"
    }
}

function Restart-Condor {
    $restart = Join-Path $script:CondorBinDir "condor_restart.exe"
    Write-Host "Restarting HTCondor master..."
    & $restart -master | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "condor_restart -master failed with exit code $LASTEXITCODE"
    }
    Start-Sleep -Seconds 8
}

function Show-Verification {
    $configVal = Join-Path $script:CondorBinDir "condor_config_val.exe"
    Write-Host ""
    Write-Host "Post-setup config values:"
    foreach ($name in @("NUM_CPUS", "MEMORY", "DISK", "EXECUTE", "START", "SLOT_TYPE_1", "NUM_SLOTS_TYPE_1", "SLOT_TYPE_1_PARTITIONABLE", "STARTD_ATTRS")) {
        $value = (& $configVal $name 2>$null | Select-Object -First 1)
        if (-not $value) {
            $value = "<empty>"
        }
        Write-Host "  $name = $value"
    }

    $status = Join-Path $script:CondorBinDir "condor_status.exe"
    Write-Host ""
    Write-Host "Visible worker slots:"
    & $status -af Name Machine Cpus Memory Disk State Activity YADOF_RAMDISK YADOF_DECLARED_CPUS YADOF_DECLARED_MEMORY_MB YADOF_DECLARED_DISK_MB 2>$null | ForEach-Object {
        Write-Host "  $_"
    }
}

if ($DeclaredCpus -lt 1) {
    throw "DeclaredCpus must be at least 1."
}
if ($DeclaredMemoryMb -lt 1) {
    throw "DeclaredMemoryMb must be at least 1."
}
if ($DeclaredDiskMb -lt 1) {
    throw "DeclaredDiskMb must be at least 1."
}

Assert-Administrator
Initialize-Condor

$partitionable = [string]$PartitionableSlot -in @("1", "true", "True", "yes", "YES", "on", "ON")
$localConfig = Get-LocalConfigPath
$diskKb = [int64]$DeclaredDiskMb * 1024
$executeForCondor = $ExecuteDir.TrimEnd("\") -replace "\\", "/"

Write-Host "YADOF worker declared resource setup"
Write-Host "Declared CPUs: $DeclaredCpus"
Write-Host "Declared memory MB: $DeclaredMemoryMb"
Write-Host "Declared disk MB: $DeclaredDiskMb"
Write-Host "Execute dir: $ExecuteDir"
Write-Host "Worker Python exe: $WorkerPythonExe"
Write-Host "Partitionable slot: $partitionable"
Write-Host "Local config: $localConfig"

Ensure-ExecuteDirectory -PathText $ExecuteDir
Ensure-WorkerPythonAccess -PythonExe $WorkerPythonExe

$slotLines = if ($partitionable) {
    @(
        "SLOT_TYPE_1 = cpus=100%, ram=100%, disk=100%",
        "NUM_SLOTS_TYPE_1 = 1",
        "SLOT_TYPE_1_PARTITIONABLE = True",
        "NUM_SLOTS = 1"
    )
}
else {
    @(
        "NUM_SLOTS = $DeclaredCpus"
    )
}

$body = @"
# Generated by project/tools/htcondor_pool/configure_worker_declared_resources.ps1
NUM_CPUS = $DeclaredCpus
MEMORY = $DeclaredMemoryMb
DISK = $diskKb
EXECUTE = $executeForCondor
YADOF_RAMDISK = True
YADOF_EXECUTE_DIR = "$executeForCondor"
YADOF_DECLARED_CPUS = $DeclaredCpus
YADOF_DECLARED_MEMORY_MB = $DeclaredMemoryMb
YADOF_DECLARED_DISK_MB = $DeclaredDiskMb
STARTD_ATTRS = YADOF_RAMDISK, YADOF_EXECUTE_DIR, YADOF_DECLARED_CPUS, YADOF_DECLARED_MEMORY_MB, YADOF_DECLARED_DISK_MB
$($slotLines -join [Environment]::NewLine)
"@

Set-ManagedBlock -TargetPath $localConfig -Body $body

if (-not $NoRestart) {
    Restart-Condor
}

Show-Verification
Write-Host ""
Write-Host "Done. Run this same CMD on every worker that should execute jobs."
