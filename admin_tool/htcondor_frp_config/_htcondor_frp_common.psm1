#requires -Version 5.1
Set-StrictMode -Version 2.0
$script:IncludeBegin = '# BEGIN YADOF FRP CONFIG INCLUDE'
$script:IncludeEnd = '# END YADOF FRP CONFIG INCLUDE'

function Test-FrpAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function ConvertTo-FrpNativeArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows CommandLineToArgvW quoting, including trailing backslashes.
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function Invoke-FrpCommand {
    param([string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds = 15,
          [string]$RootConfig = '')
    $process = New-Object Diagnostics.Process
    $process.StartInfo.FileName = $FilePath
    $process.StartInfo.Arguments = ($Arguments | ForEach-Object { ConvertTo-FrpNativeArgument $_ }) -join ' '
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    if ($RootConfig) { $process.StartInfo.EnvironmentVariables['CONDOR_CONFIG'] = $RootConfig }
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            throw "Command timed out after ${TimeoutSeconds}s: $FilePath"
        }
        return [pscustomobject]@{ Code = $process.ExitCode; Out = $stdout.Result.Trim(); Error = $stderr.Result.Trim() }
    }
    finally { $process.Dispose() }
}

function Get-FrpValue {
    param($Context, [string]$Name, [string]$RootConfig = '')
    if (-not $RootConfig) { $RootConfig = $Context.RootConfig }
    $result = Invoke-FrpCommand $Context.ConfigVal @($Name) -RootConfig $RootConfig
    if ($result.Code -eq 0) { return $result.Out }
    return ''
}

function Get-FrpContext {
    param([string]$RootConfig = '')
    $command = Get-Command condor_config_val.exe -ErrorAction SilentlyContinue
    $service = Get-CimInstance Win32_Service -Filter "Name='condor'" -ErrorAction Stop
    $bin = ''
    if ($service -and $service.PathName -match '^\s*"?(.+?condor_master\.exe)"?(?:\s|$)') {
        $bin = Split-Path -Parent $matches[1]
    }
    if (-not $bin -and $command) { $bin = Split-Path -Parent $command.Source }
    if (-not $bin -or -not (Test-Path -LiteralPath (Join-Path $bin 'condor_config_val.exe'))) {
        throw 'Install HTCondor for Windows first (with the condor Windows service).'
    }
    if (-not $RootConfig) {
        $candidates = @($env:CONDOR_CONFIG, [Environment]::GetEnvironmentVariable('CONDOR_CONFIG', 'Machine'))
        foreach ($key in @('HKLM:\SOFTWARE\Condor', 'HKLM:\SOFTWARE\WOW6432Node\Condor')) {
            $reg = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
            if ($reg -and $reg.PSObject.Properties['CONDOR_CONFIG']) { $candidates += $reg.CONDOR_CONFIG }
        }
        $candidates += Join-Path (Split-Path -Parent $bin) 'condor_config'
        $RootConfig = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
    }
    if (-not $RootConfig -or -not (Test-Path -LiteralPath $RootConfig -PathType Leaf)) {
        throw 'Cannot find the HTCondor root config. Pass -RootConfig with its absolute path.'
    }
    $RootConfig = (Resolve-Path -LiteralPath $RootConfig).Path
    $context = [pscustomobject]@{
        RootConfig = $RootConfig
        ManagedConfig = Join-Path (Split-Path -Parent $RootConfig) 'condor_config.yadof_frp'
        ConfigVal = Join-Path $bin 'condor_config_val.exe'
        Status = Join-Path $bin 'condor_status.exe'
        Service = $service
    }
    # Environment/user overrides would make CLI validation differ from LocalSystem.
    $overrides = @(Get-ChildItem Env: | Where-Object Name -like '_CONDOR_*')
    if ($overrides.Count) { throw 'Remove process _CONDOR_* overrides before using these setup scripts.' }
    $version = Invoke-FrpCommand (Join-Path $bin 'condor_version.exe') @()
    if ($version.Out -notmatch 'CondorVersion:\s+(\d+)\.(\d+)\.(\d+)') { throw 'Cannot detect the HTCondor version.' }
    $detected = [version]('{0}.{1}.{2}' -f $matches[1], $matches[2], $matches[3])
    if ($detected -lt [version]'25.14.1') { throw "This FRP/outbound-CCB setup requires HTCondor 25.14.1 or newer; found $detected." }
    return $context
}

