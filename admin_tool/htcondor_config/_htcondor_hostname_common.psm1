Set-StrictMode -Version 2.0

# HTCondor manual references used by this module:
# Windows configuration lookup:
# https://htcondor.readthedocs.io/en/latest/admin-manual/introduction-to-configuration.html
# Collector host names and shared port networking:
# https://htcondor.readthedocs.io/en/latest/admin-manual/networking.html
# Host-name authorization rules:
# https://htcondor.readthedocs.io/en/latest/admin-manual/security.html
# Execute resources and partitionable slots:
# https://htcondor.readthedocs.io/en/lts/admin-manual/ep-policy-configuration.html
# Windows execute accounts and scratch directories:
# https://htcondor.readthedocs.io/en/latest/platform-specific/microsoft-windows.html

$script:CondorRootConfig = $null
$script:CondorLocalConfig = $null
$script:CondorBinDirectory = $null
$script:CondorRootDirectory = $null
$script:CondorCommands = @{}
$script:ManagedBlockBegin = "# BEGIN YADOF HTCONDOR HOSTNAME POOL"
$script:ManagedBlockEnd = "# END YADOF HTCONDOR HOSTNAME POOL"
$script:FirewallRuleName = "YADOF HTCondor hostname pool"

function Test-YadofAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Start-YadofElevatedScript {
    param([Parameter(Mandatory = $true)][string]$ScriptPath)

    $quotedScript = '"' + $ScriptPath.Replace('"', '\"') + '"'
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File $quotedScript"
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs | Out-Null
}

function Get-CondorRegistryConfigPaths {
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($registryPath in @("HKLM:\SOFTWARE\Condor", "HKLM:\SOFTWARE\WOW6432Node\Condor")) {
        $entry = Get-ItemProperty -Path $registryPath -ErrorAction SilentlyContinue
        if ($entry -and $entry.CONDOR_CONFIG) {
            $result.Add([string]$entry.CONDOR_CONFIG)
        }
    }
    return @($result)
}

function Get-CondorService {
    $exact = Get-Service -Name "condor" -ErrorAction SilentlyContinue
    if ($exact) {
        return $exact
    }
    return Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*condor*" -or $_.DisplayName -like "*condor*" } |
        Sort-Object Name |
        Select-Object -First 1
}

function Get-CondorBinCandidates {
    $result = New-Object System.Collections.Generic.List[string]

    foreach ($commandName in @("condor_config_val.exe", "condor_config_val")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            $result.Add((Split-Path -Parent $command.Source))
        }
    }

    foreach ($configPath in @(
        $env:CONDOR_CONFIG,
        [Environment]::GetEnvironmentVariable("CONDOR_CONFIG", "Machine")
    ) + @(Get-CondorRegistryConfigPaths)) {
        if ($configPath) {
            $configParent = Split-Path -Parent ([string]$configPath)
            if ($configParent) {
                $result.Add((Join-Path $configParent "bin"))
            }
        }
    }

    $knownRoots = New-Object System.Collections.Generic.List[string]
    foreach ($root in @(
        $env:CONDOR_LOCATION,
        (Join-Path $env:ProgramFiles "HTCondor"),
        (Join-Path $env:ProgramFiles "Condor"),
        "C:\condor",
        "D:\condor"
    )) {
        if ($root) {
            $knownRoots.Add($root)
        }
    }
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $knownRoots.Add((Join-Path $programFilesX86 "HTCondor"))
        $knownRoots.Add((Join-Path $programFilesX86 "Condor"))
    }
    foreach ($drive in Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue) {
        $knownRoots.Add((Join-Path $drive.Root "condor"))
    }
    foreach ($root in $knownRoots) {
        if ($root) {
            $result.Add((Join-Path $root "bin"))
        }
    }

    $services = @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*condor*" -or $_.DisplayName -like "*condor*" })
    foreach ($service in $services) {
        $servicePath = [string]$service.PathName
        $masterPath = $null
        if ($servicePath -match '^\s*"([^"]+condor_master\.exe)"') {
            $masterPath = $matches[1]
        }
        elseif ($servicePath -match '^\s*([^"].*?condor_master\.exe)(?:\s|$)') {
            $masterPath = $matches[1].Trim()
        }
        if ($masterPath -and (Test-Path -LiteralPath $masterPath -PathType Leaf)) {
            $result.Add((Split-Path -Parent $masterPath))
        }
    }

    return @($result | Where-Object { $_ } | Select-Object -Unique)
}

function Find-CondorCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    foreach ($commandName in @("$Name.exe", $Name)) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            return $command.Source
        }
    }
    foreach ($binDirectory in Get-CondorBinCandidates) {
        $candidate = Join-Path $binDirectory "$Name.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "HTCondor command '$Name.exe' was not found. Install HTCondor for Windows first."
}

function Get-RootConfigCandidates {
    param([Parameter(Mandatory = $true)][string]$CondorRootDirectory)

    return @(
        $env:CONDOR_CONFIG,
        [Environment]::GetEnvironmentVariable("CONDOR_CONFIG", "Machine")
    ) + @(Get-CondorRegistryConfigPaths) + @(
        (Join-Path $CondorRootDirectory "condor_config"),
        (Join-Path $CondorRootDirectory "etc\condor_config")
    )
}

function Invoke-CondorConfigVal {
    param([Parameter(Mandatory = $true)][string]$Name)

    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $script:CondorCommands["condor_config_val"] $Name 2>$null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    if ($exitCode -eq 0 -and $null -ne $output) {
        return ([string]($output | Select-Object -First 1)).Trim()
    }
    return ""
}

