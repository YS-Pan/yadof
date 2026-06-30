[CmdletBinding()]
param(
    [string]$ExecuteDir = "R:\condor_execute",

    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$script:CondorCommands = @{}
$script:CondorBinDir = $null
$script:CondorRootDir = $null

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an elevated Administrator shell."
    }
}

function Get-CondorBinCandidates {
    $dirs = New-Object System.Collections.Generic.List[string]

    if ($env:CONDOR_LOCATION) {
        $dirs.Add((Join-Path $env:CONDOR_LOCATION "bin"))
    }
    foreach ($dir in @(
        "D:\condor\bin",
        "D:\Condor\bin",
        "D:\HTCondor\bin",
        "C:\Condor\bin",
        "C:\condor\bin",
        "C:\HTCondor\bin",
        "$env:ProgramFiles\Condor\bin",
        "$env:ProgramFiles\HTCondor\bin"
    )) {
        if ($dir) {
            $dirs.Add($dir)
        }
    }

    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $dirs.Add((Join-Path $programFilesX86 "Condor\bin"))
        $dirs.Add((Join-Path $programFilesX86 "HTCondor\bin"))
    }

    $services = @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*condor*" -or $_.DisplayName -like "*HTCondor*" })
    foreach ($service in $services) {
        $rawPath = [string]$service.PathName
        if (-not $rawPath) {
            continue
        }
        $exePath = $null
        if ($rawPath -match '^\s*"([^"]+condor_master\.exe)"') {
            $exePath = $matches[1]
        }
        elseif ($rawPath -match '^\s*([^"]*condor_master\.exe)') {
            $exePath = $matches[1]
        }
        if ($exePath -and (Test-Path -LiteralPath $exePath)) {
            $dirs.Add((Split-Path -Parent $exePath))
        }
    }

    return @($dirs | Where-Object { $_ } | Select-Object -Unique)
}