function Read-FrpText {
    param([string]$Prompt, [string]$Value, [string]$Default, [switch]$NonInteractive)
    if ($Value) { return $Value.Trim() }
    if ($NonInteractive) {
        if ($Default) { return $Default }
        throw "Missing required value: $Prompt"
    }
    while ($true) {
        $label = if ($Default) { "$Prompt [$Default]" } else { $Prompt }
        $answer = (Read-Host $label).Trim()
        if ($answer) { return $answer }
        if ($Default) { return $Default }
    }
}

function Assert-FrpName {
    param([string]$Value, [string]$Label = 'Name')
    if ($Value -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]*$') { throw "$Label must be a machine/domain name: $Value" }
    return $Value
}

function Assert-FrpResourcePath {
    param([string]$Path)
    if ($Path -notmatch '^[A-Za-z]:[\\/]' -or $Path -match '[\x00-\x1f$#"]') {
        throw 'Execute directory must be an absolute local-drive path without config metacharacters.'
    }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($full.Length -le 3) { throw 'A drive root cannot be used as the execute directory.' }
    $ancestor = $full
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if (-not $item.PSIsContainer) { throw "Execute path contains a file: $ancestor" }
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Execute path cannot traverse a junction or symbolic link: $ancestor"
            }
        }
        $ancestor = Split-Path -Parent $ancestor
    }
    return $full
}