function Add-LocalConfigToRoot {
    param([Parameter(Mandatory = $true)][string]$LocalConfigPath)

    $rootText = if (Test-Path -LiteralPath $script:CondorRootConfig -PathType Leaf) {
        [IO.File]::ReadAllText($script:CondorRootConfig)
    }
    else {
        ""
    }
    $begin = "# BEGIN YADOF HOSTNAME LOCAL CONFIG INCLUDE"
    $end = "# END YADOF HOSTNAME LOCAL CONFIG INCLUDE"
    $condorPath = $LocalConfigPath -replace "\\", "/"
    $block = @($begin, "LOCAL_CONFIG_FILE = $condorPath", $end, "") -join [Environment]::NewLine
    $pattern = "(?ms)^" + [regex]::Escape($begin) + "\r?\n.*?^" + [regex]::Escape($end) + "\r?\n?"
    if ($rootText -match [regex]::Escape($begin)) {
        $updated = [regex]::Replace($rootText, $pattern, $block)
    }
    elseif ($rootText.Trim()) {
        $updated = $rootText.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block
    }
    else {
        $updated = $block
    }

    $parent = Split-Path -Parent $script:CondorRootConfig
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $script:CondorRootConfig -PathType Leaf) {
        Copy-Item -LiteralPath $script:CondorRootConfig -Destination ($script:CondorRootConfig + ".bak." + (Get-Date -Format "yyyyMMdd-HHmmss-fff")) -Force
    }
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($script:CondorRootConfig, $updated, $utf8)
}

function Resolve-LocalConfigPath {
    $configured = Invoke-CondorConfigVal -Name "LOCAL_CONFIG_FILE"
    if ($configured) {
        $wholePath = $configured.Trim().Trim('"') -replace "/", "\"
        if (Test-Path -LiteralPath $wholePath -PathType Leaf) {
            return (Resolve-Path -LiteralPath $wholePath).Path
        }

        $items = @([regex]::Matches($configured, '"([^"]+)"|([^,\s]+)') | ForEach-Object {
            if ($_.Groups[1].Success) { $_.Groups[1].Value } else { $_.Groups[2].Value }
        } | Where-Object { $_ })
        for ($index = $items.Count - 1; $index -ge 0; $index--) {
            $candidate = $items[$index] -replace "/", "\"
            if (-not $candidate.Contains('$(') -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        }
        for ($index = $items.Count - 1; $index -ge 0; $index--) {
            if (-not $items[$index].Contains('$(') -and [IO.Path]::IsPathRooted($items[$index])) {
                return ($items[$index] -replace "/", "\")
            }
        }
    }

    $fallback = Join-Path (Split-Path -Parent $script:CondorBinDirectory) "condor_config.local"
    Add-LocalConfigToRoot -LocalConfigPath $fallback
    return $fallback
}

function Initialize-YadofCondor {
    foreach ($name in @("condor_config_val", "condor_status", "condor_restart")) {
        $script:CondorCommands[$name] = Find-CondorCommand -Name $name
    }
    $script:CondorBinDirectory = Split-Path -Parent $script:CondorCommands["condor_config_val"]
    $script:CondorRootDirectory = Split-Path -Parent $script:CondorBinDirectory

    $script:CondorRootConfig = Get-RootConfigCandidates -CondorRootDirectory $script:CondorRootDirectory |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
    if (-not $script:CondorRootConfig) {
        throw "The HTCondor root configuration file could not be found."
    }
    $script:CondorRootConfig = (Resolve-Path -LiteralPath $script:CondorRootConfig).Path
    $env:CONDOR_CONFIG = $script:CondorRootConfig
    if (($env:PATH -split ";") -notcontains $script:CondorBinDirectory) {
        $env:PATH = $script:CondorBinDirectory + ";" + $env:PATH
    }
    $script:CondorLocalConfig = Resolve-LocalConfigPath

    Write-Host "HTCondor bin:    $script:CondorBinDirectory"
    Write-Host "Root config:     $script:CondorRootConfig"
    Write-Host "Managed config:  $script:CondorLocalConfig"
}

function Assert-MachineName {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [switch]$AllowWildcard
    )

    $value = $Name.Trim()
    if (-not $value) {
        throw "A machine name cannot be empty."
    }
    $parsedAddress = $null
    if ([Net.IPAddress]::TryParse($value, [ref]$parsedAddress)) {
        throw "An IP address is not allowed here. Use a resolvable machine name: $value"
    }
    if ($value -match '^\d{1,3}(?:\.\d{1,3}|\.\*){3}$') {
        throw "An IP address pattern is not allowed here. Use machine names: $value"
    }
    if (-not $AllowWildcard -and $value.Contains("*")) {
        throw "Wildcards are not allowed in the manager machine name: $value"
    }
    if ($value -notmatch '^[A-Za-z0-9_*](?:[A-Za-z0-9_.*-]*[A-Za-z0-9_*])?$') {
        throw "Invalid machine name or host-name pattern: $value"
    }
    return $value
}

function Assert-ManagerResolves {
    param([Parameter(Mandatory = $true)][string]$ManagerMachineName)

    try {
        $addresses = [Net.Dns]::GetHostAddresses($ManagerMachineName)
        if (-not $addresses -or $addresses.Count -eq 0) {
            throw "No result"
        }
    }
    catch {
        throw "Manager machine name '$ManagerMachineName' cannot be resolved. Fix DNS/hosts/name resolution before configuring HTCondor."
    }
    Write-Host "Name resolution: '$ManagerMachineName' resolved successfully."
}

function Get-YadofUsableAdapterIPv4Addresses {
    param([Parameter(Mandatory = $true)]$Adapter)

    return @(Get-NetIPAddress -InterfaceIndex $Adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -and
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.IPAddress -ne "0.0.0.0"
        } |
        Select-Object -ExpandProperty IPAddress -Unique)
}

