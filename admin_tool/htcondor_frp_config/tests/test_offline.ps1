#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$suite = Split-Path -Parent $PSScriptRoot
$modulePath = Join-Path $suite '_htcondor_frp_common.psm1'
$module = Import-Module $modulePath -Force -PassThru -DisableNameChecking
$script:checks = 0
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
    $script:checks++
}
function Assert-Throws {
    param([scriptblock]$Body, [string]$Message)
    $threw = $false
    try { & $Body | Out-Null } catch { $threw = $true }
    Assert-True $threw $Message
}

$work = Join-Path ([IO.Path]::GetFullPath($OutputDirectory)) ('test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -Force | Out-Null
foreach ($source in Get-ChildItem -LiteralPath $suite -Recurse -File | Where-Object Extension -in @('.ps1','.psm1')) {
    $tokens=$null; $errors=$null
    [Management.Automation.Language.Parser]::ParseFile($source.FullName,[ref]$tokens,[ref]$errors) | Out-Null
    Assert-True (@($errors).Count -eq 0) ("Parse errors in {0}: {1}" -f $source.Name, (($errors | ForEach-Object { $_.Message }) -join '; '))
}
$live = Get-FrpContext
$productionPaths = @($live.RootConfig, (Get-FrpValue $live 'LOCAL_CONFIG_FILE')) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
$before = @{}
foreach ($path in $productionPaths) { $before[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
$serviceBefore = Get-Service condor
$statusBefore = [string]$serviceBefore.Status
$startBefore = [string]$serviceBefore.StartType

$local = Join-Path $work 'legacy.local'
Write-FrpUtf8 $local @'
YADOF_POOL_ROLE = Worker
YADOF_MANAGER_NAME = manager.example
CONDOR_HOST = 127.0.0.1
COLLECTOR_HOST = 127.0.0.1:29618
CCB_ADDRESS = 127.0.0.1:29618
OUTBOUND_CCB_ADDRESS = 127.0.0.1:29618
SEC_DEFAULT_AUTHENTICATION = Required
ALLOW_ADMINISTRATOR = test-admin@example
ALLOW_DAEMON = test-daemon@example
STARTD_ATTRS = ExistingAttribute
'@
$root = Join-Path $work 'condor_config'
$release = Split-Path -Parent (Split-Path -Parent $live.ConfigVal)
Write-FrpUtf8 $root ("RELEASE_DIR = $($release.Replace('\','/'))`r`nLOCAL_DIR = $($release.Replace('\','/'))`r`nLOCAL_CONFIG_DIR =`r`nLOCAL_CONFIG_FILE = $($local.Replace('\','/'))`r`n")
$context = [pscustomobject]@{RootConfig=$root; ManagedConfig=(Join-Path $work 'condor_config.yadof_frp'); ConfigVal=$live.ConfigVal; Status=$live.Status; Service=[pscustomobject]@{Name='condor'}}
$resource = @{ Path='D:\condor\execute'; Cpus=2L; MemoryMiB=1024L; DiskMiB=2048L }
$worker = New-FrpSettings -Role Worker -ManagerName 'manager.example' -TrustDomain 'manager.example' -PrivateNetworkName 'isolated-worker'
Assert-True ($worker.CCB_ADDRESS -eq '127.0.0.1:29618' -and $worker.OUTBOUND_CCB_ADDRESS -eq $worker.CCB_ADDRESS) 'Worker must preserve both FRP/CCB paths.'
Assert-True ($worker.DAEMON_LIST -eq 'MASTER' -and $worker.START -eq 'False') 'Undeclared worker must not execute jobs.'
Assert-True ($worker.USE_OUTBOUND_CCB -eq 'False') 'Do not spawn an unintended local CCB.'
$plan = New-FrpPlan $context $worker $work
Assert-True ((Get-FrpValue $context 'ALLOW_DAEMON' $plan.PreviewRoot) -eq 'test-daemon@example') 'Daemon authorization must survive.'
Assert-True ((Get-FrpValue $context 'ALLOW_ADMINISTRATOR' $plan.PreviewRoot) -eq 'test-admin@example') 'Administrator authorization must survive.'
Assert-True ((Get-FrpValue $context 'SEC_DEFAULT_ENCRYPTION' $plan.PreviewRoot) -ieq 'Required') 'Encryption must remain required.'
$execution = New-FrpSettings -Role Worker -ManagerName 'manager.example' -TrustDomain 'manager.example' -PrivateNetworkName 'isolated-worker' -Resources $resource -StartdAttrs ExistingAttribute
$executePlan = New-FrpPlan $context $execution $work
Assert-True ((Get-FrpValue $context 'DISK' $executePlan.PreviewRoot) -eq '2097152') 'MiB to KiB conversion failed.'
Assert-True ($execution.STARTD_ATTRS -match 'ExistingAttribute' -and $execution.DAEMON_LIST -match 'STARTD') 'Resource configuration must preserve ads and enable execution.'
$manager = New-FrpSettings -Role Manager -ManagerName $env:COMPUTERNAME -TrustDomain $env:COMPUTERNAME -PrivateNetworkName 'manager-net' -BrokerTargetAllowlist '192.168.137.1' -Resources $resource
$managerPlan = New-FrpPlan $context $manager $work
Assert-True (-not $manager.CCB_ADDRESS -and -not $manager.OUTBOUND_CCB_ADDRESS -and $manager.CCB_OUTBOUND_PROXY -eq 'True') 'Manager must clear worker CCB endpoints and enable the broker.'
Assert-True ($manager.DAEMON_LIST -match 'SCHEDD' -and $manager.DAEMON_LIST -match 'STARTD') 'Manager must retain both submission and configured execution.'
$detached = New-FrpSettings -Role Detached -ManagerName $env:COMPUTERNAME -TrustDomain $env:COMPUTERNAME -PrivateNetworkName 'detached'
$leavePlan = New-FrpPlan $context $detached $work
Assert-True (-not $detached.CCB_ADDRESS -and -not $detached.OUTBOUND_CCB_ADDRESS -and $detached.DAEMON_LIST -eq 'MASTER') 'Detach must clear both CCB paths and active roles.'
$includeOnce = Add-FrpInclude ([IO.File]::ReadAllText($root)) $context.ManagedConfig
$includeTwice = Add-FrpInclude $includeOnce $context.ManagedConfig
Assert-True ($includeOnce -ceq $includeTwice) 'Root include must be idempotent.'
Assert-Throws { Add-FrpInclude "# BEGIN YADOF FRP CONFIG INCLUDE`r`ninvalid" $context.ManagedConfig } 'Malformed marker must fail.'
Assert-Throws { Assert-FrpResourcePath 'D:\' } 'Drive root must be rejected.'
Assert-Throws { Assert-FrpResourcePath '\\server\share\execute' } 'UNC execute directory must be rejected.'
Assert-Throws { Assert-FrpResourcePath "D:\execute`nSTART = True" } 'Configuration injection must be rejected.'
Assert-Throws { Assert-FrpResourcePath 'D:\$(BAD)' } 'Macro injection must be rejected.'
$bad = [ordered]@{YADOF_FRP_MANAGED="True`nALLOW_WRITE = *"}
Assert-Throws { ConvertTo-FrpConfigText $bad } 'Multiline config value must be rejected.'

# Confirm native argument quoting using the actual Windows PowerShell executable.
$echoScript = Join-Path $work 'echo-arguments.ps1'
Write-FrpUtf8 $echoScript '$args | ForEach-Object { [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($_)) }'
$sentinels = @('two words', 'D:\some path\', 'embedded"quote', 'literal$(macro)')
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$echo = Invoke-FrpCommand $powershell (@('-NoProfile','-ExecutionPolicy','Bypass','-File',$echoScript) + $sentinels)
$received = @($echo.Out -split '\r?\n' | ForEach-Object { [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($_)) })
Assert-True (($received -join '|') -ceq ($sentinels -join '|')) 'Native command arguments did not round trip.'

# Re-run role entry points against a prepared manager/execute fixture. They must
# retain explicit resources, including STARTD on a manager, and custom FRP ports.
$replayRoot = Join-Path $work 'replay-root'
$replayLocal = Join-Path $work 'replay.local'
$manager.YADOF_FRP_VISITOR_PORT = '30618'
Write-FrpUtf8 $replayLocal (ConvertTo-FrpConfigText $manager)
Write-FrpUtf8 $replayRoot ("RELEASE_DIR = $($release.Replace('\','/'))`r`nLOCAL_DIR = $($release.Replace('\','/'))`r`nLOCAL_CONFIG_DIR =`r`nLOCAL_CONFIG_FILE = $($replayLocal.Replace('\','/'))`r`n")
foreach ($entry in @('2_htcondor_register_manager.ps1','3_htcondor_register_worker.ps1')) {
    $run = Invoke-FrpCommand $powershell @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $suite $entry),'-DryRun','-RootConfig',$replayRoot,'-OutputDirectory',$work) -TimeoutSeconds 20
    Assert-True ($run.Code -eq 0) "Repeated role dry run failed: $($run.Out) $($run.Error)"
    Assert-True ($run.Out -match 'Execute enabled: True; daemons: .*STARTD') 'Repeated role setup lost explicit resources.'
    if ($entry -like '3_*') { Assert-True ($run.Out -match '127.0.0.1:30618') 'Custom visitor port was not preserved.' }
}
$negative = Invoke-FrpCommand $powershell @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $suite '3_htcondor_register_worker.ps1'),'-DryRun','-VisitorPort','9618','-SharedPort','9618','-OutputDirectory',$work)
Assert-True ($negative.Code -ne 0 -and $negative.Out -match 'different ports') 'Conflicting listener ports must fail before mutation.'
$negative = Invoke-FrpCommand $powershell @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $suite '4_htcondor_set_execute_resources.ps1'),'-DryRun','-ExecuteDirectory','D:\','-Cpus','1','-MemoryMiB','1','-DiskMiB','1','-OutputDirectory',$work)
Assert-True ($negative.Code -ne 0 -and $negative.Out -match 'drive root') 'Unsafe execute root must fail before mutation.'

