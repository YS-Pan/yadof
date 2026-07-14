[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Manager", "Worker")]
    [string]$Role,

    [Parameter(Mandatory = $true)]
    [string]$MachineLabel,

    [int]$Port = 9618,

    [int]$JobCpus = 4,

    [int]$JobMemoryMb = 8192,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$script:CondorCommands = @{}
$script:CondorBinDir = $null
$script:CondorRootDir = $null
$script:ScriptDir = Split-Path -Parent $PSCommandPath
$script:ManagerIpFile = Join-Path $script:ScriptDir "manager_ip.txt"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an elevated Administrator shell."
    }
}

function Get-CondorBinCandidates {
    $dirs = New-Object System.Collections.Generic.List[string]

    if ($env:CONDOR_LOCATION) {
        $dirs.Add((Join-Path $env:CONDOR_LOCATION "bin"))
    }
    foreach ($dir in @(
        "$env:ProgramFiles\Condor\bin",
        "$env:ProgramFiles\HTCondor\bin"
    )) {
        if ($dir) {
            $dirs.Add($dir)
        }
    }

    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $dirs.Add((Join-Path $programFilesX86 "Condor\bin"))
        $dirs.Add((Join-Path $programFilesX86 "HTCondor\bin"))
    }

    $services = @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*condor*" -or $_.DisplayName -like "*HTCondor*" })
    foreach ($service in $services) {
        $rawPath = [string]$service.PathName
        if (-not $rawPath) {
            continue
        }
        $exePath = $null
        if ($rawPath -match '^\s*"([^"]+condor_master\.exe)"') {
            $exePath = $matches[1]
        }
        elseif ($rawPath -match '^\s*([^"]*condor_master\.exe)') {
            $exePath = $matches[1]
        }
        if ($exePath -and (Test-Path -LiteralPath $exePath)) {
            $dirs.Add((Split-Path -Parent $exePath))
        }
    }

    return @($dirs | Where-Object { $_ } | Select-Object -Unique)
}

function Find-CondorCommand {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    foreach ($dir in Get-CondorBinCandidates) {
        $candidate = Join-Path $dir "$Name.exe"
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    $searched = (Get-CondorBinCandidates) -join ", "
    throw "Required HTCondor command '$Name.exe' was not found. Searched PATH and: $searched"
}

function Initialize-CondorCommands {
    foreach ($name in @("condor_config_val", "condor_status", "condor_restart")) {
        $script:CondorCommands[$name] = Find-CondorCommand $name
    }

    $binDir = Split-Path -Parent $script:CondorCommands["condor_config_val"]
    $script:CondorBinDir = $binDir
    $script:CondorRootDir = Split-Path -Parent $binDir
    $pathParts = @($env:PATH -split ";" | Where-Object { $_ })
    if ($pathParts -notcontains $binDir) {
        $env:PATH = "$binDir;$env:PATH"
    }
    Write-Host "Using HTCondor binaries from: $binDir"
}

function ConvertTo-IPv4Int {
    param([string]$IpAddress)
    $bytes = [Net.IPAddress]::Parse($IpAddress).GetAddressBytes()
    return ([uint32]$bytes[0] -shl 24) -bor ([uint32]$bytes[1] -shl 16) -bor ([uint32]$bytes[2] -shl 8) -bor [uint32]$bytes[3]
}

function ConvertFrom-IPv4Int {
    param([uint32]$Value)
    $bytes = [byte[]](
        (($Value -shr 24) -band 255),
        (($Value -shr 16) -band 255),
        (($Value -shr 8) -band 255),
        ($Value -band 255)
    )
    return ([Net.IPAddress]::new($bytes)).ToString()
}

function Get-SubnetMaskInt {
    param([int]$PrefixLength)
    if ($PrefixLength -le 0) {
        return [uint32]0
    }
    if ($PrefixLength -ge 32) {
        return [uint32]::MaxValue
    }
    return ([uint32]::MaxValue -shl (32 - $PrefixLength))
}

function Get-NetworkCidr {
    param(
        [string]$IpAddress,
        [int]$PrefixLength
    )
    $mask = Get-SubnetMaskInt -PrefixLength $PrefixLength
    $network = (ConvertTo-IPv4Int $IpAddress) -band $mask
    return "$(ConvertFrom-IPv4Int $network)/$PrefixLength"
}

function Get-AllowPattern {
    param(
        [string]$IpAddress,
        [int]$PrefixLength
    )
    $parts = $IpAddress.Split(".")
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

function Test-UsableIPv4 {
    param([string]$IpAddress)
    return (
        $IpAddress -and
        $IpAddress -ne "127.0.0.1" -and
        -not $IpAddress.StartsWith("169.254.") -and
        -not $IpAddress.StartsWith("0.") -and
        -not $IpAddress.StartsWith("255.")
    )
}

function Test-PrivateIPv4 {
    param([string]$IpAddress)
    if (-not (Test-UsableIPv4 $IpAddress)) {
        return $false
    }
    $parts = @($IpAddress.Split(".") | ForEach-Object { [int]$_ })
    return (
        $parts[0] -eq 10 -or
        ($parts[0] -eq 192 -and $parts[1] -eq 168) -or
        ($parts[0] -eq 172 -and $parts[1] -ge 16 -and $parts[1] -le 31)
    )
}

function Get-PrimaryIPv4 {
    $routeCandidates = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric, InterfaceMetric)

    foreach ($route in $routeCandidates) {
        $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue |
            Where-Object { Test-UsableIPv4 $_.IPAddress } |
            Sort-Object @{ Expression = { Test-PrivateIPv4 $_.IPAddress }; Descending = $true }, PrefixLength -Descending)
        if ($addresses.Count -gt 0) {
            return $addresses[0]
        }
    }

    $upAdapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq "Up" })
    foreach ($adapter in $upAdapters) {
        $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $adapter.ifIndex -ErrorAction SilentlyContinue |
            Where-Object { Test-UsableIPv4 $_.IPAddress } |
            Sort-Object @{ Expression = { Test-PrivateIPv4 $_.IPAddress }; Descending = $true }, PrefixLength -Descending)
        if ($addresses.Count -gt 0) {
            return $addresses[0]
        }
    }

    throw "Could not find a usable IPv4 address. Connect this machine to the modem/router LAN and try again."
}