function Resolve-YadofNetworkAdapter {
    param(
        [string]$AdapterName = "",
        [string]$NetworkInterface = "",
        [switch]$Quiet
    )

    $adapters = @(Get-NetAdapter -ErrorAction Stop)
    $adapter = $null
    if ($AdapterName.Trim()) {
        $requestedName = $AdapterName.Trim()
        $matches = @($adapters | Where-Object { $_.Name -ieq $requestedName })
        if ($matches.Count -ne 1) {
            throw "Network adapter '$requestedName' was not found. Run Get-NetAdapter and enter the exact local adapter name."
        }
        $adapter = $matches[0]
    }
    else {
        $selector = $NetworkInterface.Trim()
        $selectorGuid = [Guid]::Empty
        if (-not $selector -or $selector -eq "*" -or -not [Guid]::TryParse($selector, [ref]$selectorGuid)) {
            throw "A specific local cluster network adapter is required. NETWORK_INTERFACE='*' is unsafe on a multi-interface node."
        }
        $matches = @($adapters | Where-Object { ([Guid]$_.InterfaceGuid) -eq $selectorGuid })
        if ($matches.Count -ne 1) {
            throw "The configured network interface '$selector' no longer matches an installed adapter. Enter the local cluster adapter name again."
        }
        $adapter = $matches[0]
    }

    if ([string]$adapter.Status -ine "Up") {
        throw "Network adapter '$($adapter.Name)' is not Up. Connect or enable the cluster network adapter first."
    }
    $ipv4Addresses = @(Get-YadofUsableAdapterIPv4Addresses -Adapter $adapter)
    if ($ipv4Addresses.Count -eq 0) {
        throw "Network adapter '$($adapter.Name)' has no usable IPv4 address."
    }

    $guidSelector = ([Guid]$adapter.InterfaceGuid).ToString("B").ToUpperInvariant()
    if (-not $Quiet) {
        Write-Host "Cluster adapter: $($adapter.Name)"
        Write-Host "  Description:  $($adapter.InterfaceDescription)"
        Write-Host "  IPv4:         $($ipv4Addresses -join ', ')"
        Write-Host "  HTCondor interface selector: $guidSelector"
    }
    return [pscustomobject]@{
        Name = [string]$adapter.Name
        Description = [string]$adapter.InterfaceDescription
        InterfaceGuid = $guidSelector
        IPv4Addresses = $ipv4Addresses
    }
}

function Assert-YadofManagerNameMatchesLocalAdapter {
    param(
        [Parameter(Mandatory = $true)][string]$ManagerMachineName,
        [Parameter(Mandatory = $true)]$NetworkSelection
    )

    $resolvedIPv4 = @([Net.Dns]::GetHostAddresses($ManagerMachineName) |
        Where-Object { $_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork } |
        ForEach-Object { $_.ToString() })
    $matchesSelectedAdapter = @($NetworkSelection.IPv4Addresses |
        Where-Object { $resolvedIPv4 -contains $_ }).Count -gt 0
    if (-not $matchesSelectedAdapter) {
        throw "Manager name '$ManagerMachineName' does not resolve to the selected local cluster adapter '$($NetworkSelection.Name)'."
    }
}

function Show-YadofNetworkAdapters {
    $rows = @(Get-NetAdapter -ErrorAction Stop | Sort-Object Name | ForEach-Object {
        $addresses = @(Get-YadofUsableAdapterIPv4Addresses -Adapter $_)
        [pscustomobject]@{
            Name = $_.Name
            Status = $_.Status
            IPv4 = $addresses -join ", "
            Description = $_.InterfaceDescription
        }
    })
    Write-Host ""
    Write-Host "Local network adapters (choose the one connected to the HTCondor cluster LAN):"
    $rows | Format-Table -AutoSize | Out-Host
}

function Get-UniqueMachineNames {
    param(
        [string[]]$Names,
        [string]$ManagerMachineName
    )

    $allNames = New-Object System.Collections.Generic.List[string]
    foreach ($name in @($Names) + @($ManagerMachineName, $env:COMPUTERNAME, [Net.Dns]::GetHostName())) {
        if ($name) {
            $validated = Assert-MachineName -Name ([string]$name) -AllowWildcard
            $allNames.Add($validated)
            if (-not $validated.Contains("*")) {
                try {
                    $entry = [Net.Dns]::GetHostEntry($validated)
                    foreach ($resolvedName in @($entry.HostName) + @($entry.Aliases)) {
                        if ($resolvedName) {
                            $allNames.Add((Assert-MachineName -Name ([string]$resolvedName) -AllowWildcard))
                        }
                    }
                }
                catch {
                    # The manager receives a separate mandatory resolution check.
                    # Optional allow-list names may be temporarily offline.
                }
            }
        }
    }
    try {
        $fqdn = [Net.Dns]::GetHostEntry([Net.Dns]::GetHostName()).HostName
        if ($fqdn) {
            $allNames.Add((Assert-MachineName -Name $fqdn -AllowWildcard))
        }
    }
    catch {
        # A short Windows machine name is sufficient when no DNS suffix exists.
    }
    return @($allNames | Select-Object -Unique)
}

