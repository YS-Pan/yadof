[CmdletBinding()]
param(
    [ValidateSet("Configure", "Diagnose")]
    [string]$Action = "Configure",

    [ValidateSet("Manager", "Worker")]
    [string]$Role,

    [string]$ManagerHost = "",

    [string]$AdvertiseAddress = "",

    [string]$NetworkInterface = "*",

    [ValidateRange(1, 65535)]
    [int]$Port = 9618,

    [string]$AllowedNetwork = "",

    [string]$AllowedHostPattern = "",

    [string]$CondorLocation = "",

    [switch]$EnableExecute,

    [ValidateRange(0, 1048576)]
    [int]$DeclaredCpus = 0,

    [ValidateRange(0, 2147483647)]
    [int]$DeclaredMemoryMb = 0,

    [ValidateRange(0, 2147483647)]
    [int]$DeclaredDiskMb = 0,

    [string]$ExecuteDir = "",

    [string]$PythonExecutable = "",

    [string[]]$ExcludeStarterThreadVariable = @(),

    [string[]]$StarterThreadVariable = @(),

    [ValidateRange(0, 300)]
    [int]$VerificationTimeoutSec = 60,

    [switch]$DryRun
)

<##
.SYNOPSIS
Configures or inspects one Windows HTCondor pool node.

.DESCRIPTION
The Configure action owns one marked block in HTCondor's local configuration.  It
sets the pool role and, when requested, the execute directory, advertised resources,
and optional starter-thread exclusions in one restart.  It does not persist PATH or
machine-specific environment variables.

Use a stable manager DNS name for -ManagerHost on every node, including the manager
itself.  Every submit and execute host must resolve that name.  By default,
NETWORK_INTERFACE is `*`, so HTCondor follows active local interfaces instead of a
DHCP address.  -AdvertiseAddress is used only to derive a default firewall scope;
it is not written to NETWORK_INTERFACE.
##>

$ErrorActionPreference = "Stop"
$script:CondorBinDir = $null
$script:CondorRootDir = $null
$script:CondorCommands = @{}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-Administrator {
    if (-not (Test-IsAdministrator)) {
        throw "Run the Configure action from an elevated Administrator PowerShell session."
    }
}

function Get-CondorBinCandidates {
    $candidates = New-Object System.Collections.Generic.List[string]

    if ($CondorLocation) {
        $candidates.Add((Join-Path $CondorLocation "bin"))
    }
    if ($env:CONDOR_LOCATION) {
        $candidates.Add((Join-Path $env:CONDOR_LOCATION "bin"))
    }
    foreach ($path in @(
        (Join-Path $env:ProgramFiles "HTCondor\bin"),
        (Join-Path $env:ProgramFiles "Condor\bin")
    )) {
        if ($path) {
            $candidates.Add($path)
        }
    }

    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $candidates.Add((Join-Path $programFilesX86 "HTCondor\bin"))
        $candidates.Add((Join-Path $programFilesX86 "Condor\bin"))
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
        if ($masterPath) {
            if (Test-Path -LiteralPath $masterPath -PathType Leaf) {
                $candidates.Add((Split-Path -Parent $masterPath))
            }
        }
    }

    return @($candidates | Where-Object { $_ } | Select-Object -Unique)
}

function Find-CondorCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }

    foreach ($directory in Get-CondorBinCandidates) {
        $candidate = Join-Path $directory "$Name.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $searched = (Get-CondorBinCandidates) -join [Environment]::NewLine
    throw "Could not find $Name.exe. Searched PATH and:`n$searched`nPass -CondorLocation <HTCondor install root> when needed."
}

function Initialize-Condor {
    foreach ($name in @("condor_config_val", "condor_restart", "condor_status")) {
        $script:CondorCommands[$name] = Find-CondorCommand -Name $name
    }

    $script:CondorBinDir = Split-Path -Parent $script:CondorCommands["condor_config_val"]
    $script:CondorRootDir = Split-Path -Parent $script:CondorBinDir
    if (($env:PATH -split ";") -notcontains $script:CondorBinDir) {
        $env:PATH = "$script:CondorBinDir;$env:PATH"
    }

    $rootConfigCandidates = @(
        [Environment]::GetEnvironmentVariable("CONDOR_CONFIG", "Machine"),
        $env:CONDOR_CONFIG,
        (Join-Path $script:CondorRootDir "condor_config"),
        (Join-Path $script:CondorRootDir "etc\condor_config")
    ) | Where-Object { $_ } | Select-Object -Unique

    $rootConfig = $rootConfigCandidates | Where-Object {
        Test-Path -LiteralPath $_ -PathType Leaf
    } | Select-Object -First 1
    if ($rootConfig) {
        $env:CONDOR_CONFIG = $rootConfig
    }

    Write-Host "HTCondor bin: $script:CondorBinDir"
    if ($env:CONDOR_CONFIG) {
        Write-Host "CONDOR_CONFIG: $env:CONDOR_CONFIG"
    }
}