function Get-ScanCandidates {
    param(
        [string]$OwnIp,
        [int]$PrefixLength
    )

    $scanPrefix = $PrefixLength
    if ($scanPrefix -lt 24) {
        $scanPrefix = 24
    }
    if ($scanPrefix -gt 30) {
        $scanPrefix = 24
    }

    $mask = Get-SubnetMaskInt -PrefixLength $scanPrefix
    $network = (ConvertTo-IPv4Int $OwnIp) -band $mask
    $hostCount = [math]::Pow(2, 32 - $scanPrefix)
    if ($hostCount -gt 512) {
        $scanPrefix = 24
        $mask = Get-SubnetMaskInt -PrefixLength $scanPrefix
        $network = (ConvertTo-IPv4Int $OwnIp) -band $mask
        $hostCount = [math]::Pow(2, 32 - $scanPrefix)
    }

    $start = [uint32]($network + 1)
    $end = [uint32]($network + [uint32]$hostCount - 2)
    $own = ConvertTo-IPv4Int $OwnIp
    $result = New-Object System.Collections.Generic.List[string]
    for ($value = $start; $value -le $end; $value++) {
        if ([uint32]$value -ne $own) {
            $result.Add((ConvertFrom-IPv4Int ([uint32]$value)))
        }
    }
    return $result
}

function Test-TcpPort {
    param(
        [string]$IpAddress,
        [int]$Port,
        [int]$TimeoutMs = 250
    )

    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($IpAddress, $Port)
        if (-not $task.Wait($TimeoutMs)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
        $client.Dispose()
    }
}