function Get-ExistingResourceConfiguration {
    $configured = Invoke-CondorConfigVal -Name "YADOF_RESOURCES_CONFIGURED"
    if ($configured -ine "True") {
        return $null
    }
    $execute = Invoke-CondorConfigVal -Name "EXECUTE"
    $cpus = Invoke-CondorConfigVal -Name "YADOF_DECLARED_CPUS"
    $memory = Invoke-CondorConfigVal -Name "YADOF_DECLARED_MEMORY_MB"
    $disk = Invoke-CondorConfigVal -Name "YADOF_DECLARED_DISK_MB"
    if (-not $execute -or -not $cpus -or -not $memory -or -not $disk) {
        return $null
    }
    return @{
        ExecuteDirectory = $execute -replace "/", "\"
        DeclaredCpus = [int]$cpus
        DeclaredMemoryMb = [int64]$memory
        DeclaredDiskMb = [int64]$disk
    }
}

function Get-YadofCurrentConfiguration {
    Initialize-YadofCondor

    $daemons = @((Invoke-CondorConfigVal -Name "DAEMON_LIST") -split "[,\s]+" | Where-Object { $_ })
    $role = if ($daemons -contains "COLLECTOR" -or $daemons -contains "NEGOTIATOR") { "Manager" }
        elseif ($daemons -contains "STARTD") { "Worker" }
        elseif ($daemons -contains "SCHEDD") { "Submit" }
        else { Invoke-CondorConfigVal -Name "YADOF_POOL_ROLE" }
    $flocking = @{}
    foreach ($key in @("FLOCK_TO", "FLOCK_COLLECTOR_HOSTS", "FLOCK_NEGOTIATOR_HOSTS")) {
        $flocking[$key] = Invoke-CondorConfigVal -Name $key
    }
    $networkInterface = Invoke-CondorConfigVal -Name "NETWORK_INTERFACE"
    $adapterName = ""
    if ($networkInterface -and $networkInterface -ne "*") {
        try {
            $adapterName = (Resolve-YadofNetworkAdapter -NetworkInterface $networkInterface -Quiet).Name
        }
        catch {
            # Return the selector even if its former adapter is no longer installed.
        }
    }
    $manager = Invoke-CondorConfigVal -Name "YADOF_MANAGER_NAME"
    if (-not $manager) {
        $manager = Invoke-CondorConfigVal -Name "CONDOR_HOST"
    }
    return [pscustomobject]@{
        Role = $role
        Daemons = $daemons
        Flocking = $flocking
        AllowedMachineNames = @((Invoke-CondorConfigVal -Name "YADOF_ALLOWED_MACHINE_NAMES") -split "\s*,\s*" | Where-Object { $_ })
        ManagerMachineName = $manager
        NetworkAdapterName = $adapterName
        NetworkInterface = $networkInterface
        Resources = Get-ExistingResourceConfiguration
    }
}

function Merge-YadofPoolRoles {
    param(
        [Parameter(Mandatory = $true)]$Current,
        [Parameter(Mandatory = $true)][ValidateSet("Manager", "Worker", "Submit")][string]$Role,
        [Parameter(Mandatory = $true)][string]$ManagerMachineName
    )

    # Adding a local capability must not silently move an existing node to a
    # different pool, particularly when it is already the central manager.
    if ($Current.Role -in @("Manager", "Worker", "Submit") -and $Current.ManagerMachineName -and
        $Current.ManagerMachineName.TrimEnd('.') -ine $ManagerMachineName.TrimEnd('.')) {
        throw "This node already uses manager '$($Current.ManagerMachineName)'. Keep that manager when adding a role; use script 1 before deliberately switching pools."
    }
    $combinedRole = if ($Role -eq "Manager" -or $Current.Role -eq "Manager") { "Manager" }
        elseif ($Role -eq "Worker" -or $Current.Role -eq "Worker") { "Worker" }
        else { "Submit" }
    return @{
        Role = $combinedRole
        ManagerMachineName = $ManagerMachineName
        ExistingDaemons = $Current.Daemons
        EnableSubmit = ($Role -in @("Manager", "Submit"))
        EnableExecute = ($Role -eq "Worker")
        Flocking = $Current.Flocking
    }
}

