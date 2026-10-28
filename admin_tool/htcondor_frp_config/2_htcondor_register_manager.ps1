#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ManagerName, [string]$TrustDomain,
    [int]$VisitorPort, [int]$SharedPort,
    [string]$PrivateNetworkName, [string]$BrokerTargetAllowlist,
    [switch]$EnableSubmit, [string]$NetworkAdapterName,
    [string]$ExecuteDirectory, [long]$Cpus, [long]$MemoryMiB, [long]$DiskMiB,
    [string]$RootConfig, [string]$OutputDirectory,
    [switch]$DryRun, [switch]$NonInteractive, [switch]$Yes, [switch]$NoPause
)
$ErrorActionPreference = 'Stop'
try {
    & (Join-Path $PSScriptRoot '_invoke_htcondor_frp.ps1') -Action 'Manager' @PSBoundParameters
    exit $LASTEXITCODE
}
catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