function Find-OpenPortCandidates {
    param(
        [string[]]$Candidates,
        [int]$Port,
        [int]$TimeoutMs = 7000
    )

    $items = New-Object System.Collections.Generic.List[object]
    foreach ($ip in $Candidates) {
        $client = [Net.Sockets.TcpClient]::new()
        try {
            $task = $client.ConnectAsync($ip, $Port)
            $items.Add([pscustomobject]@{
                Ip = $ip
                Client = $client
                Task = $task
            })
        }
        catch {
            $client.Close()
            $client.Dispose()
        }
    }

    $deadline = (Get-Date).AddMilliseconds($TimeoutMs)
    do {
        Start-Sleep -Milliseconds 100
        $done = @($items | Where-Object { $_.Task.IsCompleted })
        if ($done.Count -eq $items.Count) {
            break
        }
    } while ((Get-Date) -lt $deadline)

    $open = New-Object System.Collections.Generic.List[string]
    foreach ($item in $items) {
        try {
            if ($item.Task.IsCompleted -and $item.Client.Connected) {
                $open.Add($item.Ip)
            }
        }
        finally {
            $item.Client.Close()
            $item.Client.Dispose()
        }
    }
    return $open
}

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutMs = 15000
    )

    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    $psi.Arguments = ($Arguments -join " ")
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    $process = [Diagnostics.Process]::Start($psi)
    if (-not $process.WaitForExit($TimeoutMs)) {
        try {
            $process.Kill()
        }
        catch {
        }
        return [pscustomobject]@{
            ExitCode = -1
            StdOut = ""
            StdErr = "timed out after $TimeoutMs ms"
            TimedOut = $true
        }
    }

    return [pscustomobject]@{
        ExitCode = [int]$process.ExitCode
        StdOut = $process.StandardOutput.ReadToEnd()
        StdErr = $process.StandardError.ReadToEnd()
        TimedOut = $false
    }
}

function Test-CondorCollector {
    param([string]$IpAddress)
    $pool = "${IpAddress}:$Port"
    $condorStatus = $script:CondorCommands["condor_status"]
    $result = Invoke-NativeCommand -FilePath $condorStatus -Arguments @("-pool", $pool, "-any", "-limit", "1")
    return $result.ExitCode -eq 0
}

