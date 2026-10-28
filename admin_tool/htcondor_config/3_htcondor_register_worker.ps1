#requires -Version 5.1

# Script settings -------------------------------------------------------------
# The manager and this worker are added automatically. Add other name patterns
# only when your site security policy needs them. IPs are rejected.
$AdditionalAllowedMachineNames = @()

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
    do {
        $ManagerMachineName = (Read-Host "Enter the manager machine name (not an IP address)").Trim()
    } while (-not $ManagerMachineName)

    Show-YadofNetworkAdapters
    do {
        $PoolNetworkAdapterName = (Read-Host "Enter this machine's cluster LAN adapter name").Trim()
    } while (-not $PoolNetworkAdapterName)

    Set-YadofPoolRole -Role Worker -ManagerMachineName $ManagerMachineName `
        -NetworkAdapterName $PoolNetworkAdapterName `
        -AllowedMachineNames $AdditionalAllowedMachineNames -Port $CollectorPort
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