function New-PoolConfigurationBody {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Detached", "Manager", "Worker", "Submit")][string]$Role,
        [Parameter(Mandatory = $true)][string]$ManagerMachineName,
        [string[]]$AllowedMachineNames,
        [string]$NetworkInterface = "*",
        [Parameter(Mandatory = $true)][ValidateRange(1, 65535)][int]$Port,
        [hashtable]$Resources,
        [string[]]$ExistingDaemons = @(),
        [bool]$EnableSubmit = $false,
        [bool]$EnableExecute = $false,
        [hashtable]$Flocking = @{}
    )

    if ($Role -ne "Detached" -and (-not $NetworkInterface.Trim() -or $NetworkInterface.Trim() -eq "*")) {
        throw "Active roles require a specific local cluster network adapter."
    }

    $allowNames = Get-UniqueMachineNames -Names $AllowedMachineNames -ManagerMachineName $ManagerMachineName
    $allowText = $allowNames -join ", "
    $administratorNames = Get-UniqueMachineNames -Names @($ManagerMachineName) -ManagerMachineName $ManagerMachineName
    $administratorText = $administratorNames -join ", "

    $daemons = switch ($Role) {
        "Manager" { @("MASTER", "COLLECTOR", "NEGOTIATOR") }
        "Worker" { @("MASTER", "STARTD") }
        "Submit" { @("MASTER", "SCHEDD") }
        default { @("MASTER") }
    }
    if ($Role -ne "Detached") {
        $daemons = @($daemons) + $ExistingDaemons
        if ($EnableSubmit) { $daemons += "SCHEDD" }
        if ($EnableExecute -or $Resources) { $daemons += "STARTD" }
        $daemons = @($daemons | ForEach-Object { $_.ToUpperInvariant() } | Select-Object -Unique)
    }

    $lines = New-Object System.Collections.Generic.List[string]
    if (-not $script:CondorRootDirectory) {
        throw "HTCondor has not been initialized."
    }
    $condorRootForConfig = $script:CondorRootDirectory.TrimEnd("\") -replace "\\", "/"
    $lines.Add("# Generated by the numbered HTCondor hostname-only setup scripts.")
    $lines.Add("# CONDOR_HOST/COLLECTOR_HOST and authorization entries use names, not addresses.")
    $lines.Add("RELEASE_DIR = $condorRootForConfig")
    $lines.Add("LOCAL_DIR = $condorRootForConfig")
    $lines.Add("YADOF_POOL_ROLE = $Role")
    $lines.Add("YADOF_MANAGER_NAME = $ManagerMachineName")
    $lines.Add("YADOF_ALLOWED_MACHINE_NAMES = $allowText")
    $lines.Add("CONDOR_HOST = $ManagerMachineName")
    $lines.Add('COLLECTOR_HOST = $(CONDOR_HOST):' + $Port)
    $lines.Add("NO_DNS = False")
    $lines.Add("NETWORK_INTERFACE = $NetworkInterface")
    $lines.Add("BIND_ALL_INTERFACES = True")
    $lines.Add("USE_SHARED_PORT = True")
    $lines.Add("SHARED_PORT_PORT = $Port")
    $lines.Add("DAEMON_LIST = $($daemons -join ', ')")
    $lines.Add("")
    foreach ($key in @("FLOCK_TO", "FLOCK_COLLECTOR_HOSTS", "FLOCK_NEGOTIATOR_HOSTS")) {
        $value = if ($Role -eq "Detached") { "" } else { $Flocking[$key] }
        $lines.Add("$key = $value")
    }
    $lines.Add("")
    $lines.Add("ALLOW_READ = $allowText")
    $lines.Add("ALLOW_WRITE = $allowText")
    $lines.Add("ALLOW_ADMINISTRATOR = $administratorText")
    $lines.Add("ALLOW_DAEMON = $allowText")
    $lines.Add("ALLOW_NEGOTIATOR = $administratorText")
    $lines.Add("ALLOW_ADVERTISE_MASTER = $allowText")
    $lines.Add("ALLOW_ADVERTISE_STARTD = $allowText")
    $lines.Add("ALLOW_ADVERTISE_SCHEDD = $allowText")
    $lines.Add("")
    $lines.Add("SEC_DEFAULT_AUTHENTICATION = Optional")
    $lines.Add("SEC_DEFAULT_ENCRYPTION = Optional")
    $lines.Add("SEC_DEFAULT_INTEGRITY = Optional")

    if ($daemons -contains "STARTD") {
        $lines.Add("")
        $lines.Add("START = True")
        $lines.Add("SUSPEND = False")
        $lines.Add("PREEMPT = False")
        $lines.Add("KILL = False")
        $lines.Add("WANT_SUSPEND = False")
        $lines.Add("WANT_VACATE = False")
    }

    if ($Resources) {
        $executeForCondor = ([string]$Resources.ExecuteDirectory).TrimEnd("\") -replace "\\", "/"
        $diskKb = [int64]$Resources.DeclaredDiskMb * 1024
        $lines.Add("")
        $lines.Add("YADOF_RESOURCES_CONFIGURED = True")
        $lines.Add("YADOF_DECLARED_CPUS = $($Resources.DeclaredCpus)")
        $lines.Add("YADOF_DECLARED_MEMORY_MB = $($Resources.DeclaredMemoryMb)")
        $lines.Add("YADOF_DECLARED_DISK_MB = $($Resources.DeclaredDiskMb)")
        $lines.Add("EXECUTE = $executeForCondor")
        $lines.Add("NUM_CPUS = $($Resources.DeclaredCpus)")
        $lines.Add("MEMORY = $($Resources.DeclaredMemoryMb)")
        $lines.Add("DISK = $diskKb")
        $lines.Add("NUM_SLOTS = 1")
        $lines.Add("NUM_SLOTS_TYPE_1 = 1")
        $lines.Add("SLOT_TYPE_1 = 100%")
        $lines.Add("SLOT_TYPE_1_PARTITIONABLE = True")
    }
    else {
        $lines.Add("")
        $lines.Add("YADOF_RESOURCES_CONFIGURED = False")
    }

    return ($lines -join [Environment]::NewLine)
}

function Write-ManagedPoolConfiguration {
    param([Parameter(Mandatory = $true)][string]$Body)

    $block = @($script:ManagedBlockBegin, $Body.TrimEnd(), $script:ManagedBlockEnd, "") -join [Environment]::NewLine
    $existing = if (Test-Path -LiteralPath $script:CondorLocalConfig -PathType Leaf) {
        [IO.File]::ReadAllText($script:CondorLocalConfig)
    }
    else {
        ""
    }

    # This repository previously used one differently named managed block.  It
    # must not remain active because its role/resource values could override or
    # leak into the hostname-only configuration.  The timestamped backup below
    # keeps the original recoverable.
    foreach ($legacyMarkers in @(
        @("# BEGIN YADOF HTCONDOR NODE", "# END YADOF HTCONDOR NODE"),
        @("# BEGIN YADOF WORKER DECLARED RESOURCES", "# END YADOF WORKER DECLARED RESOURCES"),
        @("# BEGIN YADOF HTCONDOR POOL", "# END YADOF HTCONDOR POOL"),
        @("# BEGIN YADOF RAMDISK EXECUTE", "# END YADOF RAMDISK EXECUTE")
    )) {
        $legacyBegin = $legacyMarkers[0]
        $legacyEnd = $legacyMarkers[1]
        $legacyPattern = "(?ms)^" + [regex]::Escape($legacyBegin) + "\r?\n.*?^" + [regex]::Escape($legacyEnd) + "\r?\n?"
        if ($existing -match [regex]::Escape($legacyBegin)) {
            $existing = [regex]::Replace($existing, $legacyPattern, "")
        }
    }

    $pattern = "(?ms)^" + [regex]::Escape($script:ManagedBlockBegin) + "\r?\n.*?^" + [regex]::Escape($script:ManagedBlockEnd) + "\r?\n?"
    if ($existing -match [regex]::Escape($script:ManagedBlockBegin)) {
        $updated = [regex]::Replace($existing, $pattern, $block)
    }
    elseif ($existing.Trim()) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block
    }
    else {
        $updated = $block
    }

    $parent = Split-Path -Parent $script:CondorLocalConfig
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $script:CondorLocalConfig -PathType Leaf) {
        Copy-Item -LiteralPath $script:CondorLocalConfig -Destination ($script:CondorLocalConfig + ".bak." + (Get-Date -Format "yyyyMMdd-HHmmss-fff")) -Force
    }
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($script:CondorLocalConfig, $updated, $utf8)
    Write-Host "Configuration written: $script:CondorLocalConfig"
}