function Read-ManagerIpFile {
    if (-not (Test-Path -LiteralPath $script:ManagerIpFile -PathType Leaf)) {
        return $null
    }

    $lines = @(Get-Content -LiteralPath $script:ManagerIpFile -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") })
    if ($lines.Count -eq 0) {
        return $null
    }

    $candidate = $lines[0]
    if ($candidate -match "=") {
        $candidate = ($candidate -split "=", 2)[1].Trim()
    }
    if (Test-UsableIPv4 $candidate) {
        return $candidate
    }
    Write-Warning "Ignoring invalid manager IP in $($script:ManagerIpFile): $candidate"
    return $null
}

function Write-ManagerIpFile {
    param([string]$IpAddress)
    $content = @(
        "# Generated by setup_machine_1_manager.cmd",
        "# Worker scripts read this file automatically; do not pass IP arguments.",
        $IpAddress
    ) -join [Environment]::NewLine

    if ($DryRun) {
        Write-Host "Would write manager IP file: $script:ManagerIpFile"
        Write-Host $content
        return
    }

    [IO.File]::WriteAllText($script:ManagerIpFile, $content + [Environment]::NewLine, [Text.Encoding]::ASCII)
    Write-Host "Manager IP written to: $script:ManagerIpFile"
}

function Resolve-ManagerIp {
    param(
        [string]$OwnIp,
        [int]$PrefixLength
    )

    $fileManagerIp = Read-ManagerIpFile
    if ($fileManagerIp) {
        Write-Host "Using manager IP from $($script:ManagerIpFile): $fileManagerIp"
        if (-not (Test-TcpPort -IpAddress $fileManagerIp -Port $Port -TimeoutMs 1200)) {
            Write-Warning "Manager IP file points to $fileManagerIp, but TCP port $Port did not answer. Falling back to subnet scan."
        }
        else {
            if (-not (Test-CondorCollector -IpAddress $fileManagerIp)) {
                Write-Warning "TCP port $Port is open at $fileManagerIp, but condor_status could not verify it as a collector yet."
            }
            return $fileManagerIp
        }
    }

    $candidates = @(Get-ScanCandidates -OwnIp $OwnIp -PrefixLength $PrefixLength)
    Write-Host "Scanning $($candidates.Count) local addresses for HTCondor collector port $Port..."
    $open = @(Find-OpenPortCandidates -Candidates $candidates -Port $Port)
    if ($open.Count -eq 0) {
        throw "No HTCondor collector was found on this subnet. Run setup_machine_1_manager.cmd first, then run this worker script again."
    }

    $collectors = @($open | Where-Object { Test-CondorCollector -IpAddress $_ })
    if ($collectors.Count -eq 1) {
        return $collectors[0]
    }
    if ($collectors.Count -gt 1) {
        throw "Found multiple HTCondor collectors: $($collectors -join ', '). Re-run this script with the manager IP as the first argument."
    }

    if ($open.Count -eq 1) {
        Write-Warning "Found one host with TCP $Port open, but could not verify condor_status. Using $($open[0])."
        return $open[0]
    }

    throw "Found hosts with TCP $Port open but none verified as the collector: $($open -join ', '). Re-run with the manager IP as the first argument."
}

function Invoke-CondorConfigVal {
    param([string]$Name)
    try {
        $condorConfigVal = $script:CondorCommands["condor_config_val"]
        $value = (& $condorConfigVal $Name 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $value) {
            return [string]$value
        }
    }
    catch {
        return $null
    }
    return $null
}

function Get-CondorRootConfigCandidates {
    $candidates = New-Object System.Collections.Generic.List[string]

    $condorConfig = [Environment]::GetEnvironmentVariable("CONDOR_CONFIG", "Machine")
    if ($condorConfig) {
        $candidates.Add($condorConfig)
    }
    if ($env:CONDOR_CONFIG) {
        $candidates.Add($env:CONDOR_CONFIG)
    }
    if ($script:CondorRootDir) {
        $candidates.Add((Join-Path $script:CondorRootDir "condor_config"))
        $candidates.Add((Join-Path $script:CondorRootDir "etc\condor_config"))
    }

    return @($candidates | Where-Object { $_ } | Select-Object -Unique)
}

function Get-ExistingCondorRootConfig {
    foreach ($candidate in Get-CondorRootConfigCandidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

function Ensure-CondorRootLoadsLocalConfig {
    param([string]$LocalConfigPath)

    $rootConfig = Get-ExistingCondorRootConfig
    if (-not $rootConfig) {
        if (-not $script:CondorRootDir) {
            throw "Could not locate HTCondor root config and could not infer the install root."
        }
        $rootConfig = Join-Path $script:CondorRootDir "condor_config"
        Write-Warning "No HTCondor root config was found. Creating $rootConfig in the inferred install root."
    }

    if (-not $DryRun) {
        $env:CONDOR_CONFIG = $rootConfig
        Write-Host "Using CONDOR_CONFIG for this process: $rootConfig"
    }

    $localConfigForCondor = $LocalConfigPath -replace "\\", "/"
    $begin = "# BEGIN YADOF HTCONDOR LOCAL CONFIG INCLUDE"
    $end = "# END YADOF HTCONDOR LOCAL CONFIG INCLUDE"
    $includeBlock = $begin + [Environment]::NewLine +
        "LOCAL_CONFIG_FILE = $localConfigForCondor" + [Environment]::NewLine +
        $end + [Environment]::NewLine

    $existing = ""
    if (Test-Path -LiteralPath $rootConfig) {
        $existing = [IO.File]::ReadAllText($rootConfig)
    }

    if ($existing -match [regex]::Escape($LocalConfigPath) -or $existing -match [regex]::Escape($localConfigForCondor)) {
        Write-Host "HTCondor root config already references $LocalConfigPath"
        return
    }

    $pattern = "(?ms)^# BEGIN YADOF HTCONDOR LOCAL CONFIG INCLUDE\r?\n.*?^# END YADOF HTCONDOR LOCAL CONFIG INCLUDE\r?\n?"
    if ($existing -match "# BEGIN YADOF HTCONDOR LOCAL CONFIG INCLUDE") {
        $updated = [regex]::Replace($existing, $pattern, $includeBlock)
    }
    elseif ($existing.Trim().Length -gt 0) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $includeBlock
    }
    else {
        $updated = $includeBlock
    }

    Write-Host "Ensuring HTCondor root config loads local config: $rootConfig"
    if ($DryRun) {
        Write-Host $includeBlock
        return
    }

    $parent = Split-Path -Parent $rootConfig
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path -LiteralPath $rootConfig) {
        $backup = "$rootConfig.bak.$(Get-Date -Format yyyyMMdd-HHmmss)"
        Copy-Item -LiteralPath $rootConfig -Destination $backup -Force
        Write-Host "Root config backup written to $backup"
    }
    [IO.File]::WriteAllText($rootConfig, $updated, [Text.Encoding]::ASCII)
}

function Get-CondorService {
    $services = @(Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*condor*" -or $_.DisplayName -like "*condor*" } |
        Sort-Object Name)
    if ($services.Count -gt 0) {
        return $services[0]
    }

    $cimServices = @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*condor*" -or $_.DisplayName -like "*condor*" -or $_.PathName -like "*condor_master.exe*" } |
        Sort-Object Name)
    if ($cimServices.Count -gt 0) {
        return $cimServices[0]
    }

    return $null
}