function Get-CondorConfigValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    $value = & $script:CondorCommands["condor_config_val"] $Name 2>$null |
        Select-Object -First 1
    if ($LASTEXITCODE -eq 0 -and $null -ne $value) {
        return ([string]$value).Trim()
    }
    return ""
}

function Get-RootConfigPath {
    $candidates = @(
        $env:CONDOR_CONFIG,
        (Join-Path $script:CondorRootDir "condor_config"),
        (Join-Path $script:CondorRootDir "etc\condor_config")
    ) | Where-Object { $_ } | Select-Object -Unique

    $existing = $candidates | Where-Object {
        Test-Path -LiteralPath $_ -PathType Leaf
    } | Select-Object -First 1
    if ($existing) {
        return $existing
    }
    return (Join-Path $script:CondorRootDir "condor_config")
}

function Ensure-RootIncludesLocalConfig {
    param([Parameter(Mandatory = $true)][string]$LocalConfigPath)

    $rootConfig = Get-RootConfigPath
    $localForCondor = $LocalConfigPath -replace "\\", "/"
    $begin = "# BEGIN YADOF HTCONDOR LOCAL CONFIG INCLUDE"
    $end = "# END YADOF HTCONDOR LOCAL CONFIG INCLUDE"
    $include = @(
        $begin,
        "LOCAL_CONFIG_FILE = $localForCondor",
        $end,
        ""
    ) -join [Environment]::NewLine

    $existing = if (Test-Path -LiteralPath $rootConfig -PathType Leaf) {
        [IO.File]::ReadAllText($rootConfig)
    }
    else {
        ""
    }
    if ($existing -match [regex]::Escape($localForCondor)) {
        return
    }

    $pattern = "(?ms)^# BEGIN YADOF HTCONDOR LOCAL CONFIG INCLUDE\r?\n.*?^# END YADOF HTCONDOR LOCAL CONFIG INCLUDE\r?\n?"
    if ($existing -match [regex]::Escape($begin)) {
        $updated = [regex]::Replace($existing, $pattern, $include)
    }
    elseif ($existing.Trim()) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $include
    }
    else {
        $updated = $include
    }

    Write-Host "Ensuring root config loads: $LocalConfigPath"
    if ($DryRun) {
        return
    }

    $parent = Split-Path -Parent $rootConfig
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $rootConfig -PathType Leaf) {
        Copy-Item -LiteralPath $rootConfig -Destination "$rootConfig.bak.$(Get-Date -Format yyyyMMdd-HHmmss)" -Force
    }
    [IO.File]::WriteAllText($rootConfig, $updated, [Text.Encoding]::ASCII)
    $env:CONDOR_CONFIG = $rootConfig
}

function Get-LocalConfigPath {
    $configured = Get-CondorConfigValue -Name "LOCAL_CONFIG_FILE"
    if ($configured) {
        foreach ($candidate in $configured -split ",") {
            $path = $candidate.Trim().Trim('"')
            if ($path -and -not $path.Contains('$(')) {
                return $path
            }
        }
    }

    $fallback = Join-Path $script:CondorRootDir "condor_config.local"
    Ensure-RootIncludesLocalConfig -LocalConfigPath $fallback
    return $fallback
}

