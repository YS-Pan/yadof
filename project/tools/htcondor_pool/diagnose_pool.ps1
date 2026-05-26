[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $PSCommandPath
$logPath = Join-Path $scriptDir ("diagnose_pool_{0}.txt" -f $env:COMPUTERNAME)
$managerIpFile = Join-Path $scriptDir "manager_ip.txt"
$condorRoot = if (Test-Path -LiteralPath "D:\condor" -PathType Container) {
    "D:\condor"
}
elseif ($env:CONDOR_LOCATION) {
    $env:CONDOR_LOCATION
}
else {
    "D:\condor"
}

$condorBin = Join-Path $condorRoot "bin"
$condorConfig = Join-Path $condorRoot "condor_config"
$condorLocalConfig = Join-Path $condorRoot "condor_config.local"
$condorStatus = Join-Path $condorBin "condor_status.exe"
$condorConfigVal = Join-Path $condorBin "condor_config_val.exe"
$condorPing = Join-Path $condorBin "condor_ping.exe"

try {
    Start-Transcript -LiteralPath $logPath -Force | Out-Null
}
catch {
    Write-Warning "Could not start transcript log at ${logPath}: $($_.Exception.Message)"
}

try {
    if (Test-Path -LiteralPath $condorConfig) {
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
    if (Test-Path -LiteralPath $path) {
        Write-Host "OK      $path"
    }
    else {
        Write-Host "MISSING $path"
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
if (Test-Path -LiteralPath $condorConfigVal) {
    foreach ($name in @("CONDOR_HOST", "COLLECTOR_HOST", "DAEMON_LIST", "NETWORK_INTERFACE", "ALLOW_READ", "ALLOW_WRITE", "ALLOW_DAEMON", "ALLOW_ADVERTISE_MASTER", "ALLOW_ADVERTISE_STARTD", "ALLOW_ADVERTISE_SCHEDD", "LOCAL_CONFIG_FILE")) {
        $value = & $condorConfigVal $name 2>$null
        Write-Host "$name = $value"
    }
}
else {
    Write-Host "condor_config_val.exe not found."
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
if (Test-Path -LiteralPath $condorStatus) {
    if ($managerIp) {
        & $condorStatus -pool "${managerIp}:9618" -af Name Machine Cpus Memory OpSys
    }
    else {
        & $condorStatus -af Name Machine Cpus Memory OpSys
    }
}
else {
    Write-Host "condor_status.exe not found."
}
Write-Host ""

Write-Host "=== Optional Collector Permission Ping ==="
if ($managerIp -and (Test-Path -LiteralPath $condorPing)) {
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
