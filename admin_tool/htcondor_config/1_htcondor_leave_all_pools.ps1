#requires -Version 5.1

# User settings ---------------------------------------------------------------
$RequireConfirmation = $true
$CollectorPort = 9618
$PauseWhenFinished = $true
# End user settings -----------------------------------------------------------

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
    Write-Host "This stops the HTCondor service and prevents pool membership after reboot." -ForegroundColor Yellow
    Write-Host "Running jobs on this machine will be terminated." -ForegroundColor Yellow
    if ($RequireConfirmation) {
        $confirmation = Read-Host "Type LEAVE to continue"
        if ($confirmation -cne "LEAVE") {
            Write-Host "Cancelled."
            exit
        }
    }
    Disable-YadofPoolMembership -Port $CollectorPort
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