function Set-ManagedConfigBlock {
    param(
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [Parameter(Mandatory = $true)][string]$Body
    )

    $begin = "# BEGIN YADOF HTCONDOR NODE"
    $end = "# END YADOF HTCONDOR NODE"
    $block = @($begin, $Body.TrimEnd(), $end, "") -join [Environment]::NewLine
    $existing = if (Test-Path -LiteralPath $TargetPath -PathType Leaf) {
        [IO.File]::ReadAllText($TargetPath)
    }
    else {
        ""
    }
    $pattern = "(?ms)^# BEGIN YADOF HTCONDOR NODE\r?\n.*?^# END YADOF HTCONDOR NODE\r?\n?"
    if ($existing -match [regex]::Escape($begin)) {
        $updated = [regex]::Replace($existing, $pattern, $block)
    }
    elseif ($existing.Trim()) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block
    }
    else {
        $updated = $block
    }

    Write-Host "Writing managed configuration block: $TargetPath"
    if ($DryRun) {
        Write-Host $block
        return
    }

    $parent = Split-Path -Parent $TargetPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $TargetPath -PathType Leaf) {
        Copy-Item -LiteralPath $TargetPath -Destination "$TargetPath.bak.$(Get-Date -Format yyyyMMdd-HHmmss)" -Force
    }
    [IO.File]::WriteAllText($TargetPath, $updated, [Text.Encoding]::ASCII)
}

function Test-UsableIPv4 {
    param([string]$Address)

    $parsed = $null
    return (
        [Net.IPAddress]::TryParse($Address, [ref]$parsed) -and
        $parsed.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and
        $Address -notlike "127.*" -and
        $Address -notlike "169.254.*" -and
        $Address -notlike "0.*" -and
        $Address -notlike "255.*"
    )
}

function Get-PrimaryIPv4 {
    if ($AdvertiseAddress) {
        if (-not (Test-UsableIPv4 -Address $AdvertiseAddress)) {
            throw "AdvertiseAddress must be a usable IPv4 address: $AdvertiseAddress"
        }
        $match = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -eq $AdvertiseAddress } |
            Select-Object -First 1
        if (-not $match) {
            throw "AdvertiseAddress is not configured on this machine: $AdvertiseAddress"
        }
        return $match
    }

    $routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric, InterfaceMetric)
    foreach ($route in $routes) {
        $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue |
            Where-Object { Test-UsableIPv4 -Address $_.IPAddress } |
            Sort-Object PrefixLength -Descending)
        if ($addresses.Count) {
            return $addresses[0]
        }
    }
    throw "Could not choose a usable IPv4 address. Pass -AdvertiseAddress explicitly."
}

function ConvertTo-IPv4Int {
    param([Parameter(Mandatory = $true)][string]$Address)

    $bytes = [Net.IPAddress]::Parse($Address).GetAddressBytes()
    return ([uint32]$bytes[0] -shl 24) -bor ([uint32]$bytes[1] -shl 16) -bor ([uint32]$bytes[2] -shl 8) -bor [uint32]$bytes[3]
}

function ConvertFrom-IPv4Int {
    param([Parameter(Mandatory = $true)][uint32]$Value)

    $bytes = [byte[]](
        (($Value -shr 24) -band 255),
        (($Value -shr 16) -band 255),
        (($Value -shr 8) -band 255),
        ($Value -band 255)
    )
    return ([Net.IPAddress]::new($bytes)).ToString()
}

function Get-NetworkCidr {
    param(
        [Parameter(Mandatory = $true)][string]$Address,
        [Parameter(Mandatory = $true)][ValidateRange(0, 32)][int]$PrefixLength
    )

    if ($PrefixLength -eq 0) {
        return "0.0.0.0/0"
    }
    $mask = if ($PrefixLength -eq 32) {
        [uint32]::MaxValue
    }
    else {
        [uint32]::MaxValue -shl (32 - $PrefixLength)
    }
    return "$(ConvertFrom-IPv4Int -Value ((ConvertTo-IPv4Int -Address $Address) -band $mask))/$PrefixLength"
}

function Get-CondorAllowPattern {
    param(
        [Parameter(Mandatory = $true)][string]$Address,
        [Parameter(Mandatory = $true)][int]$PrefixLength
    )

    $parts = $Address.Split(".")
    if ($PrefixLength -ge 24) {
        return "$($parts[0]).$($parts[1]).$($parts[2]).*"
    }
    if ($PrefixLength -ge 16) {
        return "$($parts[0]).$($parts[1]).*.*"
    }
    if ($PrefixLength -ge 8) {
        return "$($parts[0]).*.*.*"
    }
    return "*"
}

function Ensure-ExecuteDirectory {
    param([Parameter(Mandatory = $true)][string]$PathText)

    $fullPath = [IO.Path]::GetFullPath($PathText)
    $root = [IO.Path]::GetPathRoot($fullPath)
    if (-not $root -or -not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "The execute directory drive is unavailable: $root"
    }
    Write-Host "Ensuring execute directory: $fullPath"
    if ($DryRun) {
        return $fullPath
    }

    New-Item -ItemType Directory -Force -Path $fullPath | Out-Null
    $icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
    & $icacls $fullPath /grant "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-11:(OI)(CI)M" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "icacls could not grant slot-user access to $fullPath"
    }
    return $fullPath
}

