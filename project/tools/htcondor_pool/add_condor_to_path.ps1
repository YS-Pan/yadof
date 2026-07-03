[CmdletBinding()]
param(
    [string]$CondorLocation
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an elevated Administrator shell."
    }
}

function Get-CondorBinCandidates {
    $dirs = New-Object System.Collections.Generic.List[string]

    if ($CondorLocation) {
        $dirs.Add((Join-Path $CondorLocation "bin"))
    }
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

function Find-CondorBin {
    foreach ($dir in Get-CondorBinCandidates) {
        $exe = Join-Path $dir "condor_config_val.exe"
        if (Test-Path -LiteralPath $exe) {
            return (Resolve-Path -LiteralPath $dir).Path
        }
    }

    $searched = (Get-CondorBinCandidates) -join [Environment]::NewLine
    throw "Could not find condor_config_val.exe. Searched:`n$searched`nIf HTCondor is installed elsewhere, run add_condor_to_path.ps1 -CondorLocation C:\Path\To\Condor"
}

function Add-DirectoryToMachinePath {
    param([string]$Directory)

    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $parts = @($machinePath -split ";" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $alreadyPresent = $false
    foreach ($part in $parts) {
        if ($part.TrimEnd("\") -ieq $Directory.TrimEnd("\")) {
            $alreadyPresent = $true
            break
        }
    }

    if (-not $alreadyPresent) {
        $newPath = (@($parts) + $Directory) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
        Write-Host "Added to system PATH: $Directory"
    }
    else {
        Write-Host "Already in system PATH: $Directory"
    }

    $currentParts = @($env:Path -split ";" | Where-Object { $_ })
    if ($currentParts -notcontains $Directory) {
        $env:Path = "$Directory;$env:Path"
    }
}

function Set-CondorLocation {
    param([string]$BinDirectory)
    $root = Split-Path -Parent $BinDirectory
    [Environment]::SetEnvironmentVariable("CONDOR_LOCATION", $root, "Machine")
    $env:CONDOR_LOCATION = $root
    Write-Host "Set system CONDOR_LOCATION: $root"

    $condorConfig = Join-Path $root "condor_config"
    if (Test-Path -LiteralPath $condorConfig) {
        [Environment]::SetEnvironmentVariable("CONDOR_CONFIG", $condorConfig, "Machine")
        $env:CONDOR_CONFIG = $condorConfig
        Write-Host "Set system CONDOR_CONFIG: $condorConfig"
    }
}

function Send-EnvironmentChanged {
    try {
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NativeMethods {
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr hWnd,
        UInt32 Msg,
        UIntPtr wParam,
        string lParam,
        UInt32 fuFlags,
        UInt32 uTimeout,
        out UIntPtr lpdwResult);
}
"@
        $result = [UIntPtr]::Zero
        [void][NativeMethods]::SendMessageTimeout(
            [IntPtr]0xffff,
            0x1A,
            [UIntPtr]::Zero,
            "Environment",
            0x0002,
            5000,
            [ref]$result
        )
    }
    catch {
        Write-Warning "Could not broadcast environment update. Open a new terminal before testing PATH."
    }
}

Assert-Administrator
$condorBin = Find-CondorBin
Add-DirectoryToMachinePath -Directory $condorBin
Set-CondorLocation -BinDirectory $condorBin
Send-EnvironmentChanged

Write-Host ""
Write-Host "Testing HTCondor command lookup..."
& (Join-Path $condorBin "condor_config_val.exe") -version
if ($LASTEXITCODE -ne 0) {
    throw "condor_config_val.exe was found but did not run successfully."
}

Write-Host ""
Write-Host "Done. Open a new Command Prompt and run:"
Write-Host "  where condor_config_val"
Write-Host "  condor_config_val -version"
Write-Host "  condor_status -af Name Machine Cpus Memory OpSys"