function Get-FrpResources {
    param($Context, [string]$ExecuteDirectory, [long]$Cpus, [long]$MemoryMiB, [long]$DiskMiB,
          [switch]$NonInteractive)
    $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $cpuLimit = [int]$computer.NumberOfLogicalProcessors
    $memoryLimit = [long][math]::Floor($computer.TotalPhysicalMemory / 1MB)
    $pathDefault = Get-FrpValue $Context 'EXECUTE'
    if (-not $pathDefault) { $pathDefault = Join-Path (Split-Path -Parent $Context.RootConfig) 'execute' }
    $path = Assert-FrpResourcePath (Read-FrpText 'Execute directory' $ExecuteDirectory $pathDefault -NonInteractive:$NonInteractive)
    foreach ($protected in @((Split-Path -Parent $Context.RootConfig), $env:SystemRoot, $env:ProgramFiles,
        (Get-FrpValue $Context 'SEC_TOKEN_SYSTEM_DIRECTORY'), (Get-FrpValue $Context 'SEC_PASSWORD_DIRECTORY'),
        (Get-FrpValue $Context 'SPOOL'), (Get-FrpValue $Context 'LOG'))) {
        if (-not $protected) { continue }
        $protected = [IO.Path]::GetFullPath($protected).TrimEnd('\')
        if ($path -ieq $protected -or $protected.StartsWith($path + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Execute directory overlaps a protected directory: $protected"
        }
        if ($protected -ine (Split-Path -Parent $Context.RootConfig) -and
            $path.StartsWith($protected + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Execute directory is inside a protected directory: $protected"
        }
    }
    $drive = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $path.Substring(0, 2)) -ErrorAction Stop
    if (-not $drive -or $drive.DriveType -ne 3) { throw 'Use a mounted local fixed drive, not a mapped/network drive.' }
    $diskLimit = [long][math]::Floor($drive.FreeSpace / 1MB)
    $values = @{}
    foreach ($spec in @(
        @{ Key='Cpus'; Value=$Cpus; Macro='NUM_CPUS'; Limit=$cpuLimit },
        @{ Key='MemoryMiB'; Value=$MemoryMiB; Macro='MEMORY'; Limit=$memoryLimit },
        @{ Key='DiskMiB'; Value=$DiskMiB; Macro='YADOF_DECLARED_DISK_MB'; Limit=$diskLimit }
    )) {
        $old = Get-FrpValue $Context $spec.Macro
        if ($old -notmatch '^\d+$' -or [decimal]$old -gt $spec.Limit -or [decimal]$old -lt 1) { $old = [string]$spec.Limit }
        $given = if ($spec.Value -gt 0) { [string]$spec.Value } else { '' }
        # In automation every resource must be explicit; do not silently allocate all hardware.
        if ($NonInteractive -and -not $given) { throw "Specify -$($spec.Key) explicitly in noninteractive mode." }
        $text = Read-FrpText "$($spec.Key) (detected maximum $($spec.Limit))" $given $old -NonInteractive:$NonInteractive
        $parsed = 0L
        if (-not [long]::TryParse($text, [ref]$parsed) -or $parsed -lt 1 -or $parsed -gt $spec.Limit) {
            throw "$($spec.Key) must be an integer between 1 and $($spec.Limit)."
        }
        $values[$spec.Key] = $parsed
    }
    $values.Path = $path
    return $values
}

function New-FrpSettings {
    param([ValidateSet('Detached','Manager','Worker')][string]$Role, [string]$ManagerName,
        [string]$TrustDomain, [int]$VisitorPort = 29618, [int]$SharedPort = 9618,
        [string]$PrivateNetworkName, [string]$BrokerTargetAllowlist = '',
        [bool]$EnableSubmit = $false, [hashtable]$Resources = $null,
        [string]$AuthenticationMethods = 'IDTOKENS, NTSSPI, PASSWORD, KERBEROS, SSL',
        [string]$StartdAttrs = '')
    $worker = $Role -eq 'Worker'
    $manager = $Role -eq 'Manager'
    $execute = $null -ne $Resources -and $Role -ne 'Detached'
    $daemons = @('MASTER')
    if ($manager) { $daemons += @('COLLECTOR', 'NEGOTIATOR', 'SCHEDD') }
    elseif ($worker -and $EnableSubmit) { $daemons += 'SCHEDD' }
    if ($execute) { $daemons += 'STARTD' }
    $endpoint = if ($worker) { "127.0.0.1:$VisitorPort" } elseif ($manager) { "${ManagerName}:$SharedPort" } else { "127.0.0.1:$SharedPort" }
    $settings = [ordered]@{
        YADOF_FRP_MANAGED='True'; YADOF_POOL_ROLE=$Role; YADOF_MANAGER_NAME=$ManagerName
        YADOF_FRP_VISITOR_PORT=[string]$VisitorPort; YADOF_FRP_ENABLE_SUBMIT=[string]$EnableSubmit
        CONDOR_HOST=$(if ($manager) { $ManagerName } else { '127.0.0.1' })
        COLLECTOR_HOST=$endpoint; TRUST_DOMAIN=$TrustDomain
        NETWORK_INTERFACE='*'; BIND_ALL_INTERFACES='True'; NO_DNS='False'
        USE_SHARED_PORT='True'; SHARED_PORT_PORT=[string]$SharedPort; COLLECTOR_USES_SHARED_PORT='True'
        UPDATE_COLLECTOR_WITH_TCP='True'; DAEMON_LIST=($daemons -join ', ')
        CCB_ADDRESS=$(if ($worker) { $endpoint } else { '' })
        OUTBOUND_CCB_ADDRESS=$(if ($worker) { $endpoint } else { '' })
        USE_OUTBOUND_CCB='False'; CCB_OUTBOUND_NEXT_HOP=''
        CCB_OUTBOUND_PROXY=[string]$manager
        CCB_OUTBOUND_TARGET_ALLOWLIST=$(if ($manager) { $BrokerTargetAllowlist } else { '' })
        CCB_SERVER_STREAMING='True'; CCB_CLIENT_STREAMING='True'
        PRIVATE_NETWORK_NAME=$PrivateNetworkName; PRIVATE_NETWORK_INTERFACE=''; TCP_FORWARDING_HOST=''
        FLOCK_TO=''; FLOCK_COLLECTOR_HOSTS=''; FLOCK_NEGOTIATOR_HOSTS=''
        SEC_DEFAULT_AUTHENTICATION='Required'; SEC_DEFAULT_ENCRYPTION='Required'; SEC_DEFAULT_INTEGRITY='Required'
        SEC_DEFAULT_AUTHENTICATION_METHODS=$AuthenticationMethods
        STARTER_ALLOW_RUNAS_OWNER='False'
        YADOF_RESOURCES_CONFIGURED=[string]$execute; YADOF_EXECUTE_READY=[string]$execute
        START=[string]$execute
    }
    if ($execute) {
        $settings.EXECUTE = $Resources.Path.Replace('\', '/')
        $settings.YADOF_EXECUTE_DIR = $settings.EXECUTE
        $settings.NUM_CPUS = [string]$Resources.Cpus
        $settings.MEMORY = [string]$Resources.MemoryMiB
        $settings.DISK = [string]($Resources.DiskMiB * 1024L)
        $settings.YADOF_DECLARED_CPUS = $settings.NUM_CPUS
        $settings.YADOF_DECLARED_MEMORY_MB = $settings.MEMORY
        $settings.YADOF_DECLARED_DISK_MB = [string]$Resources.DiskMiB
        $settings.NUM_SLOTS = '1'
        $settings.NUM_SLOTS_TYPE_1 = '1'
        $settings.SLOT_TYPE_1 = '100%'
        $settings.SLOT_TYPE_1_PARTITIONABLE = 'True'
        $settings.SUSPEND = 'False'; $settings.PREEMPT = 'False'; $settings.KILL = 'False'
        $settings.WANT_SUSPEND = 'False'; $settings.WANT_VACATE = 'False'
    }
    else { $settings.YADOF_EXECUTE_DIR = '' }
    $attrs = @($StartdAttrs -split '[,\s]+' | Where-Object { $_ }) + @('YADOF_EXECUTE_READY', 'YADOF_EXECUTE_DIR')
    $settings.STARTD_ATTRS = ($attrs | Select-Object -Unique) -join ', '
    return $settings
}

function ConvertTo-FrpConfigText {
    param([System.Collections.IDictionary]$Settings)
    $lines = @('# Managed by admin_tool/htcondor_frp_config. Credentials and ALLOW/DENY rules remain in existing config.')
    foreach ($key in $Settings.Keys) {
        $value = [string]$Settings[$key]
        if ($value -match '[\r\n]' -or $value.Contains('$(')) { throw "Unsafe config value for $key" }
        $lines += "$key = $value"
    }
    return ($lines -join "`r`n") + "`r`n"
}

function Add-FrpInclude {
    param([string]$RootText, [string]$ManagedPath)
    if ($ManagedPath -match '[\r\n$#"]') { throw 'Unsupported metacharacter in configuration path.' }
    $pattern = '(?ms)^' + [regex]::Escape($script:IncludeBegin) + '\r?\n.*?^' + [regex]::Escape($script:IncludeEnd) + '(?:\r?\n|$)'
    if ($RootText.Contains($script:IncludeBegin) -and -not [regex]::IsMatch($RootText, $pattern)) {
        throw 'The existing FRP include block is incomplete; repair it before proceeding.'
    }
    $clean = [regex]::Replace($RootText, $pattern, '').TrimEnd()
    # LOCAL_CONFIG_FILE is a comma/whitespace list, not a shell; quotes are literal.
    # Use an existing parent's Windows short name when the install/temp path has spaces.
    if ($ManagedPath -match '[\s,]') {
        $filesystem = New-Object -ComObject Scripting.FileSystemObject
        try {
            if (Test-Path -LiteralPath $ManagedPath -PathType Leaf) { $ManagedPath = $filesystem.GetFile($ManagedPath).ShortPath }
            else { $ManagedPath = Join-Path $filesystem.GetFolder((Split-Path -Parent $ManagedPath)).ShortPath (Split-Path -Leaf $ManagedPath) }
        }
        finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($filesystem) }
        if ($ManagedPath -match '[\s,]') {
            throw 'HTCondor include paths cannot contain spaces/commas here and Windows short names are unavailable. Use a path without spaces (-OutputDirectory for previews).'
        }
    }
    # HTCondor expands a self reference using the preceding definition.
    $include = 'LOCAL_CONFIG_FILE = $(LOCAL_CONFIG_FILE), ' + $ManagedPath.Replace('\', '/')
    return "$clean`r`n`r`n$script:IncludeBegin`r`n$include`r`n$script:IncludeEnd`r`n"
}

function Write-FrpUtf8 {
    param([string]$Path, [string]$Text)
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}

function Assert-FrpEffectiveSettings {
    param($Context, [string]$RootConfig, [System.Collections.IDictionary]$Settings)
    # -dump reads all generated keys in one process; no daemon is contacted.
    $pattern = '^(' + (($Settings.Keys | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')$'
    $result = Invoke-FrpCommand $Context.ConfigVal @('-expanded', '-dump', $pattern) -RootConfig $RootConfig
    if ($result.Code -ne 0) { throw "HTCondor rejected the staged configuration: $($result.Error)" }
    $actual = @{}
    foreach ($line in $result.Out -split '\r?\n') {
        if ($line -match '^([A-Za-z0-9_]+)\s*=\s*(.*)$') { $actual[$matches[1]] = $matches[2].Trim() }
    }
    foreach ($key in $Settings.Keys) {
        $expected = [string]$Settings[$key]
        $value = if ($actual.ContainsKey($key)) { [string]$actual[$key] } else { '' }
        if ($value.Trim() -ine $expected.Trim()) {
            throw "Effective $key differs from the plan: expected '$expected', got '$value'. Check later/user config overrides."
        }
    }
}

function New-FrpPlan {
    param($Context, [System.Collections.IDictionary]$Settings, [string]$OutputDirectory)
    $stageDir = Join-Path ([IO.Path]::GetFullPath($OutputDirectory)) ('plan-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
    $rootHash = (Get-FileHash -LiteralPath $Context.RootConfig -Algorithm SHA256).Hash
    $managedHash = if (Test-Path -LiteralPath $Context.ManagedConfig) {
        (Get-FileHash -LiteralPath $Context.ManagedConfig -Algorithm SHA256).Hash
    } else { '' }
    $rootText = [IO.File]::ReadAllText($Context.RootConfig)
    $body = ConvertTo-FrpConfigText $Settings
    $stagedBody = Join-Path $stageDir 'condor_config.yadof_frp'
    $stagedRoot = Join-Path $stageDir 'condor_config.preview'
    Write-FrpUtf8 $stagedBody $body
    Write-FrpUtf8 $stagedRoot (Add-FrpInclude $rootText $stagedBody)
    Assert-FrpEffectiveSettings $Context $stagedRoot $Settings
    $finalRoot = Add-FrpInclude $rootText $Context.ManagedConfig
    Write-FrpUtf8 (Join-Path $stageDir 'condor_config.proposed') $finalRoot
    return [pscustomobject]@{
        Directory=$stageDir; Body=$body; RootText=$finalRoot; PreviewRoot=$stagedRoot
        OriginalRootHash=$rootHash
        OriginalManagedHash=$managedHash
    }
}

function Test-FrpVisitor {
    param([int]$Port)
    $client = New-Object Net.Sockets.TcpClient
    try {
        $connect = $client.ConnectAsync('127.0.0.1', $Port)
        if (-not $connect.Wait(3000) -or -not $client.Connected) { throw 'Not connected' }
    }
    catch { throw "FRP visitor 127.0.0.1:$Port is unavailable. Start/fix the existing FRP tunnel first." }
    finally { $client.Dispose() }
}

function Assert-FrpLiveDaemon {
    param($Context, [System.Collections.IDictionary]$Settings, [string]$AddressMacro, [switch]$Execute)
    $addressFile = Get-FrpValue $Context $AddressMacro
    if (-not $addressFile -or -not (Test-Path -LiteralPath $addressFile -PathType Leaf)) { throw "$AddressMacro is not available yet." }
    $addressText = [IO.File]::ReadAllText($addressFile)
    if ($addressText -notmatch '[?&]sock=([^&>\s]+)') { throw "No shared-port socket ID in $addressFile" }
    $address = '<127.0.0.1:' + $Settings.SHARED_PORT_PORT + '?sock=' + $matches[1] + '>'
    $keys = @('YADOF_FRP_MANAGED', 'YADOF_POOL_ROLE', 'COLLECTOR_HOST', 'START')
    if ($Settings.YADOF_POOL_ROLE -eq 'Worker') { $keys += @('CCB_ADDRESS', 'OUTBOUND_CCB_ADDRESS') }
    if ($Execute) { $keys += @('EXECUTE', 'NUM_CPUS', 'MEMORY', 'DISK') }
    $result = Invoke-FrpCommand $Context.ConfigVal (@('-address', $address) + $keys) -TimeoutSeconds 5 -RootConfig $Context.RootConfig
    if ($result.Code -ne 0) { throw "Cannot verify running daemon configuration: $($result.Error)" }
    $values = @($result.Out -split '\r?\n')
    if ($values.Count -ne $keys.Count) { throw 'Running daemon returned an incomplete configuration.' }
    for ($index = 0; $index -lt $keys.Count; $index++) {
        if ($values[$index].Trim() -ine [string]$Settings[$keys[$index]]) { throw "Running daemon has a different $($keys[$index]) value." }
    }
}

function Wait-FrpRegistration {
    param($Context, [System.Collections.IDictionary]$Settings, [int]$TimeoutSeconds = 45)
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = ''
    do {
        try {
            Assert-FrpLiveDaemon $Context $Settings 'MASTER_ADDRESS_FILE'
            if ($Settings.YADOF_RESOURCES_CONFIGURED -eq 'True') { Assert-FrpLiveDaemon $Context $Settings 'STARTD_ADDRESS_FILE' -Execute }
            $result = Invoke-FrpCommand $Context.Status @('-pool', $Settings.COLLECTOR_HOST, '-master', '-af', 'Machine', 'DaemonStartTime') -TimeoutSeconds 8 -RootConfig $Context.RootConfig
            $hostname = Get-FrpValue $Context 'FULL_HOSTNAME'
            foreach ($line in $result.Out -split '\r?\n') {
                if ($line -match '^(\S+)\s+(\d+)$' -and $matches[1] -in @($hostname, $env:COMPUTERNAME)) {
                    $bootTime = ([datetimeoffset]::FromUnixTimeSeconds([long]$matches[2])).UtcDateTime
                    if ($bootTime -ge $script:RestartStarted.AddSeconds(-3)) {
                        if ($Settings.YADOF_RESOURCES_CONFIGURED -eq 'True') {
                            $slots = Invoke-FrpCommand $Context.Status @('-pool', $Settings.COLLECTOR_HOST, '-af', 'Machine', 'DaemonStartTime', 'MyAddress') -TimeoutSeconds 8 -RootConfig $Context.RootConfig
                            $found = $false
                            foreach ($slot in $slots.Out -split '\r?\n') {
                                if ($slot -match '^(\S+)\s+(\d+)\s+(.+)$' -and $matches[1] -in @($hostname, $env:COMPUTERNAME)) {
                                    $slotStart = ([datetimeoffset]::FromUnixTimeSeconds([long]$matches[2])).UtcDateTime
                                    if ($slotStart -ge $script:RestartStarted.AddSeconds(-3) -and
                                        ($Settings.YADOF_POOL_ROLE -ne 'Worker' -or $matches[3].Contains('CCBID='))) { $found = $true }
                                }
                            }
                            if (-not $found) { throw 'No fresh execute advertisement (with CCBID for a worker) is visible yet.' }
                        }
                        Write-Host 'Running daemon configuration and fresh collector registration verified.'
                        return
                    }
                }
            }
            $lastError = $result.Error
        }
        catch { $lastError = $_.Exception.Message }
        Start-Sleep -Seconds 2
    } while ([datetime]::UtcNow -lt $deadline)
    throw "No fresh local MASTER registration was seen. Check FRP, tokens, authorization and MasterLog. $lastError"
}

function Install-FrpPlan {
    param($Context, $Plan, [System.Collections.IDictionary]$Settings, [hashtable]$Resources)
    if (-not (Test-FrpAdministrator)) { throw 'Administrator privileges are required to apply the plan.' }
    if (-not $Context.Service) { throw 'The condor Windows service is required. Install it before applying this setup.' }
    if ((Get-FileHash -LiteralPath $Context.RootConfig -Algorithm SHA256).Hash -ne $Plan.OriginalRootHash) {
        throw 'Root config changed after planning. Run the script again.'
    }
    $currentHash = if (Test-Path -LiteralPath $Context.ManagedConfig) { (Get-FileHash -LiteralPath $Context.ManagedConfig -Algorithm SHA256).Hash } else { '' }
    if ($currentHash -ne $Plan.OriginalManagedHash) { throw 'Managed config changed after planning. Run the script again.' }
    if ($Settings.YADOF_POOL_ROLE -eq 'Worker') { Test-FrpVisitor ([int]$Settings.YADOF_FRP_VISITOR_PORT) }
    $backup = Join-Path (Split-Path -Parent $Context.RootConfig) ('yadof_frp_backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item -LiteralPath $Context.RootConfig -Destination (Join-Path $backup 'condor_config.original')
    $hadManaged = Test-Path -LiteralPath $Context.ManagedConfig
    if ($hadManaged) { Copy-Item -LiteralPath $Context.ManagedConfig -Destination (Join-Path $backup 'condor_config.yadof_frp.original') }
    $before = Get-Service -Name condor
    $wasRunning = $before.Status -eq 'Running'
    $startup = [string]$before.StartType
    $acl = $null
    $state = @{ RootConfig=$Context.RootConfig; ManagedConfig=$Context.ManagedConfig; HadManaged=$hadManaged; WasRunning=$wasRunning; StartupType=$startup }
    $state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'state.json') -Encoding UTF8
    Write-Host "Backup: $backup"
    try {
        Stop-Service -Name condor -Force -ErrorAction Stop
        if ($Resources -and $Settings.YADOF_RESOURCES_CONFIGURED -eq 'True') {
            if (Test-Path -LiteralPath $Resources.Path) { $acl = Get-Acl -LiteralPath $Resources.Path; $acl | Export-Clixml -LiteralPath (Join-Path $backup 'execute-acl.xml') }
            New-Item -ItemType Directory -Path $Resources.Path -Force | Out-Null
            $permissions = Invoke-FrpCommand (Join-Path $env:SystemRoot 'System32\icacls.exe') @(
                $Resources.Path, '/inheritance:e', '/grant', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-32-545:(OI)(CI)M')
            if ($permissions.Code -ne 0) { throw "Cannot set execute-directory permissions: $($permissions.Error)" }
        }
        Write-FrpUtf8 $Context.ManagedConfig $Plan.Body
        Write-FrpUtf8 $Context.RootConfig $Plan.RootText
        Assert-FrpEffectiveSettings $Context $Context.RootConfig $Settings
        if ($Settings.YADOF_POOL_ROLE -eq 'Detached') {
            Set-Service -Name condor -StartupType Disabled -ErrorAction Stop
            Write-Host 'Detached: condor is stopped and disabled. FRP and credentials were preserved.'
            return
        }
        Set-Service -Name condor -StartupType Automatic -ErrorAction Stop
        $script:RestartStarted = [datetime]::UtcNow
        Start-Service -Name condor -ErrorAction Stop
        Wait-FrpRegistration $Context $Settings
        if ((Get-Service -Name condor).Status -ne 'Running') { throw 'The condor service stopped after startup.' }
        Write-Host 'Configuration applied. Pool registration does not prove job transfer/execution succeeds.'
    }
    catch {
        $reason = $_.Exception.Message
        try {
            Stop-Service -Name condor -Force -ErrorAction Stop
            Copy-Item -LiteralPath (Join-Path $backup 'condor_config.original') -Destination $Context.RootConfig -Force
            if ($hadManaged) {
                Copy-Item -LiteralPath (Join-Path $backup 'condor_config.yadof_frp.original') -Destination $Context.ManagedConfig -Force
            }
            elseif (Test-Path -LiteralPath $Context.ManagedConfig) { Remove-Item -LiteralPath $Context.ManagedConfig -Force }
            if ($acl) { Set-Acl -LiteralPath $Resources.Path -AclObject $acl }
            Set-Service -Name condor -StartupType $startup -ErrorAction Stop
            if ($wasRunning) { Start-Service -Name condor -ErrorAction Stop }
        }
        catch { throw "Apply failed: $reason. Rollback also failed: $($_.Exception.Message). Backup: $backup" }
        throw "Apply failed and previous config/service state was restored: $reason. Backup: $backup"
    }
}

Export-ModuleMember -Function *-Frp*