function Ensure-PythonAccess {
    param([string]$Executable)

    if (-not $Executable) {
        return
    }
    $resolved = $Executable
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        $command = Get-Command $Executable -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            $resolved = $command.Source
        }
        else {
            throw "PythonExecutable was not found: $Executable"
        }
    }

    $pythonHome = Split-Path -Parent $resolved
    Write-Host "Granting slot users read/execute access to: $pythonHome"
    if ($DryRun) {
        return
    }
    $icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
    & $icacls $pythonHome /grant "*S-1-5-11:(OI)(CI)RX" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "icacls could not grant slot-user access to $pythonHome"
    }
}

function Ensure-FirewallRule {
    param([Parameter(Mandatory = $true)][string]$RemoteAddress)

    $name = "YADOF HTCondor TCP $Port"
    Write-Host "Ensuring firewall rule '$name' for $RemoteAddress"
    if ($DryRun) {
        return
    }
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP `
        -LocalPort $Port -Profile Any -RemoteAddress $RemoteAddress | Out-Null
}

function Get-CondorService {
    return Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*condor*" -or $_.DisplayName -like "*condor*" } |
        Sort-Object Name |
        Select-Object -First 1
}

function Restart-Condor {
    Write-Host "Restarting HTCondor..."
    if ($DryRun) {
        return
    }

    $service = Get-CondorService
    if ($service) {
        if ($service.Status -eq "Running") {
            Restart-Service -Name $service.Name -Force
        }
        else {
            Start-Service -Name $service.Name
        }
    }
    else {
        & $script:CondorCommands["condor_restart"] -master 2>$null
        if ($LASTEXITCODE -ne 0) {
            $master = Join-Path $script:CondorBinDir "condor_master.exe"
            if (-not (Test-Path -LiteralPath $master -PathType Leaf)) {
                throw "No HTCondor Windows service was found, condor_restart -master failed, and condor_master.exe is missing: $master"
            }
            Write-Warning "No HTCondor Windows service was found. Starting condor_master.exe directly."
            Start-Process -FilePath $master -WorkingDirectory $script:CondorRootDir -WindowStyle Hidden
        }
    }
    Start-Sleep -Seconds 5
}

function Get-UniqueNames {
    param([string[]]$Names)

    $seen = @{}
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($name in $Names) {
        foreach ($part in ([string]$name -split "[,\s]+")) {
            if ($part -and -not $seen.ContainsKey($part.ToUpperInvariant())) {
                $seen[$part.ToUpperInvariant()] = $true
                $result.Add($part)
            }
        }
    }
    return @($result)
}

function Resolve-StarterThreadVariables {
    if (-not $ExcludeStarterThreadVariable.Count) {
        return ""
    }

    $source = if ($StarterThreadVariable.Count) {
        Get-UniqueNames -Names $StarterThreadVariable
    }
    else {
        Get-UniqueNames -Names @((Get-CondorConfigValue -Name "STARTER_NUM_THREADS_ENV_VARS"))
    }
    if (-not $source.Count) {
        throw "Could not read STARTER_NUM_THREADS_ENV_VARS. Supply -StarterThreadVariable explicitly before excluding a variable."
    }

    $excluded = @{}
    foreach ($name in Get-UniqueNames -Names $ExcludeStarterThreadVariable) {
        $excluded[$name.ToUpperInvariant()] = $true
    }
    $retained = @($source | Where-Object { -not $excluded.ContainsKey($_.ToUpperInvariant()) })
    if (-not $retained.Count) {
        throw "Excluding the requested starter-thread variables would leave an empty list."
    }
    foreach ($name in $excluded.Keys) {
        if ($source | Where-Object { $_.ToUpperInvariant() -eq $name }) {
            Write-Host "Excluding starter thread variable: $name"
        }
        else {
            Write-Warning "Starter thread variable was not present in the source list: $name"
        }
    }
    return ($retained -join " ")
}

function New-ConfigBody {
    param(
        [Parameter(Mandatory = $true)][string]$ManagerEndpoint,
        [Parameter(Mandatory = $true)][string]$HostAllowPattern,
        [Parameter(Mandatory = $true)][bool]$ConfigureExecute
    )

    $daemonNames = if ($Role -eq "Manager") {
        @("MASTER", "SHARED_PORT", "COLLECTOR", "NEGOTIATOR", "SCHEDD")
    }
    else {
        @("MASTER", "SHARED_PORT")
    }
    if ($ConfigureExecute) {
        $daemonNames += "STARTD"
    }

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# Generated by admin_tool/htcondor_pool/htcondor_pool.ps1")
    $lines.Add("CONDOR_HOST = $ManagerEndpoint")
    $lines.Add('COLLECTOR_HOST = $(CONDOR_HOST):' + $Port)
    $lines.Add("NETWORK_INTERFACE = $NetworkInterface")
    $lines.Add("")
    $lines.Add("USE_SHARED_PORT = TRUE")
    $lines.Add("SHARED_PORT_PORT = $Port")
    $lines.Add("DAEMON_LIST = $($daemonNames -join ', ')")
    $lines.Add("")
    foreach ($macro in @("ALLOW_READ", "ALLOW_WRITE", "ALLOW_ADMINISTRATOR", "ALLOW_DAEMON", "ALLOW_NEGOTIATOR", "ALLOW_ADVERTISE_MASTER", "ALLOW_ADVERTISE_STARTD", "ALLOW_ADVERTISE_SCHEDD")) {
        $lines.Add("$macro = $HostAllowPattern")
    }
    $lines.Add("SEC_DEFAULT_AUTHENTICATION = OPTIONAL")
    $lines.Add("SEC_DEFAULT_ENCRYPTION = OPTIONAL")
    $lines.Add("SEC_DEFAULT_INTEGRITY = OPTIONAL")
    $lines.Add("")
    $lines.Add("START = TRUE")
    $lines.Add("SUSPEND = FALSE")
    $lines.Add("PREEMPT = FALSE")
    $lines.Add("KILL = FALSE")
    $lines.Add("WANT_SUSPEND = FALSE")
    $lines.Add("WANT_VACATE = FALSE")

    if ($ConfigureExecute) {
        $executePath = Ensure-ExecuteDirectory -PathText $ExecuteDir
        Ensure-PythonAccess -Executable $PythonExecutable
        $executeForCondor = $executePath.TrimEnd("\\") -replace "\\", "/"
        $diskKb = [int64]$DeclaredDiskMb * 1024
        $existingStartdAttrs = Get-CondorConfigValue -Name "STARTD_ATTRS"
        $startdAttrs = Get-UniqueNames -Names @($existingStartdAttrs, "YADOF_EXECUTE_READY", "YADOF_EXECUTE_DIR", "YADOF_DECLARED_CPUS", "YADOF_DECLARED_MEMORY_MB", "YADOF_DECLARED_DISK_MB")

        $lines.Add("")
        $lines.Add("NUM_CPUS = $DeclaredCpus")
        $lines.Add("MEMORY = $DeclaredMemoryMb")
        $lines.Add("DISK = $diskKb")
        $lines.Add("EXECUTE = $executeForCondor")
        $lines.Add("YADOF_EXECUTE_READY = True")
        $lines.Add("YADOF_EXECUTE_DIR = `"$executeForCondor`"")
        $lines.Add("YADOF_DECLARED_CPUS = $DeclaredCpus")
        $lines.Add("YADOF_DECLARED_MEMORY_MB = $DeclaredMemoryMb")
        $lines.Add("YADOF_DECLARED_DISK_MB = $DeclaredDiskMb")
        $lines.Add("STARTD_ATTRS = $($startdAttrs -join ', ')")
        $lines.Add("NUM_SLOTS = 1")
        $lines.Add("NUM_SLOTS_TYPE_1 = 1")
        $lines.Add("SLOT_TYPE_1 = cpus=100%, ram=100%, disk=100%")
        $lines.Add("SLOT_TYPE_1_PARTITIONABLE = True")
    }

    $starterVariables = Resolve-StarterThreadVariables
    if ($starterVariables) {
        $lines.Add("")
        $lines.Add("STARTER_NUM_THREADS_ENV_VARS = $starterVariables")
    }
    return ($lines -join [Environment]::NewLine)
}

