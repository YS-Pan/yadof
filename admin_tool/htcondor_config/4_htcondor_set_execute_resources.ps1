#requires -Version 5.1

# Script settings -------------------------------------------------------------
$CollectorPort = 9618
$PauseWhenFinished = $true
# End script settings ---------------------------------------------------------

# Units follow the HTCondor manual:
#   DeclaredMemoryMb: MiB
#   DeclaredDiskMb:   MiB here; this script converts it to HTCondor's KiB.

function Read-TextValue {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [string]$DefaultValue = ""
    )

    while ($true) {
        $label = if ($DefaultValue) { "$Prompt [$DefaultValue]" } else { $Prompt }
        $value = (Read-Host $label).Trim()
        if ($value) {
            return $value
        }
        if ($DefaultValue) {
            return $DefaultValue
        }
        Write-Warning "A value is required."
    }
}

function Read-PositiveInt64 {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Nullable[Int64]]$DefaultValue = $null
    )

    while ($true) {
        $label = if ($null -ne $DefaultValue) { "$Prompt [$DefaultValue]" } else { $Prompt }
        $text = (Read-Host $label).Trim()
        if (-not $text -and $null -ne $DefaultValue) {
            return [int64]$DefaultValue
        }
        $parsed = [int64]0
        if ([int64]::TryParse($text, [ref]$parsed) -and $parsed -gt 0) {
            return $parsed
        }
        Write-Warning "Enter a positive integer."
    }
}

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
    if ($current.Role -notin @("Manager", "Worker", "Submit")) {
        throw "Run script 2 (manager), 3 (worker), or 5 (submit) before declaring execute resources."
    }

    $ManagerMachineName = Read-TextValue -Prompt "Enter the manager machine name (not an IP address)" `
        -DefaultValue $current.ManagerMachineName

    Show-YadofNetworkAdapters
    $PoolNetworkAdapterName = Read-TextValue `
        -Prompt "Enter this machine's cluster LAN adapter name" `
        -DefaultValue $current.NetworkAdapterName

    $resourceDefaults = $current.Resources
    $executeDefault = if ($resourceDefaults) { [string]$resourceDefaults.ExecuteDirectory } else { "R:\condor_execute" }
    $cpuDefault = if ($resourceDefaults) { [Nullable[Int64]]([int64]$resourceDefaults.DeclaredCpus) } else { $null }
    $memoryDefault = if ($resourceDefaults) { [Nullable[Int64]]([int64]$resourceDefaults.DeclaredMemoryMb) } else { $null }
    $diskDefault = if ($resourceDefaults) { [Nullable[Int64]]([int64]$resourceDefaults.DeclaredDiskMb) } else { $null }

    $ExecuteDirectory = Read-TextValue -Prompt "Enter the HTCondor execute directory" -DefaultValue $executeDefault
    $cpus64 = Read-PositiveInt64 -Prompt "Enter declared logical CPUs" -DefaultValue $cpuDefault
    if ($cpus64 -gt [int]::MaxValue) {
        throw "The CPU declaration is too large: $cpus64"
    }
    $DeclaredCpus = [int]$cpus64
    $DeclaredMemoryMb = Read-PositiveInt64 -Prompt "Enter declared memory (MiB)" -DefaultValue $memoryDefault
    $DeclaredDiskMb = Read-PositiveInt64 -Prompt "Enter declared execute disk (MiB)" -DefaultValue $diskDefault

    Set-YadofExecuteResources -ManagerMachineName $ManagerMachineName `
        -NetworkAdapterName $PoolNetworkAdapterName `
        -ExecuteDirectory $ExecuteDirectory `
        -DeclaredCpus $DeclaredCpus `
        -DeclaredMemoryMb $DeclaredMemoryMb `
        -DeclaredDiskMb $DeclaredDiskMb `
        -Port $CollectorPort
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