function Set-YadofFirewallRule {
    param([Parameter(Mandatory = $true)][ValidateRange(1, 65535)][int]$Port)

    Get-NetFirewallRule -DisplayName $script:FirewallRuleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $script:FirewallRuleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port -Profile Any -RemoteAddress Any | Out-Null
    Write-Host "Windows Firewall: inbound TCP $Port is enabled."
}

function Remove-YadofFirewallRule {
    Get-NetFirewallRule -DisplayName $script:FirewallRuleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
}

function Restart-YadofCondor {
    $service = Get-CondorService
    if ($service) {
        Set-Service -Name $service.Name -StartupType Automatic
        $service.Refresh()
        if ($service.Status -eq "Running") {
            Restart-Service -Name $service.Name -Force
        }
        else {
            Start-Service -Name $service.Name
        }
    }
    else {
        $restart = $script:CondorCommands["condor_restart"]
        & $restart -master 2>$null
        if ($LASTEXITCODE -ne 0) {
            $master = Join-Path $script:CondorBinDirectory "condor_master.exe"
            if (-not (Test-Path -LiteralPath $master -PathType Leaf)) {
                throw "No HTCondor Windows service or condor_master.exe was found."
            }
            Start-Process -FilePath $master -WorkingDirectory (Split-Path -Parent $script:CondorBinDirectory) -WindowStyle Hidden
        }
    }
    Start-Sleep -Seconds 4

    $service = Get-CondorService
    if ($service) {
        $service.Refresh()
        if ($service.Status -ne "Running") {
            $configuredMaster = Invoke-CondorConfigVal -Name "MASTER"
            $configuredLog = Invoke-CondorConfigVal -Name "LOG"
            throw "The HTCondor service stopped during startup. Effective MASTER='$configuredMaster', LOG='$configuredLog'. Check the Windows service event and MasterLog."
        }
    }
}

function Stop-YadofCondor {
    $service = Get-CondorService
    if ($service) {
        if ($service.Status -ne "Stopped") {
            Stop-Service -Name $service.Name -Force
        }
        Set-Service -Name $service.Name -StartupType Manual
        Write-Host "HTCondor service stopped; startup type is Manual."
        return
    }

    $masterProcesses = @(Get-Process -Name "condor_master" -ErrorAction SilentlyContinue)
    if ($masterProcesses.Count) {
        $masterProcesses | Stop-Process -Force
        Write-Host "Standalone condor_master process stopped."
    }
}

function Show-EffectiveConfiguration {
    Write-Host ""
    Write-Host "Effective configuration:"
    foreach ($name in @(
        "YADOF_POOL_ROLE", "RELEASE_DIR", "LOCAL_DIR", "CONDOR_HOST", "COLLECTOR_HOST", "DAEMON_LIST",
        "NETWORK_INTERFACE", "BIND_ALL_INTERFACES", "IP_ADDRESS", "EXECUTE", "NUM_CPUS", "MEMORY", "DISK",
        "SLOT_TYPE_1_PARTITIONABLE"
    )) {
        $value = Invoke-CondorConfigVal -Name $name
        if (-not $value) {
            $value = "<not set>"
        }
        Write-Host "  $name = $value"
    }
}