function Show-ConfigurationSummary {
    Write-Host ""
    Write-Host "Effective HTCondor configuration:"
    foreach ($name in @("CONDOR_HOST", "COLLECTOR_HOST", "NETWORK_INTERFACE", "DAEMON_LIST", "EXECUTE", "NUM_CPUS", "MEMORY", "DISK", "SLOT_TYPE_1_PARTITIONABLE", "STARTER_NUM_THREADS_ENV_VARS", "STARTD_ATTRS")) {
        $value = Get-CondorConfigValue -Name $name
        if (-not $value) {
            $value = "<undefined>"
        }
        Write-Host "  $name = $value"
    }
}

function Show-PoolStatus {
    param([string]$Endpoint)

    $poolArguments = @()
    if ($Endpoint) {
        $poolArguments = @("-pool", "${Endpoint}:$Port")
    }
    Write-Host ""
    Write-Host "Visible execute slots:"
    & $script:CondorCommands["condor_status"] @poolArguments -af Name Machine Cpus Memory Disk State Activity OpSys YADOF_EXECUTE_READY 2>$null | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "condor_status could not query the pool yet. Verify manager reachability and wait for daemon registration."
    }
}

function Wait-ForPoolStatus {
    param([Parameter(Mandatory = $true)][string]$Endpoint)

    if ($DryRun -or $VerificationTimeoutSec -eq 0) {
        return
    }
    $deadline = (Get-Date).AddSeconds($VerificationTimeoutSec)
    do {
        & $script:CondorCommands["condor_status"] -pool "${Endpoint}:$Port" -any -limit 1 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Show-PoolStatus -Endpoint $Endpoint
            return
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)
    Write-Warning "The collector did not answer within $VerificationTimeoutSec seconds. Run the Diagnose action after checking firewall and manager reachability."
}

