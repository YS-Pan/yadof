#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$suite = Split-Path -Parent $PSScriptRoot
$module = Import-Module (Join-Path $suite '_htcondor_hostname_common.psm1') -Force -PassThru
$script:checks = 0
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
    $script:checks++
}

foreach ($source in Get-ChildItem -LiteralPath $suite -Recurse -File | Where-Object Extension -in @('.ps1', '.psm1')) {
    $tokens = $null; $errors = $null
    [Management.Automation.Language.Parser]::ParseFile($source.FullName, [ref]$tokens, [ref]$errors) | Out-Null
    Assert-True (@($errors).Count -eq 0) "Parse errors in $($source.Name): $errors"
}

$configVal = (Get-Command condor_config_val.exe -ErrorAction Stop).Source
$release = Split-Path -Parent (Split-Path -Parent $configVal)
$fixtureInterface = ([guid](Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -First 1).InterfaceGuid).ToString('B')
$ErrorActionPreference = 'Continue'
$productionSources = @(& $configVal -config 2>$null) | ForEach-Object { $_.Trim() } |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
$ErrorActionPreference = 'Stop'
$productionHashes = @{}
foreach ($path in $productionSources) { $productionHashes[$path] = (Get-FileHash -LiteralPath $path).Hash }
$service = Get-Service condor
$serviceState = "$($service.Status)|$($service.StartType)"
$masterPids = @(Get-Process condor_master -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$priorConfig = $env:CONDOR_CONFIG
trap { Write-Output $_.ScriptStackTrace; break }
$work = Join-Path ([IO.Path]::GetFullPath($OutputDirectory)) ('test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -Force | Out-Null
$root = Join-Path $work 'condor_config'
$local = Join-Path $work 'condor_config.local'
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($root, @"
RELEASE_DIR = $($release.Replace('\', '/'))
LOCAL_DIR = $($release.Replace('\', '/'))
LOCAL_CONFIG_FILE = $($local.Replace('\', '/'))
LOCAL_CONFIG_DIR =
"@, $utf8)

# All OS/service/network side effects are replaced before the public mutators
# run. Configuration writing and the native Condor parser use only this fixture.
& $module {
    param($ConfigVal, $Release, $Root, $Local, $Interface)
    $script:CondorCommands['condor_config_val'] = $ConfigVal
    $script:CondorRootDirectory = $Release
    $script:CondorRootConfig = $Root
    $script:CondorLocalConfig = $Local
    $script:FixtureInterface = $Interface
    $script:OriginalWaitRegistration = (Get-Command Wait-YadofPoolRegistration).ScriptBlock
    $script:TestCalls = New-Object 'System.Collections.Generic.List[string]'
    function script:Initialize-YadofCondor { $env:CONDOR_CONFIG = $script:CondorRootConfig }
    function script:Test-YadofAdministrator { return $true }
    function script:Assert-ManagerResolves { param($ManagerMachineName) }
    function script:Get-UniqueMachineNames {
        param($Names, $ManagerMachineName)
        return @(@($Names) + @($ManagerMachineName, $env:COMPUTERNAME) | Where-Object { $_ } | Select-Object -Unique)
    }
    function script:Assert-YadofManagerNameMatchesLocalAdapter {
        param($ManagerMachineName, $NetworkSelection)
        $script:TestCalls.Add('manager-adapter-check')
    }
    function script:Resolve-YadofNetworkAdapter {
        param($AdapterName, $NetworkInterface, [switch]$Quiet)
        return [pscustomobject]@{Name='fixture-lan';InterfaceGuid=$script:FixtureInterface}
    }
    function script:Set-YadofFirewallRule { param($Port) $script:TestCalls.Add('firewall') }
    function script:Restart-YadofCondor { $script:TestCalls.Add('restart') }
    function script:Stop-YadofCondor { $script:TestCalls.Add('stop') }
    function script:Remove-YadofFirewallRule { $script:TestCalls.Add('remove-firewall') }
    function script:Show-EffectiveConfiguration { }
    function script:Wait-YadofPoolRegistration { param($Role, $ManagerMachineName, $Port) $script:TestCalls.Add("registration:$Role") }
    function script:Assert-ResourceValues {
        param($ExecuteDirectory, $DeclaredCpus, $DeclaredMemoryMb, $DeclaredDiskMb)
        return $ExecuteDirectory
    }
    function script:Set-ExecuteDirectoryPermissions { param($ExecuteDirectory) $script:TestCalls.Add('execute-acl') }
} $configVal $release $root $local $fixtureInterface

function Reset-Fixture {
    param([string[]]$Daemons, [bool]$Resources = $false)
    $role = if ($Daemons -contains 'COLLECTOR') { 'Manager' }
        elseif ($Daemons -contains 'STARTD') { 'Worker' }
        elseif ($Daemons -contains 'SCHEDD') { 'Submit' } else { 'Detached' }
    $text = @"
# independent settings must survive replacement of the managed block
CUSTOM_KEEP = untouched
# BEGIN YADOF HTCONDOR HOSTNAME POOL
YADOF_POOL_ROLE = $role
YADOF_MANAGER_NAME = $env:COMPUTERNAME
CONDOR_HOST = $env:COMPUTERNAME
COLLECTOR_HOST = $($env:COMPUTERNAME):9618
DAEMON_LIST = $($Daemons -join ', ')
YADOF_ALLOWED_MACHINE_NAMES = $env:COMPUTERNAME
NETWORK_INTERFACE = $fixtureInterface
FLOCK_TO = secondary.example
FLOCK_COLLECTOR_HOSTS = secondary.example:9618
FLOCK_NEGOTIATOR_HOSTS = secondary.example
YADOF_RESOURCES_CONFIGURED = $Resources
"@
    if ($Resources) {
        $text += @"

YADOF_DECLARED_CPUS = 2
YADOF_DECLARED_MEMORY_MB = 1024
YADOF_DECLARED_DISK_MB = 2048
EXECUTE = D:/fixture-execute
NUM_CPUS = 2
MEMORY = 1024
DISK = 2097152
NUM_SLOTS = 1
NUM_SLOTS_TYPE_1 = 1
SLOT_TYPE_1 = 100%
SLOT_TYPE_1_PARTITIONABLE = True
"@
    }
    $text += "`r`n# END YADOF HTCONDOR HOSTNAME POOL`r`n"
    [IO.File]::WriteAllText($local, $text, $utf8)
    & $module { $script:TestCalls.Clear() }
}
function Read-Value {
    param([string]$Name, [switch]$AllowUndefined)
    $priorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $value = & $configVal -root-config $root $Name 2>$null
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $priorPreference }
    if ($code -ne 0) {
        if ($AllowUndefined) { return '' }
        throw "Native parser failed for ${Name}: $value"
    }
    return ([string]$value).Trim()
}
function Assert-Resources {
    Assert-True ((Read-Value 'NUM_CPUS') -eq '2') 'Declared CPUs were lost.'
    Assert-True ((Read-Value 'MEMORY') -eq '1024') 'Declared memory was lost.'
    Assert-True ((Read-Value 'DISK') -eq '2097152') 'Declared disk/unit conversion was lost.'
    Assert-True ((Read-Value 'EXECUTE') -eq 'D:/fixture-execute') 'Execute directory was lost.'
    Assert-True ((Read-Value 'SLOT_TYPE_1_PARTITIONABLE') -ieq 'True') 'Partitionable slot configuration was lost.'
}

try {
    # All eight combinations of the three independent capabilities, followed by
    # each role-registration action twice, including legacy unmarked schedds.
    foreach ($mask in 0..7) {
        foreach ($action in @('Manager', 'Worker', 'Submit')) {
            $initial = @('MASTER', 'KBDD')
            if ($mask -band 1) { $initial += @('COLLECTOR', 'NEGOTIATOR') }
            if ($mask -band 2) { $initial += 'SCHEDD' }
            if ($mask -band 4) { $initial += 'STARTD' }
            Reset-Fixture $initial ([bool]($mask -band 4))
            if ($mask -eq 2) {
                # Existing native submit machines need not already have metadata.
                $raw = [IO.File]::ReadAllText($local) -replace '(?m)^YADOF_POOL_ROLE = .*\r?\n', ''
                [IO.File]::WriteAllText($local, $raw, $utf8)
            }
            $expected = @($initial)
            switch ($action) {
                'Manager' { $expected += @('COLLECTOR', 'NEGOTIATOR', 'SCHEDD') }
                'Worker' { $expected += 'STARTD' }
                'Submit' { $expected += 'SCHEDD' }
            }
            $expected = @($expected | Sort-Object -Unique)
            $firstBody = $null
            foreach ($repeat in 1..2) {
                Set-YadofPoolRole -Role $action -ManagerMachineName $env:COMPUTERNAME -NetworkAdapterName 'fixture-lan'
                $actual = @((Read-Value 'DAEMON_LIST') -split '[,\s]+' | Sort-Object -Unique)
                Assert-True (($actual -join ',') -eq ($expected -join ',')) "Lost roles: mask=$mask action=$action repeat=$repeat"
                Assert-True ((Read-Value 'CONDOR_HOST') -eq $env:COMPUTERNAME) 'Pool target changed.'
                Assert-True ((Read-Value 'FLOCK_TO') -eq 'secondary.example') 'Flocking target was cleared.'
                Assert-True ((Read-Value 'FLOCK_COLLECTOR_HOSTS') -eq 'secondary.example:9618') 'Flocking collector was cleared.'
                Assert-True ((Read-Value 'FLOCK_NEGOTIATOR_HOSTS') -eq 'secondary.example') 'Flocking negotiator was cleared.'
                Assert-True ((Read-Value 'CUSTOM_KEEP') -eq 'untouched') 'Unmanaged settings were changed.'
                if ($mask -band 4) { Assert-Resources }
                $body = [IO.File]::ReadAllText($local)
                if ($null -ne $firstBody) { Assert-True ($body -ceq $firstBody) 'Repeated role setup is not idempotent.' }
                $firstBody = $body
            }
            if ($expected -contains 'COLLECTOR') { Assert-True ((Read-Value 'YADOF_POOL_ROLE') -eq 'Manager') 'Manager identity was downgraded.' }
        }
    }

    # Resources must also preserve submit-only and full manager nodes.
    foreach ($initial in @(@('MASTER', 'SCHEDD'), @('MASTER', 'COLLECTOR', 'NEGOTIATOR', 'SCHEDD', 'STARTD'))) {
        Reset-Fixture $initial
        Set-YadofExecuteResources -ManagerMachineName $env:COMPUTERNAME -NetworkAdapterName 'fixture-lan' `
            -ExecuteDirectory 'D:\fixture-execute' -DeclaredCpus 2 -DeclaredMemoryMb 1024 -DeclaredDiskMb 2048
        $actual = (Read-Value 'DAEMON_LIST') -split '[,\s]+'
        foreach ($daemon in @($initial) + @('STARTD')) { Assert-True ($actual -contains $daemon) "Resource setup lost $daemon" }
        Assert-Resources
    }

    Reset-Fixture @('MASTER', 'COLLECTOR', 'NEGOTIATOR', 'SCHEDD', 'STARTD') $true
    $before = [IO.File]::ReadAllText($local)
    foreach ($action in @('Manager', 'Worker', 'Submit', 'Resources')) {
        $threw = $false
        try {
            if ($action -eq 'Resources') {
                Set-YadofExecuteResources -ManagerMachineName 'different-pool.example' -NetworkAdapterName 'fixture-lan' `
                    -ExecuteDirectory 'D:\fixture-execute' -DeclaredCpus 2 -DeclaredMemoryMb 1024 -DeclaredDiskMb 2048
            }
            else { Set-YadofPoolRole -Role $action -ManagerMachineName 'different-pool.example' -NetworkAdapterName 'fixture-lan' }
        }
        catch { $threw = $_.Exception.Message -match 'already uses manager' }
        Assert-True $threw 'An additive operation must reject an unintended pool switch.'
        Assert-True ([IO.File]::ReadAllText($local) -ceq $before) 'Rejected pool switch changed config.'
        $calls = @(& $module { @($script:TestCalls.ToArray()) })
        Assert-True ($calls.Count -eq 0) 'Rejected pool switch performed an OS/service mutation.'
    }

    # Explicit leave remains the operation that removes all three capabilities.
    Disable-YadofPoolMembership
    Assert-True ((Read-Value 'DAEMON_LIST') -eq 'MASTER') 'Leave retained active roles.'
    Assert-True ((Read-Value 'FLOCK_TO' -AllowUndefined) -eq '') 'Leave retained flocking.'
    Assert-True ((Read-Value 'YADOF_RESOURCES_CONFIGURED') -ieq 'False') 'Leave retained resource declaration.'

    # Exercise the real registration command routing using a local status stub.
    $statusStub = Join-Path $work 'fixture-status.ps1'
    $statusArguments = Join-Path $work 'status-arguments.txt'
    [IO.File]::WriteAllText($statusStub,
        ("[IO.File]::WriteAllText('" + $statusArguments.Replace("'", "''") + "', (`$args -join ' ')); `$env:COMPUTERNAME; `$global:LASTEXITCODE = 0"), $utf8)
    & $module {
        param($StatusStub)
        $script:CondorCommands['condor_status'] = $StatusStub
        Set-Item Function:script:Wait-YadofPoolRegistration -Value $script:OriginalWaitRegistration
    } $statusStub
    foreach ($role in @('Manager', 'Worker', 'Submit')) {
        & $module { param($Role) Wait-YadofPoolRegistration -Role $Role -ManagerMachineName $env:COMPUTERNAME -Port 9618 -TimeoutSeconds 5 } $role
        $arguments = [IO.File]::ReadAllText($statusArguments)
        if ($role -eq 'Manager') { Assert-True ($arguments -match '-collector -af Name') 'Manager verification must query collector ads.' }
        elseif ($role -eq 'Submit') { Assert-True ($arguments -match '-schedd -af Machine') 'Submit verification must query schedd ads.' }
        else { Assert-True ($arguments -match '-af Machine' -and $arguments -notmatch '-schedd|-collector') 'Worker verification must query execution ads.' }
    }
}
finally {
    [Environment]::SetEnvironmentVariable('CONDOR_CONFIG', $priorConfig, 'Process')
    foreach ($path in $productionSources) {
        Assert-True ((Get-FileHash -LiteralPath $path).Hash -eq $productionHashes[$path]) 'Production configuration changed.'
    }
    $service = Get-Service condor
    Assert-True ("$($service.Status)|$($service.StartType)" -eq $serviceState) 'Production service state changed.'
    $afterPids = @(Get-Process condor_master -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    Assert-True (($afterPids -join ',') -eq ($masterPids -join ',')) 'Production master restarted.'
    Remove-Module $module
}
Write-Output "PASS: $script:checks offline checks; artifacts: $work"