function Wait-YadofPoolRegistration {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Manager", "Worker", "Submit")][string]$Role,
        [Parameter(Mandatory = $true)][string]$ManagerMachineName,
        [Parameter(Mandatory = $true)][ValidateRange(1, 65535)][int]$Port,
        [ValidateRange(5, 300)][int]$TimeoutSeconds = 45
    )

    $status = $script:CondorCommands["condor_status"]
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $localNames = @(Get-UniqueMachineNames -Names @() -ManagerMachineName $env:COMPUTERNAME |
        Where-Object { -not $_.Contains("*") })

    do {
        $oldPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            if ($Role -eq "Manager") {
                $output = @(& $status -pool "${ManagerMachineName}:$Port" -collector -af Name 2>$null)
            }
            elseif ($Role -eq "Submit") {
                $output = @(& $status -pool "${ManagerMachineName}:$Port" -schedd -af Machine 2>$null)
            }
            else {
                $output = @(& $status -pool "${ManagerMachineName}:$Port" -af Machine 2>$null)
            }
            $exitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $oldPreference
        }

        if ($exitCode -eq 0) {
            if ($Role -eq "Manager" -and @($output | Where-Object { ([string]$_).Trim() }).Count -gt 0) {
                Write-Host "Collector registration check: passed."
                return
            }
            if ($Role -in @("Worker", "Submit")) {
                $visibleMachines = @($output | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
                if (@($visibleMachines | Where-Object { $localNames -icontains $_ }).Count -gt 0) {
                    Write-Host "$Role registration check: passed."
                    return
                }
            }
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    if ($Role -eq "Manager") {
        throw "The collector did not answer by machine name within $TimeoutSeconds seconds. Check the HTCondor logs and name resolution."
    }
    throw "This $Role node did not appear at manager '$ManagerMachineName' within $TimeoutSeconds seconds. Check the manager allow-list, firewall, and name resolution."
}

function Set-YadofPoolRole {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Manager", "Worker", "Submit")][string]$Role,
        [Parameter(Mandatory = $true)][string]$ManagerMachineName,
        [Parameter(Mandatory = $true)][string]$NetworkAdapterName,
        [string[]]$AllowedMachineNames = @(),
        [ValidateRange(1, 65535)][int]$Port = 9618
    )

    if (-not (Test-YadofAdministrator)) {
        throw "Administrator privileges are required."
    }
    $current = Get-YadofCurrentConfiguration
    $manager = Assert-MachineName -Name $ManagerMachineName
    $rolePlan = Merge-YadofPoolRoles -Current $current -Role $Role -ManagerMachineName $manager
    Assert-ManagerResolves -ManagerMachineName $manager
    $network = Resolve-YadofNetworkAdapter -AdapterName $NetworkAdapterName
    if ($rolePlan.Role -eq "Manager") {
        Assert-YadofManagerNameMatchesLocalAdapter -ManagerMachineName $manager -NetworkSelection $network
    }

    $allowedNames = @($AllowedMachineNames) + @($current.AllowedMachineNames)
    $body = New-PoolConfigurationBody @rolePlan `
        -AllowedMachineNames $allowedNames -NetworkInterface $network.InterfaceGuid `
        -Port $Port -Resources $current.Resources
    Write-ManagedPoolConfiguration -Body $body
    Set-YadofFirewallRule -Port $Port
    Restart-YadofCondor
    Show-EffectiveConfiguration

    if ((Invoke-CondorConfigVal -Name "YADOF_POOL_ROLE") -ine $rolePlan.Role) {
        throw "HTCondor did not load the newly written role configuration."
    }
    Wait-YadofPoolRegistration -Role $Role -ManagerMachineName $manager -Port $Port
    Write-Host ""
    Write-Host "HTCondor capability enabled successfully: $Role (node role: $($rolePlan.Role))"
}

