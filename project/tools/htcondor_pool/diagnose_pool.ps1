[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $PSCommandPath
$logPath = Join-Path $scriptDir ("diagnose_pool_{0}.txt" -f $env:COMPUTERNAME)
$managerIpFile = Join-Path $scriptDir "manager_ip.txt"

function Get-CondorBinCandidates {
    $dirs = New-Object System.Collections.Generic.List[string]
    if ($env:CONDOR_LOCATION) {
        $dirs.Add((Join-Path $env:CONDOR_LOCATION "bin"))
    }
    foreach ($dir in @(
        "$env:ProgramFiles\HTCondor\bin",
        "$env:ProgramFiles\Condor\bin"
    )) {
        if ($dir) {
            $dirs.Add($dir)
        }
    }
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $dirs.Add((Join-Path $programFilesX86 "HTCondor\bin"))
        $dirs.Add((Join-Path $programFilesX86 "Condor\bin"))
    }
    return @($dirs | Where-Object { $_ } | Select-Object -Unique)
}

function Find-CondorCommand {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    foreach ($dir in Get-CondorBinCandidates) {
        $candidate = Join-Path $dir "$Name.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

$condorStatus = Find-CondorCommand "condor_status"
$condorConfigVal = Find-CondorCommand "condor_config_val"
$condorPing = Find-CondorCommand "condor_ping"
$condorBin = if ($condorConfigVal) { Split-Path -Parent $condorConfigVal } elseif ($condorStatus) { Split-Path -Parent $condorStatus } else { $null }
$condorRoot = if ($condorBin) { Split-Path -Parent $condorBin } elseif ($env:CONDOR_LOCATION) { $env:CONDOR_LOCATION } else { $null }

$configCandidates = @(
    [Environment]::GetEnvironmentVariable("CONDOR_CONFIG", "Machine"),
    $env:CONDOR_CONFIG
)
if ($condorRoot) {
    $configCandidates += @(
        (Join-Path $condorRoot "condor_config"),
        (Join-Path $condorRoot "etc\condor_config")
    )
}
$configCandidates = @($configCandidates | Where-Object { $_ } | Select-Object -Unique)
$condorConfig = $null
foreach ($candidate in $configCandidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $condorConfig = $candidate
        break
    }
}
$condorLocalConfig = if ($condorRoot) { Join-Path $condorRoot "condor_config.local" } else { $null }

try {
    Start-Transcript -LiteralPath $logPath -Force | Out-Null
}
catch {
    Write-Warning "Could not start transcript log at ${logPath}: $($_.Exception.Message)"
}

try {
    if ($condorConfig) {
        $env:CONDOR_CONFIG = $condorConfig
    }

function Read-ManagerIp {
    if (-not (Test-Path -LiteralPath $managerIpFile -PathType Leaf)) {
        return $null
    }
    return @(Get-Content -LiteralPath $managerIpFile |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") } |
        Select-Object -First 1)[0]
}

function Show-Command {
    param([scriptblock]$Command)
    try {
        & $Command
    }
    catch {
        Write-Host "ERROR: $($_.Exception.Message)"
    }
}

$managerIp = Read-ManagerIp

Write-Host "=== YADOF HTCondor Pool Diagnosis ==="
Write-Host "ComputerName: $env:COMPUTERNAME"
Write-Host "ScriptDir: $scriptDir"
Write-Host "CondorRoot: $condorRoot"
Write-Host "CONDOR_CONFIG: $env:CONDOR_CONFIG"
Write-Host "manager_ip.txt: $managerIp"
Write-Host ""

Write-Host "=== Files ==="
foreach ($path in @($condorStatus, $condorConfigVal, $condorConfig, $condorLocalConfig, $managerIpFile)) {
    if ($path -and (Test-Path -LiteralPath $path)) {
        Write-Host "OK      $path"
    }
    elseif ($path) {
        Write-Host "MISSING $path"
    }
    else {
        Write-Host "MISSING <not resolved>"
    }
}
Write-Host ""

Write-Host "=== Local IPv4 ==="
Show-Command {
    Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object IPAddress, PrefixLength, InterfaceAlias |
        Format-Table -AutoSize
}

if ($managerIp) {
    Write-Host "=== Connectivity To Manager ${managerIp}:9618 ==="
    Show-Command {
        Test-NetConnection -ComputerName $managerIp -Port 9618 |
            Select-Object ComputerName, RemoteAddress, TcpTestSucceeded |
            Format-List
    }
}
else {
    Write-Host "=== Connectivity To Manager ==="
    Write-Host "manager_ip.txt is missing. Run setup_machine_1_manager.cmd first, then copy manager_ip.txt to this folder on workers."
}
Write-Host ""

Write-Host "=== HTCondor Config Values ==="
if ($condorConfigVal -and (Test-Path -LiteralPath $condorConfigVal)) {
    foreach ($name in @("CONDOR_HOST", "COLLECTOR_HOST", "DAEMON_LIST", "NETWORK_INTERFACE", "ALLOW_READ", "ALLOW_WRITE", "ALLOW_DAEMON", "ALLOW_ADVERTISE_MASTER", "ALLOW_ADVERTISE_STARTD", "ALLOW_ADVERTISE_SCHEDD", "LOCAL_CONFIG_FILE")) {
        $value = & $condorConfigVal $name 2>$null
        Write-Host "$name = $value"
    }
}
else {
    Write-Host "condor_config_val.exe not found. Put HTCondor on PATH or set CONDOR_LOCATION."
}
Write-Host ""

Write-Host "=== Local Condor Processes ==="
Show-Command {
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -like "condor_*.exe" } |
        Select-Object ProcessId, Name, ExecutablePath |
        Format-Table -AutoSize
}

Write-Host "=== Pool Slots Seen From This Machine ==="
if ($condorStatus -and (Test-Path -LiteralPath $condorStatus)) {
    if ($managerIp) {
        & $condorStatus -pool "${managerIp}:9618" -af Name Machine Cpus Memory OpSys
    }
    else {
        & $condorStatus -af Name Machine Cpus Memory OpSys
    }
}
else {
    Write-Host "condor_status.exe not found. Put HTCondor on PATH or set CONDOR_LOCATION."
}
Write-Host ""

Write-Host "=== Optional Collector Permission Ping ==="
if ($managerIp -and $condorPing -and (Test-Path -LiteralPath $condorPing)) {
    & $condorPing -pool "${managerIp}:9618" -table READ WRITE ADVERTISE_STARTD 2>$null
}
else {
    Write-Host "Skipped. condor_ping.exe or manager IP is missing."
}

Write-Host ""
Write-Host "Diagnosis log saved to: $logPath"
}
finally {
    try {
        Stop-Transcript | Out-Null
    }
    catch {
    }
}
