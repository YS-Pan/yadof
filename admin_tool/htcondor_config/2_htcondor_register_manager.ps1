#requires -Version 5.1

# Script settings -------------------------------------------------------------
# Replace "*" with explicit names for a restricted pool, for example:
# $AllowedMachineNames = @("MANAGER01", "WORKER01", "WORKER02")
# Host-name wildcards such as "*.example.local" are accepted. IPs are rejected.
$AllowedMachineNames = @("*")

$CollectorPort = 9618
$PauseWhenFinished = $true
# End script settings ---------------------------------------------------------

$ErrorActionPreference = "Stop"
$modulePath = Join-Path $PSScriptRoot "_htcondor_hostname_common.psm1"
try {
    Import-Module $modulePath -Force
}
catch {
    Write-Host "Cannot load the required module: $modulePath" -ForegroundColor Red
    Write-Host $_ -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

if (-not (Test-YadofAdministrator)) {
    try {
        Start-YadofElevatedScript -ScriptPath $PSCommandPath
    }
    catch {
        Add-Type -AssemblyName PresentationFramework -ErrorAction SilentlyContinue
        [System.Windows.MessageBox]::Show($_.Exception.Message, "HTCondor setup error") | Out-Null
    }
    exit
}

$failed = $false
try {
    $managerInput = Read-Host "Enter the manager machine name [$env:COMPUTERNAME]"
    $ManagerMachineName = if ($managerInput.Trim()) { $managerInput.Trim() } else { $env:COMPUTERNAME }

    Show-YadofNetworkAdapters
    do {
        $PoolNetworkAdapterName = (Read-Host "Enter this machine's cluster LAN adapter name").Trim()
    } while (-not $PoolNetworkAdapterName)

    if ($AllowedMachineNames -contains "*") {
        Write-Warning "All resolvable host names are allowed. Replace '*' with explicit machine names for a restricted pool."
    }
    Set-YadofPoolRole -Role Manager -ManagerMachineName $ManagerMachineName `
        -NetworkAdapterName $PoolNetworkAdapterName `
        -AllowedMachineNames $AllowedMachineNames -Port $CollectorPort
}
catch {
    $failed = $true
    Write-Host ""
    Write-Error $_
}
finally {
    if ($PauseWhenFinished) {
        Read-Host "Press Enter to close"
    }
}
if ($failed) { exit 1 }