function Get-LocalCondorProcesses {
    $binPrefix = ($script:CondorBinDir.TrimEnd("\") + "\").ToLowerInvariant()
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -like "condor_*.exe" -and
            $_.ExecutablePath -and
            ([string]$_.ExecutablePath).ToLowerInvariant().StartsWith($binPrefix)
        })
}

function Start-CondorMasterProcess {
    param([switch]$ForceRestartExisting)

    $master = Join-Path $script:CondorBinDir "condor_master.exe"
    if (-not (Test-Path -LiteralPath $master)) {
        throw "Could not find condor_master.exe at $master"
    }

    $running = @(Get-LocalCondorProcesses)
    if ($running.Count -gt 0) {
        if (-not $ForceRestartExisting) {
            Write-Host "Local HTCondor processes are already running."
            return
        }
        Write-Warning "Stopping existing local HTCondor processes before starting with the new config."
        foreach ($process in $running | Sort-Object ProcessId -Descending) {
            Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
    }

    Write-Warning "No HTCondor Windows service was found. Starting condor_master.exe directly from $master"
    Start-Process -FilePath $master -WorkingDirectory $script:CondorRootDir -WindowStyle Hidden
}

function Get-CondorConfigTarget {
    $preferredLocalConfigs = New-Object System.Collections.Generic.List[string]
    if ($script:CondorRootDir) {
        $preferredLocalConfigs.Add((Join-Path $script:CondorRootDir "condor_config.local"))
    }

    foreach ($candidate in @($preferredLocalConfigs | Select-Object -Unique)) {
        $parent = Split-Path -Parent $candidate
        if ($parent -and (Test-Path -LiteralPath $parent)) {
            Write-Host "Using HTCondor local config target: $candidate"
            Ensure-CondorRootLoadsLocalConfig -LocalConfigPath $candidate
            return $candidate
        }
    }

    $localDirRaw = Invoke-CondorConfigVal "LOCAL_CONFIG_DIR"
    if ($localDirRaw) {
        $localDirs = @($localDirRaw -split "," | ForEach-Object { $_.Trim().Trim('"') } | Where-Object { $_ })
        foreach ($dir in $localDirs) {
            if (-not (Test-Path -LiteralPath $dir)) {
                if (-not $DryRun) {
                    New-Item -ItemType Directory -Force -Path $dir | Out-Null
                }
            }
            if (Test-Path -LiteralPath $dir) {
                return (Join-Path $dir "99-yadof-pool.config")
            }
        }
    }

    $localFileRaw = Invoke-CondorConfigVal "LOCAL_CONFIG_FILE"
    if ($localFileRaw) {
        $localFiles = @($localFileRaw -split "," | ForEach-Object { $_.Trim().Trim('"') } | Where-Object { $_ })
        foreach ($file in $localFiles) {
            $parent = Split-Path -Parent $file
            if ($parent -and (Test-Path -LiteralPath $parent)) {
                return $file
            }
        }
    }

    $fallbacks = New-Object System.Collections.Generic.List[string]
    if ($script:CondorRootDir) {
        $fallbacks.Add((Join-Path $script:CondorRootDir "condor_config.local"))
    }

    foreach ($candidate in @($fallbacks | Select-Object -Unique)) {
        $parent = Split-Path -Parent $candidate
        if (Test-Path -LiteralPath $parent) {
            Ensure-CondorRootLoadsLocalConfig -LocalConfigPath $candidate
            return $candidate
        }
    }

    throw "Could not locate HTCondor local config. Check condor_config_val LOCAL_CONFIG_FILE."
}

function Set-ManagedConfigBlock {
    param(
        [string]$TargetPath,
        [string]$BlockBody
    )

    $begin = "# BEGIN YADOF HTCONDOR POOL"
    $end = "# END YADOF HTCONDOR POOL"
    $block = $begin + [Environment]::NewLine + $BlockBody.TrimEnd() + [Environment]::NewLine + $end + [Environment]::NewLine

    $existing = ""
    if (Test-Path -LiteralPath $TargetPath) {
        $existing = [IO.File]::ReadAllText($TargetPath)
    }

    $pattern = "(?ms)^# BEGIN YADOF HTCONDOR POOL\r?\n.*?^# END YADOF HTCONDOR POOL\r?\n?"
    if ($existing -match "# BEGIN YADOF HTCONDOR POOL") {
        $updated = [regex]::Replace($existing, $pattern, $block)
    }
    elseif ($existing.Trim().Length -gt 0) {
        $updated = $existing.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block
    }
    else {
        $updated = $block
    }

    Write-Host "Writing HTCondor config block to $TargetPath"
    if ($DryRun) {
        Write-Host $block
        return
    }

    $parent = Split-Path -Parent $TargetPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    if (Test-Path -LiteralPath $TargetPath) {
        $backup = "$TargetPath.bak.$(Get-Date -Format yyyyMMdd-HHmmss)"
        Copy-Item -LiteralPath $TargetPath -Destination $backup -Force
        Write-Host "Backup written to $backup"
    }
    [IO.File]::WriteAllText($TargetPath, $updated, [Text.Encoding]::ASCII)
}

function Ensure-FirewallRule {
    param([string]$RemoteAddress)
    $displayName = "YADOF HTCondor shared port $Port"
    Write-Host "Ensuring Windows Firewall allows inbound TCP $Port from $RemoteAddress"
    if ($DryRun) {
        return
    }

    Get-NetFirewallRule -DisplayName $displayName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule `
        -DisplayName $displayName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $Port `
        -Profile Any `
        -RemoteAddress $RemoteAddress | Out-Null
}

function Restart-Condor {
    Write-Host "Restarting HTCondor..."
    if ($DryRun) {
        return
    }

    $restartWorked = $false
    try {
        $condorRestart = $script:CondorCommands["condor_restart"]
        $null = & $condorRestart -master 2>$null
        if ($LASTEXITCODE -eq 0) {
            $restartWorked = $true
        }
    }
    catch {
        $restartWorked = $false
    }

    if (-not $restartWorked) {
        $service = Get-CondorService
        if ($null -ne $service) {
            Write-Host "Using HTCondor Windows service: $($service.Name)"
            $serviceName = [string]$service.Name
            $serviceState = [string]$service.Status
            if (-not $serviceState -and $service.PSObject.Properties.Name -contains "State") {
                $serviceState = [string]$service.State
            }
            if ($serviceState -match "Running") {
                Restart-Service -Name $serviceName -Force
            }
            else {
                Start-Service -Name $serviceName
            }
        }
        else {
            Start-CondorMasterProcess -ForceRestartExisting
        }
    }

    Start-Sleep -Seconds 6
}

function Wait-ForPoolStatus {
    param([string]$CollectorIp)
    $pool = "${CollectorIp}:$Port"
    Write-Host "Checking pool status at $pool..."
    if ($DryRun) {
        return
    }

    for ($attempt = 1; $attempt -le 12; $attempt++) {
        $condorStatus = $script:CondorCommands["condor_status"]
        $result = Invoke-NativeCommand -FilePath $condorStatus -Arguments @("-pool", $pool, "-af", "Name", "Machine", "Cpus", "Memory", "OpSys")
        if ($result.ExitCode -eq 0) {
            Write-Host "Pool is reachable:"
            ($result.StdOut -split "\r?\n" | Where-Object { $_ }) | ForEach-Object { Write-Host "  $_" }
            return
        }
        Start-Sleep -Seconds 5
    }
    Write-Warning "condor_status did not return successfully yet. Wait a minute and run: condor_status -pool $pool"
}

function Show-PostSetupConfig {
    $condorConfigVal = $script:CondorCommands["condor_config_val"]
    Write-Host ""
    Write-Host "Post-setup HTCondor config:"
    foreach ($name in @("CONDOR_HOST", "COLLECTOR_HOST", "DAEMON_LIST", "NETWORK_INTERFACE", "ALLOW_ADVERTISE_STARTD", "STARTER_NUM_THREADS_ENV_VARS", "LOCAL_CONFIG_FILE")) {
        $result = Invoke-NativeCommand -FilePath $condorConfigVal -Arguments @($name)
        $value = ($result.StdOut -split "\r?\n" | Select-Object -First 1)
        if (-not $value) {
            $value = "<empty>"
        }
        Write-Host "  $name = $value"
    }
}

function New-CondorConfigBody {
    param(
        [string]$Role,
        [string]$OwnIp,
        [string]$ManagerIp,
        [string]$AllowPattern
    )

    $daemonList = if ($Role -eq "Manager") {
        "MASTER, SHARED_PORT, COLLECTOR, NEGOTIATOR, SCHEDD, STARTD"
    }
    else {
        "MASTER, SHARED_PORT, STARTD"
    }

    return @"
# Generated by admin_tool/htcondor_pool/configure_htcondor_pool.ps1
# Re-run the matching setup_machine_*.cmd if this machine receives a new IP.
YADOF_MACHINE_LABEL = $MachineLabel
CONDOR_HOST = $ManagerIp
COLLECTOR_HOST = `$`(CONDOR_HOST`):$Port
NETWORK_INTERFACE = $OwnIp

USE_SHARED_PORT = TRUE
SHARED_PORT_PORT = $Port
DAEMON_LIST = $daemonList

ALLOW_READ = *
ALLOW_WRITE = *
ALLOW_ADMINISTRATOR = $AllowPattern
ALLOW_DAEMON = *
ALLOW_NEGOTIATOR = *
ALLOW_ADVERTISE_MASTER = *
ALLOW_ADVERTISE_STARTD = *
ALLOW_ADVERTISE_SCHEDD = *

SEC_DEFAULT_AUTHENTICATION = OPTIONAL
SEC_DEFAULT_ENCRYPTION = OPTIONAL
SEC_DEFAULT_INTEGRITY = OPTIONAL

START = TRUE
SUSPEND = FALSE
PREEMPT = FALSE
KILL = FALSE
WANT_SUSPEND = FALSE
WANT_VACATE = FALSE

# HFSS 2024.1 Iterative Solver crashes when HTCondor injects OMP_THREAD_LIMIT.
STARTER_NUM_THREADS_ENV_VARS = CUBACORES GOMAXPROCS JULIA_NUM_THREADS MKL_NUM_THREADS NUMEXPR_NUM_THREADS OMP_NUM_THREADS OPENBLAS_NUM_THREADS PYTHON_CPU_COUNT ROOT_MAX_THREADS TF_LOOP_PARALLEL_ITERATIONS TF_NUM_THREADS

NUM_SLOTS = 1
NUM_SLOTS_TYPE_1 = 1
SLOT_TYPE_1 = cpus=$JobCpus, ram=$JobMemoryMb, disk=90%
SLOT_TYPE_1_PARTITIONABLE = FALSE
"@
}