function Find-CondorCommand {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    foreach ($dir in Get-CondorBinCandidates) {
        $candidate = Join-Path $dir "$Name.exe"
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    $searched = (Get-CondorBinCandidates) -join ", "
    throw "Required HTCondor command '$Name.exe' was not found. Searched PATH and: $searched"
}

function Initialize-CondorCommands {
    foreach ($name in @("condor_config_val", "condor_restart", "condor_status")) {
        $script:CondorCommands[$name] = Find-CondorCommand $name
    }

    $binDir = Split-Path -Parent $script:CondorCommands["condor_config_val"]
    $script:CondorBinDir = $binDir
    $script:CondorRootDir = Split-Path -Parent $binDir
    $pathParts = @($env:PATH -split ";" | Where-Object { $_ })
    if ($pathParts -notcontains $binDir) {
        $env:PATH = "$binDir;$env:PATH"
    }
    Write-Host "Using HTCondor binaries from: $binDir"
}

function Invoke-CondorConfigVal {
    param([string]$Name)
    try {
        $condorConfigVal = $script:CondorCommands["condor_config_val"]
        $value = (& $condorConfigVal $Name 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $value) {
            return [string]$value
        }
    }
    catch {
        return $null
    }
    return $null
}

function Get-CondorRootConfigCandidates {
    $candidates = New-Object System.Collections.Generic.List[string]

    $condorConfig = [Environment]::GetEnvironmentVariable("CONDOR_CONFIG", "Machine")
    if ($condorConfig) {
        $candidates.Add($condorConfig)
    }
    if ($env:CONDOR_CONFIG) {
        $candidates.Add($env:CONDOR_CONFIG)
    }
    if ($script:CondorRootDir) {
        $candidates.Add((Join-Path $script:CondorRootDir "condor_config"))
        $candidates.Add((Join-Path $script:CondorRootDir "etc\condor_config"))
    }

    foreach ($candidate in @(
        "D:\condor\condor_config",
        "D:\Condor\condor_config",
        "D:\HTCondor\condor_config",
        "C:\Condor\condor_config",
        "C:\condor\condor_config",
        "C:\HTCondor\condor_config"
    )) {
        $candidates.Add($candidate)
    }

    return @($candidates | Where-Object { $_ } | Select-Object -Unique)
}

function Get-ExistingCondorRootConfig {
    foreach ($candidate in Get-CondorRootConfigCandidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

function Ensure-CondorRootLoadsLocalConfig {
    param([string]$LocalConfigPath)

    $rootConfig = Get-ExistingCondorRootConfig
    if (-not $rootConfig) {
        if (-not $script:CondorRootDir) {
            throw "Could not locate HTCondor root config and could not infer the install root."
        }
        $rootConfig = Join-Path $script:CondorRootDir "condor_config"
        Write-Warning "No HTCondor root config was found. Creating $rootConfig and setting system CONDOR_CONFIG to this file."
        [Environment]::SetEnvironmentVariable("CONDOR_CONFIG", $rootConfig, "Machine")
        $env:CONDOR_CONFIG = $rootConfig
    }

    $localConfigForCondor = $LocalConfigPath -replace "\\", "/"
    $begin = "# BEGIN YADOF RAMDISK LOCAL CONFIG INCLUDE"
    $end = "# END YADOF RAMDISK LOCAL CONFIG INCLUDE"
    $includeBlock = $begin + [Environment]::NewLine +
        "LOCAL_CONFIG_FILE = $localConfigForCondor" + [Environment]::NewLine +
        $end + [Environment]::NewLine

    $existing = ""
    if (Test-Path -LiteralPath $rootConfig) {
        $existing = [IO.File]::ReadAllText($rootConfig)
    }

    if ($existing -match [regex]::Escape($LocalConfigPath) -or $existing -match [regex]::Escape($localConfigForCondor)) {
        Write-Host "HTCondor root config already references $LocalConfigPath"
        return
    }

    $pattern = "(?ms)^# BEGIN YADOF RAMDISK LOCAL CONFIG INCLUDE\r?\n.*?^# END YADOF RAMDISK LOCAL CONFIG INCLUDE\r?\n?"
    if ($existing -match "# BEGIN YADOF RAMDISK LOCAL CONFIG INCLUDE") {
        $updated = [regex]::Replace($existing, $pattern, $includeBlock)
    }
    elseif ($existing.Trim().Length -gt 0) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $includeBlock
    }
    else {
        $updated = $includeBlock
    }

    Write-Host "Ensuring HTCondor root config loads local config: $rootConfig"
    $parent = Split-Path -Parent $rootConfig
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path -LiteralPath $rootConfig) {
        $backup = "$rootConfig.bak.$(Get-Date -Format yyyyMMdd-HHmmss)"
        Copy-Item -LiteralPath $rootConfig -Destination $backup -Force
        Write-Host "Root config backup written to $backup"
    }
    [IO.File]::WriteAllText($rootConfig, $updated, [Text.Encoding]::ASCII)
}

function Get-CondorLocalConfigTarget {
    $localFileRaw = Invoke-CondorConfigVal "LOCAL_CONFIG_FILE"
    if ($localFileRaw) {
        $localFiles = @($localFileRaw -split "," | ForEach-Object { $_.Trim().Trim('"') } | Where-Object { $_ })
        foreach ($file in $localFiles) {
            $parent = Split-Path -Parent $file
            if ($parent) {
                New-Item -ItemType Directory -Force -Path $parent | Out-Null
            }
            return $file
        }
    }

    $fallbacks = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath "D:\condor" -PathType Container) {
        $fallbacks.Add("D:\condor\condor_config.local")
    }
    if ($script:CondorRootDir) {
        $fallbacks.Add((Join-Path $script:CondorRootDir "condor_config.local"))
    }
    foreach ($candidate in @(
        "D:\Condor\condor_config.local",
        "D:\HTCondor\condor_config.local",
        "C:\Condor\condor_config.local",
        "C:\condor\condor_config.local",
        "C:\HTCondor\condor_config.local"
    )) {
        $fallbacks.Add($candidate)
    }

    foreach ($candidate in @($fallbacks | Select-Object -Unique)) {
        $parent = Split-Path -Parent $candidate
        if ($parent -and (Test-Path -LiteralPath $parent)) {
            Ensure-CondorRootLoadsLocalConfig -LocalConfigPath $candidate
            return $candidate
        }
    }

    throw "Could not locate HTCondor local config. Run the pool setup script first, then run this script again."
}