# A process override wins after local files. It must fail native validation,
# rather than accepting only the generated text. Never persist the override.
$priorOverride = [Environment]::GetEnvironmentVariable('_CONDOR_YADOF_FRP_MANAGED', 'Process')
try {
    $env:_CONDOR_YADOF_FRP_MANAGED = 'False'
    Assert-Throws { New-FrpPlan $context $worker $work } 'A shadowed staged configuration must fail native validation.'
}
finally { [Environment]::SetEnvironmentVariable('_CONDOR_YADOF_FRP_MANAGED', $priorOverride, 'Process') }

# Exercise the real transaction on fixture files only. Every service/network
# mutation is replaced in module scope BEFORE Install-FrpPlan is invoked.
& $module {
    $script:ServiceCalls = New-Object 'System.Collections.Generic.List[string]'
    function script:Test-FrpAdministrator { return $true }
    function script:Get-Service { param($Name) return [pscustomobject]@{Status='Running';StartType='Automatic'} }
    function script:Stop-Service { [CmdletBinding()]param($Name,[switch]$Force) $script:ServiceCalls.Add('stop') }
    function script:Start-Service { [CmdletBinding()]param($Name) $script:ServiceCalls.Add('start') }
    function script:Set-Service { [CmdletBinding()]param($Name,$StartupType) $script:ServiceCalls.Add("startup:$StartupType") }
    function script:Test-FrpVisitor { param($Port) $script:ServiceCalls.Add('visitor') }
    function script:Wait-FrpRegistration { param($Context,$Settings) throw 'Simulated registration failure' }
}
$rootBefore = [IO.File]::ReadAllBytes($root)
$legacyHash = (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash
Assert-Throws { Install-FrpPlan $context $plan $worker $null } 'Registration failure must make apply fail.'
Assert-True ([Convert]::ToBase64String([IO.File]::ReadAllBytes($root)) -eq [Convert]::ToBase64String($rootBefore)) 'Rollback must restore root bytes exactly.'
Assert-True (-not (Test-Path -LiteralPath $context.ManagedConfig)) 'Rollback must remove a newly created managed file.'
$calls = & $module { return @($script:ServiceCalls.ToArray()) }
Assert-True (($calls -join ',') -eq 'visitor,stop,startup:Automatic,start,stop,startup:Automatic,start') 'Rollback must restore prior startup/running state.'
Assert-True ((Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash -eq $legacyHash) 'Legacy local config must remain untouched.'

# A failed update must restore an existing managed file too.
Write-FrpUtf8 $context.ManagedConfig '# previous managed content'
$secondPlan = New-FrpPlan $context $worker $work
Assert-Throws { Install-FrpPlan $context $secondPlan $worker $null } 'Updating an existing managed file must roll back on failure.'
Assert-True ([IO.File]::ReadAllText($context.ManagedConfig) -eq '# previous managed content') 'Existing managed content was not restored.'

# Exit/detach applies entirely to fixture files and mocked service controls.
$detachPlan = New-FrpPlan $context $detached $work
Install-FrpPlan $context $detachPlan $detached $null
$calls = & $module { return @($script:ServiceCalls.ToArray()) }
Assert-True ($calls[-1] -eq 'startup:Disabled') 'Detach must disable startup, not only stop the service.'

foreach ($path in $productionPaths) {
    Assert-True ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -eq $before[$path]) 'An actual configuration file changed.'
}
$serviceAfter = Microsoft.PowerShell.Management\Get-Service condor
Assert-True ([string]$serviceAfter.Status -eq $statusBefore -and [string]$serviceAfter.StartType -eq $startBefore) 'Actual service state changed.'
Write-Output "PASS: $script:checks offline checks; artifacts: $work"
