[CmdletBinding()]
param(
    [string]$CondorLocation
)

$ErrorActionPreference = "Stop"

function Get-CondorBinCandidates {
    $dirs = New-Object System.Collections.Generic.List[string]

    if ($CondorLocation) {
        $dirs.Add((Join-Path $CondorLocation "bin"))
    }
    if ($env:CONDOR_LOCATION) {
        $dirs.Add((Join-Path $env:CONDOR_LOCATION "bin"))
    }
    foreach ($dir in @(
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

function Find-CondorBin {
    $command = Get-Command condor_config_val -ErrorAction SilentlyContinue
    if ($command) {
        return (Split-Path -Parent $command.Source)
    }
    foreach ($dir in Get-CondorBinCandidates) {
        $exe = Join-Path $dir "condor_config_val.exe"
        if (Test-Path -LiteralPath $exe) {
            return (Resolve-Path -LiteralPath $dir).Path
        }
    }
    $searched = (Get-CondorBinCandidates) -join [Environment]::NewLine
    throw "Could not find condor_config_val.exe. Searched:`n$searched`nIf HTCondor is installed elsewhere, pass -CondorLocation <condor-root>."
}

$condorBin = Find-CondorBin
$condorRoot = Split-Path -Parent $condorBin
if (($env:Path -split ";") -notcontains $condorBin) {
    $env:Path = "$condorBin;$env:Path"
}
$env:CONDOR_LOCATION = $condorRoot
$condorConfig = Join-Path $condorRoot "condor_config"
if (Test-Path -LiteralPath $condorConfig -PathType Leaf) {
    $env:CONDOR_CONFIG = $condorConfig
}

Write-Host "HTCondor binary directory: $condorBin"
Write-Host "Current-process CONDOR_LOCATION: $env:CONDOR_LOCATION"
Write-Host "Current-process CONDOR_CONFIG: $env:CONDOR_CONFIG"
Write-Host ""
Write-Host "Testing HTCondor command lookup..."
& (Join-Path $condorBin "condor_config_val.exe") -version
if ($LASTEXITCODE -ne 0) {
    throw "condor_config_val.exe was found but did not run successfully."
}

Write-Host ""
Write-Host "Done. No system environment variables were changed. For future terminals, add the HTCondor bin directory to PATH using your normal machine setup process."