function Set-ManagedConfigBlock {
    param(
        [string]$TargetPath,
        [string]$BlockBody
    )

    $begin = "# BEGIN YADOF RAMDISK EXECUTE"
    $end = "# END YADOF RAMDISK EXECUTE"
    $block = $begin + [Environment]::NewLine + $BlockBody.TrimEnd() + [Environment]::NewLine + $end + [Environment]::NewLine

    $existing = ""
    if (Test-Path -LiteralPath $TargetPath) {
        $existing = [IO.File]::ReadAllText($TargetPath)
    }

    $pattern = "(?ms)^# BEGIN YADOF RAMDISK EXECUTE\r?\n.*?^# END YADOF RAMDISK EXECUTE\r?\n?"
    if ($existing -match "# BEGIN YADOF RAMDISK EXECUTE") {
        $updated = [regex]::Replace($existing, $pattern, $block)
    }
    elseif ($existing.Trim().Length -gt 0) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block
    }
    else {
        $updated = $block
    }

    Write-Host "Writing worker execute config block to $TargetPath"
    $parent = Split-Path -Parent $TargetPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path -LiteralPath $TargetPath) {
        $backup = "$TargetPath.bak.$(Get-Date -Format yyyyMMdd-HHmmss)"
        Copy-Item -LiteralPath $TargetPath -Destination $backup -Force
        Write-Host "Backup written to $backup"
    }
    [IO.File]::WriteAllText($TargetPath, $updated, [Text.Encoding]::ASCII)
}

function Ensure-ExecuteDirectory {
    param([string]$PathText)

    $root = [IO.Path]::GetPathRoot($PathText)
    if (-not $root -or -not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "Required execute drive is not available: $root. Create or mount the R: RAM disk first."
    }

    New-Item -ItemType Directory -Force -Path $PathText | Out-Null
    Write-Host "Ensured execute directory: $PathText"

    $icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
    $aclOutput = & $icacls $PathText /grant "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-11:(OI)(CI)M" /T
    $aclOutput | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed while granting access to $PathText"
    }
}

function Restart-Condor {
    Write-Host "Restarting HTCondor..."
    $condorRestart = $script:CondorCommands["condor_restart"]
    $null = & $condorRestart -master
    if ($LASTEXITCODE -ne 0) {
        throw "condor_restart -master failed with exit code $LASTEXITCODE"
    }
    Start-Sleep -Seconds 6
}

function Show-Verification {
    $condorConfigVal = $script:CondorCommands["condor_config_val"]
    Write-Host ""
    Write-Host "Post-setup HTCondor values:"
    foreach ($name in @("YADOF_MACHINE_LABEL", "DAEMON_LIST", "EXECUTE", "YADOF_RAMDISK", "YADOF_EXECUTE_DIR", "STARTD_ATTRS")) {
        $value = (& $condorConfigVal $name 2>$null | Select-Object -First 1)
        if (-not $value) {
            $value = "<empty>"
        }
        Write-Host "  $name = $value"
    }

    $condorStatus = $script:CondorCommands["condor_status"]
    $status = & $condorStatus -af Name Machine Cpus Memory Disk OpSys YADOF_RAMDISK 2>$null
    if ($LASTEXITCODE -eq 0 -and $status) {
        Write-Host ""
        Write-Host "Visible slots:"
        $status | ForEach-Object { Write-Host "  $_" }
    }
}

Assert-Administrator
Initialize-CondorCommands
Write-Host "YADOF worker RAM disk execute setup"
Write-Host "Target execute directory: $ExecuteDir"

Ensure-ExecuteDirectory -PathText $ExecuteDir

$condorExecuteDir = $ExecuteDir.TrimEnd("\") -replace "\\", "/"
$body = @"
# Generated by project/tools/htcondor_pool/configure_worker_ramdisk_execute.ps1
# Run setup_worker_ramdisk_execute.cmd on every execute machine: 1, 3, and 6.
EXECUTE = $condorExecuteDir
YADOF_RAMDISK = True
YADOF_EXECUTE_DIR = "$condorExecuteDir"
STARTD_ATTRS = YADOF_RAMDISK, YADOF_EXECUTE_DIR
"@

$targetPath = Get-CondorLocalConfigTarget
Set-ManagedConfigBlock -TargetPath $targetPath -BlockBody $body

if (-not $NoRestart) {
    Restart-Condor
}

Show-Verification

Write-Host ""
Write-Host "Done. Run this same CMD on machines 1, 3, and 6."
