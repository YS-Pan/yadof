param(
    [string]$OutputDir = "rawData",
    [switch]$DryRun
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
    $Value | ConvertTo-Json -Depth 6 | Out-File -FilePath $Path -Encoding utf8
}

function Write-TextFile {
    param([string]$Path, [string]$Text)
    $Text | Out-File -FilePath $Path -Encoding utf8
}

function Reg-QueryText {
    param([string]$Key)
    try {
        $text = reg.exe query $Key 2>&1
        return ($text -join "`n")
    } catch {
        return $_.Exception.Message
    }
}

function Set-ExpandStringValue {
    param([string]$KeyPath, [string]$Name, [string]$Value)
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($KeyPath)
    try {
        $key.SetValue($Name, $Value, [Microsoft.Win32.RegistryValueKind]::ExpandString)
    } finally {
        $key.Close()
    }
}

Ensure-Directory $OutputDir

$userProfile = [Environment]::GetEnvironmentVariable("USERPROFILE")
$documents = Join-Path $userProfile "Documents"
$ansoft = Join-Path $documents "Ansoft"
$shellKeyText = "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
$shellKeyPath = "Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
$documentsGuid = "{F42EE2D3-909F-4907-8871-4C22FC0BF756}"
$target = "%USERPROFILE%\Documents"

Write-TextFile (Join-Path $OutputDir "known_folders_before.txt") (Reg-QueryText $shellKeyText)

$actions = New-Object System.Collections.Generic.List[object]
foreach ($path in @($documents, $ansoft)) {
    if (-not $DryRun) { Ensure-Directory $path }
    $actions.Add([pscustomobject]@{ action = "ensure_directory"; path = $path; dry_run = [bool]$DryRun })
}

if (-not $DryRun) {
    Set-ExpandStringValue $shellKeyPath "Personal" $target
    Set-ExpandStringValue $shellKeyPath $documentsGuid $target
}
$actions.Add([pscustomobject]@{
    action = "set_user_shell_folders"
    key = $shellKeyText
    values = @("Personal", $documentsGuid)
    data = $target
    kind = "REG_EXPAND_SZ"
    dry_run = [bool]$DryRun
})

Write-TextFile (Join-Path $OutputDir "known_folders_after.txt") (Reg-QueryText $shellKeyText)
Write-JsonFile (Join-Path $OutputDir "fix_summary.json") ([ordered]@{
    collected_at = (Get-Date).ToString("o")
    computername = $env:COMPUTERNAME
    username = $env:USERNAME
    whoami = (whoami.exe 2>$null)
    cwd = (Get-Location).Path
    userprofile = $userProfile
    documents = $documents
    ansoft = $ansoft
    dry_run = [bool]$DryRun
    actions = $actions
})
