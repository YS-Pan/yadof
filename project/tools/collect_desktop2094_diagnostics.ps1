param(
    [string]$OutputDir = "rawData",
    [int]$EventHours = 24
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Ensure-Directory {
    param([string]$Path)
    if (-not [string]::IsNullOrWhiteSpace($Path) -and -not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-JsonFile {
    param([string]$Path, [object]$Value)
    $Value | ConvertTo-Json -Depth 8 | Out-File -FilePath $Path -Encoding utf8
}

function Write-TextFile {
    param([string]$Path, [string]$Text)
    $Text | Out-File -FilePath $Path -Encoding utf8
}

function Safe-Value {
    param([scriptblock]$Block)
    try {
        & $Block
    } catch {
        [pscustomobject]@{
            error_type = $_.Exception.GetType().FullName
            error_message = $_.Exception.Message
        }
    }
}

function Directory-Sample {
    param([string]$Path)
    $rows = New-Object System.Collections.Generic.List[object]
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return [pscustomobject]@{ path = $Path; exists = $false; sample = @(); error = "empty path" }
    }
    $exists = [System.IO.Directory]::Exists($Path)
    $errorText = ""
    if ($exists) {
        try {
            $count = 0
            foreach ($entry in [System.IO.Directory]::EnumerateFileSystemEntries($Path)) {
                $count += 1
                if ($count -gt 40) { break }
                try {
                    $item = Get-Item -LiteralPath $entry -Force -ErrorAction Stop
                    $rows.Add([pscustomobject]@{
                        name = $item.Name
                        full_name = $item.FullName
                        is_directory = [bool]$item.PSIsContainer
                        length = if ($item.PSIsContainer) { $null } else { $item.Length }
                        last_write_time = $item.LastWriteTime
                    })
                } catch {
                    $rows.Add([pscustomobject]@{ full_name = $entry; error = $_.Exception.Message })
                }
            }
        } catch {
            $errorText = $_.Exception.Message
        }
    }
    [pscustomobject]@{
        path = $Path
        exists = $exists
        sample = $rows
        error = $errorText
    }
}

function Test-WriteAccess {
    param([string]$Path)
    $result = [ordered]@{
        path = $Path
        mkdir_ok = $false
        write_ok = $false
        read_ok = $false
        delete_ok = $false
        error = ""
    }
    try {
        Ensure-Directory $Path
        $result.mkdir_ok = $true
        $probe = Join-Path $Path ("yadof_probe_" + [guid]::NewGuid().ToString("N") + ".txt")
        [System.IO.File]::WriteAllText($probe, "probe " + [DateTime]::Now.ToString("o"))
        $result.write_ok = $true
        $text = [System.IO.File]::ReadAllText($probe)
        $result.read_ok = $text.StartsWith("probe")
        [System.IO.File]::Delete($probe)
        $result.delete_ok = -not [System.IO.File]::Exists($probe)
    } catch {
        $result.error = $_.Exception.Message
    }
    [pscustomobject]$result
}

Ensure-Directory $OutputDir

$identity = [ordered]@{
    collected_at = (Get-Date).ToString("o")
    computername = $env:COMPUTERNAME
    username = $env:USERNAME
    userdomain = $env:USERDOMAIN
    whoami = (Safe-Value { whoami.exe 2>$null })
    cwd = (Get-Location).Path
    powershell = $PSVersionTable.PSVersion.ToString()
    os_version = [Environment]::OSVersion.VersionString
    processor_count = [Environment]::ProcessorCount
    is_64bit_os = [Environment]::Is64BitOperatingSystem
}
Write-JsonFile (Join-Path $OutputDir "identity.json") $identity

$env_keys = @(
    "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR",
    "_CONDOR_SCRATCH_DIR", "ANSYSLMD_LICENSE_FILE", "PATH", "COMSPEC"
)
$env_rows = foreach ($key in $env_keys) {
    [pscustomobject]@{ name = $key; value = [Environment]::GetEnvironmentVariable($key) }
}
Write-JsonFile (Join-Path $OutputDir "environment.json") $env_rows

$drives = Safe-Value {
    Get-PSDrive -PSProvider FileSystem |
        Select-Object Name, Root, Used, Free, Description
}
Write-JsonFile (Join-Path $OutputDir "drives.json") $drives

$paths = @(
    $env:USERPROFILE,
    $env:HOME,
    $env:APPDATA,
    $env:LOCALAPPDATA,
    $env:TEMP,
    $env:TMP,
    $env:_CONDOR_SCRATCH_DIR,
    (Join-Path $env:USERPROFILE "Documents"),
    (Join-Path $env:USERPROFILE "Documents\Ansoft"),
    (Join-Path ([IO.Path]::GetTempPath()) "condor_execute")
) | Where-Object { $_ -and $_.Trim() } | Select-Object -Unique
Write-JsonFile (Join-Path $OutputDir "directory_summaries.json") ($paths | ForEach-Object { Directory-Sample $_ })
Write-JsonFile (Join-Path $OutputDir "write_access.json") ($paths | ForEach-Object { Test-WriteAccess $_ })

$tasklist = Safe-Value {
    $patterns = @("ansysedt.exe", "hf3d.exe", "ansyscl.exe", "python.exe", "condor_starter.exe")
    $out = New-Object System.Collections.Generic.List[object]
    foreach ($pattern in $patterns) {
        $text = tasklist.exe /fo csv /v /fi "imagename eq $pattern" 2>$null
        $out.Add([pscustomobject]@{ image = $pattern; output = ($text -join "`n") })
    }
    $out
}
Write-JsonFile (Join-Path $OutputDir "tasklist.json") $tasklist

$knownFolderText = Safe-Value {
    $a = reg.exe query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" 2>&1
    $b = reg.exe query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" 2>&1
    ($a -join "`n") + "`n--- Shell Folders ---`n" + ($b -join "`n")
}
Write-TextFile (Join-Path $OutputDir "known_folders.txt") ([string]$knownFolderText)

$ansoftRegText = Safe-Value {
    $a = reg.exe query "HKCU\Software\Ansoft" 2>&1
    $b = reg.exe query "HKCU\Software\ANSYS" 2>&1
    ($a -join "`n") + "`n--- HKCU Software ANSYS ---`n" + ($b -join "`n")
}
Write-TextFile (Join-Path $OutputDir "ansoft_registry_top.txt") ([string]$ansoftRegText)

Write-JsonFile (Join-Path $OutputDir "summary.json") ([ordered]@{
    collected_at = (Get-Date).ToString("o")
    computername = $env:COMPUTERNAME
    username = $env:USERNAME
    event_hours_requested_but_skipped = $EventHours
    note = "Lightweight probe: no recursive directory scan, no event log expansion, no AEDT import."
    output_files = (Get-ChildItem -LiteralPath $OutputDir -File | Select-Object -ExpandProperty Name)
})
