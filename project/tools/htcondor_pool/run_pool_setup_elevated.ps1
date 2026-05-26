[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Manager", "Worker")]
    [string]$Role,

    [Parameter(Mandatory = $true)]
    [string]$MachineLabel
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $PSCommandPath
$configureScript = Join-Path $scriptDir "configure_htcondor_pool.ps1"

$argumentList = @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    ('"{0}"' -f $configureScript),
    "-Role",
    $Role,
    "-MachineLabel",
    $MachineLabel
)

Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $argumentList `
    -WorkingDirectory $scriptDir `
    -Verb RunAs