Assert-Administrator
Initialize-CondorCommands
Write-Host "YADOF HTCondor pool setup script version: 20260713-hfss-omp-compat"

$primary = Get-PrimaryIPv4
$ownIp = [string]$primary.IPAddress
$prefixLength = [int]$primary.PrefixLength
$networkCidr = Get-NetworkCidr -IpAddress $ownIp -PrefixLength $prefixLength
$allowPattern = Get-AllowPattern -IpAddress $ownIp -PrefixLength $prefixLength

Write-Host "Machine label: $MachineLabel"
Write-Host "Role: $Role"
Write-Host "Selected local IPv4: $ownIp/$prefixLength"
Write-Host "Detected local network: $networkCidr"

if ($Role -eq "Manager") {
    $resolvedManagerIp = $ownIp
    Write-ManagerIpFile -IpAddress $resolvedManagerIp
}
else {
    $resolvedManagerIp = Resolve-ManagerIp -OwnIp $ownIp -PrefixLength $prefixLength
}

Write-Host "HTCondor manager IP: $resolvedManagerIp"

$targetPath = Get-CondorConfigTarget
$body = New-CondorConfigBody -Role $Role -OwnIp $ownIp -ManagerIp $resolvedManagerIp -AllowPattern $allowPattern
Set-ManagedConfigBlock -TargetPath $targetPath -BlockBody $body
Ensure-FirewallRule -RemoteAddress $networkCidr
Restart-Condor
Show-PostSetupConfig
Wait-ForPoolStatus -CollectorIp $resolvedManagerIp

Write-Host ""
Write-Host "Done."
Write-Host "Local IP: $ownIp"
Write-Host "Manager IP: $resolvedManagerIp"
Write-Host "Verify from machine 1 with: condor_status -pool ${resolvedManagerIp}:$Port"