function Invoke-Diagnose {
    $endpoint = $ManagerHost
    if (-not $endpoint) {
        $endpoint = Get-CondorConfigValue -Name "CONDOR_HOST"
    }
    Write-Host "HTCondor root: $script:CondorRootDir"
    Write-Host "Manager endpoint: $endpoint"
    Show-ConfigurationSummary
    Show-PoolStatus -Endpoint $endpoint
}

if ($Action -eq "Configure") {
    if (-not $Role) {
        throw "Configure requires -Role Manager or -Role Worker."
    }
    if (-not $DryRun) {
        Assert-Administrator
    }
}

Initialize-Condor

if ($Action -ne "Configure") {
    Invoke-Diagnose
    return
}

$primaryAddress = Get-PrimaryIPv4
$localAddress = [string]$primaryAddress.IPAddress
$prefixLength = [int]$primaryAddress.PrefixLength
$network = if ($AllowedNetwork) {
    $AllowedNetwork
}
else {
    Get-NetworkCidr -Address $localAddress -PrefixLength $prefixLength
}
$hostPattern = if ($AllowedHostPattern) {
    $AllowedHostPattern
}
else {
    Get-CondorAllowPattern -Address $localAddress -PrefixLength $prefixLength
}

$configureExecute = ($Role -eq "Worker") -or $EnableExecute.IsPresent
if ($configureExecute) {
    if ($DeclaredCpus -lt 1 -or $DeclaredMemoryMb -lt 1 -or $DeclaredDiskMb -lt 1) {
        throw "Execute nodes require positive -DeclaredCpus, -DeclaredMemoryMb, and -DeclaredDiskMb values."
    }
    if (-not $ExecuteDir) {
        $ExecuteDir = Join-Path ([IO.Path]::GetTempPath()) "htcondor_execute"
    }
}

if (-not $ManagerHost) {
    throw "Configure requires -ManagerHost <stable manager DNS name> on both manager and worker nodes."
}
$managerEndpoint = $ManagerHost

Write-Host "Role: $Role"
Write-Host "Local address: $localAddress/$prefixLength"
Write-Host "Manager endpoint: $managerEndpoint"
Write-Host "NETWORK_INTERFACE: $NetworkInterface"
Write-Host "Allowed firewall network: $network"
Write-Host "HTCondor allow pattern: $hostPattern"
Write-Host "Configure execute resources: $configureExecute"

$configBody = New-ConfigBody -ManagerEndpoint $managerEndpoint -HostAllowPattern $hostPattern -ConfigureExecute $configureExecute
$targetConfig = Get-LocalConfigPath
Set-ManagedConfigBlock -TargetPath $targetConfig -Body $configBody
Ensure-FirewallRule -RemoteAddress $network
Restart-Condor
Show-ConfigurationSummary
Wait-ForPoolStatus -Endpoint $managerEndpoint

Write-Host ""
Write-Host "HTCondor node configuration completed."