function Disable-YadofPoolMembership {
    param(
        [ValidateRange(1, 65535)][int]$Port = 9618
    )

    if (-not (Test-YadofAdministrator)) {
        throw "Administrator privileges are required."
    }
    Initialize-YadofCondor
    $localName = Assert-MachineName -Name $env:COMPUTERNAME
    $networkInterface = Invoke-CondorConfigVal -Name "NETWORK_INTERFACE"
    if (-not $networkInterface) {
        $networkInterface = "*"
    }
    $body = New-PoolConfigurationBody -Role "Detached" -ManagerMachineName $localName `
        -AllowedMachineNames @($localName) -NetworkInterface $networkInterface -Port $Port -Resources $null
    Write-ManagedPoolConfiguration -Body $body
    Stop-YadofCondor
    Remove-YadofFirewallRule
    Write-Host ""
    Write-Host "This machine is detached from HTCondor pools."
    Write-Host "The service is stopped and will not rejoin after reboot."
    Write-Host "Run script 2, 3, or 5 to enable it again."
}

function Assert-ResourceValues {
    param(
        [Parameter(Mandatory = $true)][string]$ExecuteDirectory,
        [Parameter(Mandatory = $true)][int]$DeclaredCpus,
        [Parameter(Mandatory = $true)][int64]$DeclaredMemoryMb,
        [Parameter(Mandatory = $true)][int64]$DeclaredDiskMb
    )

    if ($DeclaredCpus -lt 1 -or $DeclaredMemoryMb -lt 1 -or $DeclaredDiskMb -lt 1) {
        throw "CPU, memory, and disk declarations must all be positive integers."
    }
    $fullPath = [IO.Path]::GetFullPath($ExecuteDirectory)
    $root = [IO.Path]::GetPathRoot($fullPath)
    if (-not $root -or -not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "The drive for the execute directory is unavailable: $root"
    }

    $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $detectedCpus = [int]$computer.NumberOfLogicalProcessors
    $detectedMemoryMb = [int64][Math]::Floor([double]$computer.TotalPhysicalMemory / 1MB)
    if ($DeclaredCpus -gt $detectedCpus) {
        throw "DeclaredCpus ($DeclaredCpus) exceeds detected logical CPUs ($detectedCpus)."
    }
    if ($DeclaredMemoryMb -gt $detectedMemoryMb) {
        throw "DeclaredMemoryMb ($DeclaredMemoryMb) exceeds detected physical memory ($detectedMemoryMb MiB)."
    }

    $driveName = $root.TrimEnd("\").TrimEnd(":")
    $drive = Get-PSDrive -Name $driveName -PSProvider FileSystem -ErrorAction Stop
    $freeMb = [int64][Math]::Floor([double]$drive.Free / 1MB)
    if ($DeclaredDiskMb -gt $freeMb) {
        throw "DeclaredDiskMb ($DeclaredDiskMb) exceeds current free space ($freeMb MiB) on $root."
    }
    return $fullPath
}

function Set-ExecuteDirectoryPermissions {
    param([Parameter(Mandatory = $true)][string]$ExecuteDirectory)

    New-Item -ItemType Directory -Force -Path $ExecuteDirectory | Out-Null
    $icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
    & $icacls $ExecuteDirectory /inheritance:e `
        /grant "*S-1-5-18:(OI)(CI)F" `
        "*S-1-5-32-544:(OI)(CI)F" `
        "*S-1-5-32-545:(OI)(CI)M" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Could not set permissions on the execute directory: $ExecuteDirectory"
    }
}

function Set-YadofExecuteResources {
    param(
        [string]$ManagerMachineName = "",
        [Parameter(Mandatory = $true)][string]$NetworkAdapterName,
        [Parameter(Mandatory = $true)][string]$ExecuteDirectory,
        [Parameter(Mandatory = $true)][int]$DeclaredCpus,
        [Parameter(Mandatory = $true)][int64]$DeclaredMemoryMb,
        [Parameter(Mandatory = $true)][int64]$DeclaredDiskMb,
        [ValidateRange(1, 65535)][int]$Port = 9618
    )

    if (-not (Test-YadofAdministrator)) {
        throw "Administrator privileges are required."
    }
    $current = Get-YadofCurrentConfiguration
    if ($current.Role -notin @("Manager", "Worker", "Submit")) {
        throw "Run script 2 (manager), 3 (worker), or 5 (submit) before declaring execute resources."
    }
    $manager = $ManagerMachineName.Trim()
    if (-not $manager) {
        $manager = $current.ManagerMachineName
    }
    $manager = Assert-MachineName -Name $manager
    $rolePlan = Merge-YadofPoolRoles -Current $current -Role Worker -ManagerMachineName $manager
    Assert-ManagerResolves -ManagerMachineName $manager
    $network = Resolve-YadofNetworkAdapter -AdapterName $NetworkAdapterName
    if ($rolePlan.Role -eq "Manager") {
        Assert-YadofManagerNameMatchesLocalAdapter -ManagerMachineName $manager -NetworkSelection $network
    }

    $allowedNames = if ($current.AllowedMachineNames.Count) { $current.AllowedMachineNames } else { @("*") }
    $fullPath = Assert-ResourceValues -ExecuteDirectory $ExecuteDirectory `
        -DeclaredCpus $DeclaredCpus -DeclaredMemoryMb $DeclaredMemoryMb -DeclaredDiskMb $DeclaredDiskMb
    Set-ExecuteDirectoryPermissions -ExecuteDirectory $fullPath

    $resources = @{
        ExecuteDirectory = $fullPath
        DeclaredCpus = $DeclaredCpus
        DeclaredMemoryMb = $DeclaredMemoryMb
        DeclaredDiskMb = $DeclaredDiskMb
    }
    $body = New-PoolConfigurationBody @rolePlan `
        -AllowedMachineNames $allowedNames -NetworkInterface $network.InterfaceGuid `
        -Port $Port -Resources $resources
    Write-ManagedPoolConfiguration -Body $body
    Set-YadofFirewallRule -Port $Port
    Restart-YadofCondor
    Show-EffectiveConfiguration

    foreach ($expected in @{
        EXECUTE = ($fullPath.TrimEnd("\") -replace "\\", "/")
        NUM_CPUS = [string]$DeclaredCpus
        MEMORY = [string]$DeclaredMemoryMb
        DISK = [string]([int64]$DeclaredDiskMb * 1024)
    }.GetEnumerator()) {
        $actual = Invoke-CondorConfigVal -Name $expected.Key
        if ($actual -ine $expected.Value) {
            throw "Verification failed for $($expected.Key): expected '$($expected.Value)', got '$actual'."
        }
    }
    Wait-YadofPoolRegistration -Role "Worker" -ManagerMachineName $manager -Port $Port
    Write-Host ""
    Write-Host "Execute directory and declared resources configured successfully."
}

Export-ModuleMember -Function @(
    "Test-YadofAdministrator",
    "Start-YadofElevatedScript",
    "Show-YadofNetworkAdapters",
    "Get-YadofCurrentConfiguration",
    "Set-YadofPoolRole",
    "Disable-YadofPoolMembership",
    "Set-YadofExecuteResources"
)
