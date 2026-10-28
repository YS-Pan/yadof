#requires -Version 5.1

# Add local job submission while keeping existing management and execution.
$CollectorPort = 9618
$PauseWhenFinished = $true
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
    $current = Get-YadofCurrentConfiguration
    $managerInput = Read-Host "Enter the manager machine name [$($current.ManagerMachineName)]"
    $manager = if ($managerInput.Trim()) { $managerInput.Trim() } else { $current.ManagerMachineName }
    if (-not $manager) { throw "A manager machine name is required." }

    Show-YadofNetworkAdapters
    $adapterInput = Read-Host "Enter this machine's cluster LAN adapter name [$($current.NetworkAdapterName)]"
    $adapter = if ($adapterInput.Trim()) { $adapterInput.Trim() } else { $current.NetworkAdapterName }
    if (-not $adapter) { throw "A local cluster LAN adapter name is required." }

    Set-YadofPoolRole -Role Submit -ManagerMachineName $manager `
        -NetworkAdapterName $adapter -Port $CollectorPort
}
catch {
    $failed = $true
    Write-Host ""
    Write-Error $_
}
finally {
    if ($PauseWhenFinished) { Read-Host "Press Enter to close" }
}
if ($failed) { exit 1 }
