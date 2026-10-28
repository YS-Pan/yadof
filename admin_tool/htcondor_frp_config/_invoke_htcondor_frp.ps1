#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Leave','Manager','Worker','Resources')][string]$Action,
    [string]$ManagerName, [string]$TrustDomain,
    [ValidateRange(0,65535)][int]$VisitorPort = 0,
    [ValidateRange(0,65535)][int]$SharedPort = 0,
    [string]$PrivateNetworkName, [string]$BrokerTargetAllowlist,
    [switch]$EnableSubmit, [string]$NetworkAdapterName,
    [string]$ExecuteDirectory,
    [ValidateRange(0,2147483647)][long]$Cpus = 0,
    [ValidateRange(0,9223372036854775807)][long]$MemoryMiB = 0,
    [ValidateRange(0,9223372036854775807)][long]$DiskMiB = 0,
    [string]$RootConfig, [string]$OutputDirectory,
    [switch]$DryRun, [switch]$NonInteractive, [switch]$Yes, [switch]$NoPause
)
$ErrorActionPreference = 'Stop'
$exitCode = 0
$delegated = $false
try {
    Import-Module (Join-Path $PSScriptRoot '_htcondor_frp_common.psm1') -Force -DisableNameChecking
    if (-not $DryRun -and -not (Test-FrpAdministrator)) {
        # Encode the entire parameter object, so spaces, Unicode and apostrophes survive UAC.
        $serialized = [Management.Automation.PSSerializer]::Serialize(@{} + $PSBoundParameters)
        $payload = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($serialized))
        $entry = $PSCommandPath.Replace("'", "''")
        $bootstrap = '$env:PSModulePath = [IO.Path]::Combine($env:SystemRoot, ''System32\WindowsPowerShell\v1.0\Modules'') + '';'' + [IO.Path]::Combine($env:ProgramFiles, ''WindowsPowerShell\Modules''); '
        $command = $bootstrap + '$p = [Management.Automation.PSSerializer]::Deserialize([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String(''' + $payload + '''))); & ''' + $entry + ''' @p; exit $LASTEXITCODE'
        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
        # This is an interactive setup window: the user must see its prompts and result.
        $child = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') `
            -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',$encoded) -Verb RunAs -Wait -PassThru
        $delegated = $true
        $exitCode = $child.ExitCode
    }
    else {
        if ($Action -ne 'Resources' -and ($ExecuteDirectory -or $Cpus -or $MemoryMiB -or $DiskMiB)) {
            throw 'Resource arguments belong to script 4; role scripts preserve already-declared resources.'
        }
        $context = Get-FrpContext -RootConfig $RootConfig
        $existingRole = Get-FrpValue $context 'YADOF_POOL_ROLE'
        $role = if ($Action -eq 'Leave') { 'Detached' } elseif ($Action -eq 'Resources') { $existingRole } else { $Action }
        if ($role -notin @('Detached','Manager','Worker')) { throw 'Run script 2 or 3 before script 4.' }
        $unattended = $NonInteractive -or $DryRun
        $oldManager = Get-FrpValue $context 'YADOF_MANAGER_NAME'
        $managerDefault = if ($role -eq 'Manager' -or $role -eq 'Detached') { $env:COMPUTERNAME } elseif ($oldManager) { $oldManager } else { 'DESKTOP-A2092' }
        $ManagerName = Assert-FrpName (Read-FrpText 'Manager identity (not the FRP server address)' $ManagerName $managerDefault -NonInteractive:$unattended)
        $domainDefault = Get-FrpValue $context 'TRUST_DOMAIN'
        if (-not $domainDefault -or ($role -eq 'Manager' -and $existingRole -ne 'Manager') -or
            (-not $oldManager -and $existingRole -notin @('Manager','Worker'))) { $domainDefault = $ManagerName }
        $TrustDomain = Assert-FrpName (Read-FrpText 'Existing pool trust domain' $TrustDomain $domainDefault -NonInteractive:$unattended) 'Trust domain'
        if (-not $VisitorPort) {
            $oldVisitor = Get-FrpValue $context 'YADOF_FRP_VISITOR_PORT'
            if ($oldVisitor -match '^\d+$') { $VisitorPort = [int]$oldVisitor }
            elseif ((Get-FrpValue $context 'COLLECTOR_HOST') -match '^127\.0\.0\.1:(\d+)$') { $VisitorPort = [int]$matches[1] }
            else { $VisitorPort = 29618 }
            if ($role -eq 'Worker') { $VisitorPort = [int](Read-FrpText 'Local FRP visitor port' '' ([string]$VisitorPort) -NonInteractive:$unattended) }
        }
        if (-not $SharedPort) {
            $oldPort = Get-FrpValue $context 'SHARED_PORT_PORT'
            $SharedPort = if ($oldPort -match '^\d+$') { [int]$oldPort } else { 9618 }
        }
        if ($VisitorPort -lt 1 -or $VisitorPort -gt 65535 -or $SharedPort -lt 1 -or $SharedPort -gt 65535) { throw 'Ports must be between 1 and 65535.' }
        if ($role -eq 'Worker' -and $VisitorPort -eq $SharedPort) { throw 'The FRP visitor and local shared-port listener must use different ports.' }
        if (-not $PrivateNetworkName) { $PrivateNetworkName = Get-FrpValue $context 'PRIVATE_NETWORK_NAME' }
        if (-not $PrivateNetworkName) { $PrivateNetworkName = $env:COMPUTERNAME }
        $PrivateNetworkName = Assert-FrpName $PrivateNetworkName 'Private network name'
        $networkInterface = Get-FrpValue $context 'NETWORK_INTERFACE'
        if (-not $networkInterface) { $networkInterface = '*' }
        if ($NetworkAdapterName) {
            $adapters = @(Get-NetAdapter | Where-Object Name -ieq $NetworkAdapterName)
            if ($adapters.Count -ne 1 -or $adapters[0].Status -ne 'Up') { throw 'Select exactly one connected local network adapter.' }
            $networkInterface = ([guid]$adapters[0].InterfaceGuid).ToString('B')
        }
        if ($role -eq 'Manager') {
            $localIps = @(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress)
            $resolvedIps = @([Net.Dns]::GetHostAddresses($ManagerName) | ForEach-Object ToString)
            if (-not @($resolvedIps | Where-Object { $localIps -contains $_ }).Count) { throw 'Manager identity must resolve to this manager machine.' }
            $targetsDefault = Get-FrpValue $context 'CCB_OUTBOUND_TARGET_ALLOWLIST'
            if (-not $targetsDefault) { $targetsDefault = Get-FrpValue $context 'IP_ADDRESS' }
            $BrokerTargetAllowlist = Read-FrpText 'Allowed outbound CCB target addresses (include the manager advertised address)' $BrokerTargetAllowlist $targetsDefault -NonInteractive:$unattended
            if ($BrokerTargetAllowlist -notmatch '^[A-Za-z0-9_.,:/ *-]+$') { throw 'Invalid CCB target allowlist.' }
        }
        $resources = $null
        $retainResources = (Get-FrpValue $context 'YADOF_RESOURCES_CONFIGURED') -ieq 'True'
        if ($Action -eq 'Resources') {
            $resources = Get-FrpResources $context -ExecuteDirectory $ExecuteDirectory -Cpus $Cpus -MemoryMiB $MemoryMiB -DiskMiB $DiskMiB -NonInteractive:$unattended
        }
        elseif ($retainResources -and $role -ne 'Detached') {
            $resources = Get-FrpResources $context -ExecuteDirectory (Get-FrpValue $context 'EXECUTE') `
                -Cpus ([long](Get-FrpValue $context 'YADOF_DECLARED_CPUS')) `
                -MemoryMiB ([long](Get-FrpValue $context 'YADOF_DECLARED_MEMORY_MB')) `
                -DiskMiB ([long](Get-FrpValue $context 'YADOF_DECLARED_DISK_MB')) -NonInteractive
        }
        $submit = $EnableSubmit -or ((Get-FrpValue $context 'YADOF_FRP_ENABLE_SUBMIT') -ieq 'True')
        # Preserve existing local submission capability when migrating a workstation.
        if ((Get-FrpValue $context 'DAEMON_LIST') -match '(?i)(^|[,\s])SCHEDD($|[,\s])') { $submit = $true }
        $methods = Get-FrpValue $context 'SEC_DEFAULT_AUTHENTICATION_METHODS'
        if (-not $methods) { $methods = 'IDTOKENS, NTSSPI, PASSWORD, KERBEROS, SSL' }
        $settings = New-FrpSettings -Role $role -ManagerName $ManagerName -TrustDomain $TrustDomain `
            -VisitorPort $VisitorPort -SharedPort $SharedPort -PrivateNetworkName $PrivateNetworkName `
            -BrokerTargetAllowlist $BrokerTargetAllowlist -EnableSubmit $submit -Resources $resources `
            -AuthenticationMethods $methods -StartdAttrs (Get-FrpValue $context 'STARTD_ATTRS')
        $settings.NETWORK_INTERFACE = $networkInterface
        if (-not $OutputDirectory) { $OutputDirectory = Join-Path $env:TEMP 'yadof-htcondor-frp' }
        $plan = New-FrpPlan $context $settings $OutputDirectory
        Write-Host "Role: $role; collector: $($settings.COLLECTOR_HOST); trust domain: $TrustDomain"
        Write-Host "Execute enabled: $($settings.YADOF_RESOURCES_CONFIGURED); daemons: $($settings.DAEMON_LIST)"
        Write-Host "Validated preview: $($plan.Directory)"
        if ($DryRun) { Write-Host 'Dry run: no service, production config, credentials, firewall or execute ACL was changed.' }
        else {
            Write-Warning 'Applying this configuration restarts/stops HTCondor and may terminate running jobs.'
            if (-not $Yes) {
                if ($NonInteractive) { throw 'Use -Yes to acknowledge the service interruption in noninteractive mode.' }
                $expected = if ($role -eq 'Detached') { 'LEAVE' } else { 'APPLY' }
                if ((Read-Host "Type $expected to continue") -cne $expected) { throw 'Cancelled before changing HTCondor.' }
            }
            Install-FrpPlan $context $plan $settings $resources
            if ($role -ne 'Detached' -and -not $resources) { Write-Host 'Execution is disabled. Run script 4 to declare resources and enable STARTD.' }
        }
    }
}
catch {
    $exitCode = 1
    Write-Host $_.Exception.Message -ForegroundColor Red
}
finally {
    if (-not $NoPause -and -not $NonInteractive -and -not $DryRun -and -not $delegated) { [void](Read-Host 'Press Enter to close') }
}
exit $exitCode
