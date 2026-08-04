[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$InstallerPath,

    [Parameter(Mandatory = $true)]
    [string]$AuditOutputPath,

    [switch]$ResumeExistingMiniforge,

    [switch]$ResumeExistingPyChronoEnvironment
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$miniforgeRoot = "C:\ProgramData\Miniforge3"
$environmentName = "pychrono-10"
$environmentPrefix = Join-Path $miniforgeRoot "envs\$environmentName"
$pychronoPython = Join-Path $environmentPrefix "python.exe"
$sharedAuditPath = Join-Path $miniforgeRoot "share\yadof\$environmentName"

$miniforgeVersion = "26.3.2-3"
$installerFileName = "Miniforge3-26.3.2-3-Windows-x86_64.exe"
$installerUrl = "https://github.com/conda-forge/miniforge/releases/download/26.3.2-3/$installerFileName"
$installerSha256 = "14a8635465b5190537ddad6286746ffebbc55a1ed2a7bb14a506595fe3191e1e"
$pychronoVersion = "10.0.0"
$pychronoBuild = "py313h418371c_0"
$projectChronoChannel = "projectchrono/label/release"
$condaForgeChannel = "conda-forge"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-FileState {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [ordered]@{ path = $Path; exists = $false; sha256 = $null }
    }

    return [ordered]@{
        path = $Path
        exists = $true
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Get-HostBaseline {
    $profileRoot = [Environment]::GetFolderPath("UserProfile")
    $profileFiles = @(
        (Join-Path $profileRoot "Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"),
        (Join-Path $profileRoot "Documents\PowerShell\Microsoft.PowerShell_profile.ps1"),
        (Join-Path $profileRoot ".bashrc"),
        (Join-Path $profileRoot ".zshrc"),
        (Join-Path $profileRoot ".condarc")
    )
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    $launcherInventory = $null
    if ($null -ne $launcher) {
        $launcherInventory = (& $launcher.Source -0p 2>&1 | Out-String).Trim()
    }

    return [ordered]@{
        machine_path = [Environment]::GetEnvironmentVariable("Path", "Machine")
        user_path = [Environment]::GetEnvironmentVariable("Path", "User")
        machine_pythonhome = [Environment]::GetEnvironmentVariable("PYTHONHOME", "Machine")
        user_pythonhome = [Environment]::GetEnvironmentVariable("PYTHONHOME", "User")
        machine_pythonpath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Machine")
        user_pythonpath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "User")
        machine_yadof_pychrono_python = [Environment]::GetEnvironmentVariable(
            "YADOF_PYCHRONO_PYTHON",
            "Machine"
        )
        python_launcher = if ($null -eq $launcher) { $null } else { $launcher.Source }
        python_launcher_inventory = $launcherInventory
        profiles = @($profileFiles | ForEach-Object { Get-FileState -Path $_ })
    }
}

function Invoke-Conda {
    param(
        [Parameter(Mandatory = $true)][string]$CondaPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$StandardErrorPath
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = (& $CondaPath @Arguments 2> $StandardErrorPath | Out-String)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        $errorText = if (Test-Path -LiteralPath $StandardErrorPath) {
            (Get-Content -LiteralPath $StandardErrorPath -Raw -Encoding UTF8).Trim()
        } else {
            ""
        }
        throw "Conda command failed with exit code $exitCode`: $($Arguments -join ' ')`n$errorText"
    }
    return $output
}

function Set-ExplicitSharedAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $administrators = [Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
    $system = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
    $users = [Security.Principal.SecurityIdentifier]::new("S-1-5-32-545")
    $inheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
        [Security.AccessControl.InheritanceFlags]::ObjectInherit
    $propagation = [Security.AccessControl.PropagationFlags]::None
    $allow = [Security.AccessControl.AccessControlType]::Allow

    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($administrators)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $system,
        [Security.AccessControl.FileSystemRights]::FullControl,
        $inheritance,
        $propagation,
        $allow
    ))
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $administrators,
        [Security.AccessControl.FileSystemRights]::FullControl,
        $inheritance,
        $propagation,
        $allow
    ))
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $users,
        [Security.AccessControl.FileSystemRights]::ReadAndExecute,
        $inheritance,
        $propagation,
        $allow
    ))
    Set-Acl -LiteralPath $resolvedPath -AclObject $acl

    $childrenPattern = Join-Path $resolvedPath "*"
    & "$env:SystemRoot\System32\icacls.exe" $childrenPattern /reset /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed to reset descendants below $resolvedPath"
    }
    & "$env:SystemRoot\System32\icacls.exe" $resolvedPath /setowner "*S-1-5-32-544" /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed to set administrator ownership below $resolvedPath"
    }
}

function Assert-BaselineUnchanged {
    param(
        [Parameter(Mandatory = $true)]$Before,
        [Parameter(Mandatory = $true)]$After
    )

    $propertyNames = @(
        "machine_path",
        "user_path",
        "machine_pythonhome",
        "user_pythonhome",
        "machine_pythonpath",
        "user_pythonpath",
        "python_launcher",
        "python_launcher_inventory"
    )
    foreach ($propertyName in $propertyNames) {
        if ($Before[$propertyName] -ne $After[$propertyName]) {
            throw "Protected host setting changed unexpectedly: $propertyName"
        }
    }

    $beforeProfiles = $Before.profiles | ConvertTo-Json -Depth 5 -Compress
    $afterProfiles = $After.profiles | ConvertTo-Json -Depth 5 -Compress
    if ($beforeProfiles -ne $afterProfiles) {
        throw "A monitored shell or Conda profile changed unexpectedly"
    }
}

if (-not (Test-IsAdministrator)) {
    throw "This installer must run from a UAC-elevated administrator process."
}

$InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
$AuditOutputPath = [IO.Path]::GetFullPath($AuditOutputPath)
if ($AuditOutputPath.StartsWith($miniforgeRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "AuditOutputPath must be caller-owned and outside the shared Miniforge prefix."
}
New-Item -ItemType Directory -Path $AuditOutputPath -Force | Out-Null

$transcriptPath = Join-Path $AuditOutputPath "install-transcript.txt"
$resultPath = Join-Path $AuditOutputPath "install-result.json"
Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null

$status = "failed"
$failure = $null
try {
    $baselineBefore = Get-HostBaseline
    $baselineBefore | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $AuditOutputPath "host-baseline-before.json") -Encoding UTF8

    if ([IO.Path]::GetFileName($InstallerPath) -ne $installerFileName) {
        throw "Unexpected installer filename: $InstallerPath"
    }
    $actualInstallerSha256 = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualInstallerSha256 -ne $installerSha256) {
        throw "Installer SHA-256 mismatch: $actualInstallerSha256"
    }
    $installerSha256Path = "$InstallerPath.sha256"
    if (-not (Test-Path -LiteralPath $installerSha256Path -PathType Leaf)) {
        throw "Official installer SHA-256 sidecar was not found: $installerSha256Path"
    }
    $sidecarSha256 = ((Get-Content -LiteralPath $installerSha256Path -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
    if ($sidecarSha256 -ne $installerSha256) {
        throw "Official installer SHA-256 sidecar mismatch: $sidecarSha256"
    }
    $signature = Get-AuthenticodeSignature -FilePath $InstallerPath
    if ($signature.Status -ne [Management.Automation.SignatureStatus]::Valid) {
        throw "Installer Authenticode signature is not valid: $($signature.Status)"
    }

    $resumedExistingPrefix = Test-Path -LiteralPath $miniforgeRoot -PathType Container
    if ($resumedExistingPrefix) {
        if (-not $ResumeExistingMiniforge) {
            throw "Refusing to overwrite existing Miniforge root: $miniforgeRoot"
        }
        if ($baselineBefore.machine_yadof_pychrono_python) {
            throw "Resume requires an unset machine-level YADOF_PYCHRONO_PYTHON."
        }
    } else {
        $installerArguments = @(
            "/InstallationType=AllUsers",
            "/AddToPath=0",
            "/RegisterPython=0",
            "/S",
            "/D=$miniforgeRoot"
        )
        $installerProcess = Start-Process -FilePath $InstallerPath -ArgumentList $installerArguments -Wait -PassThru
        if ($installerProcess.ExitCode -ne 0) {
            throw "Miniforge installer failed with exit code $($installerProcess.ExitCode)"
        }
    }

    $reusedExistingEnvironment = Test-Path -LiteralPath $environmentPrefix -PathType Container
    if ($reusedExistingEnvironment -and -not $ResumeExistingPyChronoEnvironment) {
        throw "Refusing an existing PyChrono environment without -ResumeExistingPyChronoEnvironment."
    }

    $condaPath = Join-Path $miniforgeRoot "Scripts\conda.exe"
    if (-not (Test-Path -LiteralPath $condaPath -PathType Leaf)) {
        throw "Installed conda executable was not found: $condaPath"
    }

    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:CONDARC -ErrorAction SilentlyContinue
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    $condaConfigError = Join-Path $AuditOutputPath "conda-config.stderr.txt"
    Invoke-Conda -CondaPath $condaPath -Arguments @(
        "config", "--system", "--set", "auto_activate", "false"
    ) -StandardErrorPath $condaConfigError | Out-Null

    $pychronoSpec = "pychrono=$pychronoVersion=$pychronoBuild"
    $dryRunError = Join-Path $AuditOutputPath "conda-dry-run.stderr.txt"
    $dryRunPrefix = if ($reusedExistingEnvironment) {
        "$environmentPrefix-dry-run-plan"
    } else {
        $environmentPrefix
    }
    if ($dryRunPrefix -ne $environmentPrefix -and (Test-Path -LiteralPath $dryRunPrefix)) {
        throw "Dry-run planning prefix unexpectedly exists: $dryRunPrefix"
    }
    $dryRunArguments = @(
        "create",
        "--dry-run",
        "--json",
        "--prefix", $dryRunPrefix,
        "--no-default-packages",
        "--override-channels",
        "--strict-channel-priority",
        "-c", $projectChronoChannel,
        "-c", $condaForgeChannel,
        "python=3.13",
        $pychronoSpec
    )
    $dryRunJson = Invoke-Conda -CondaPath $condaPath -Arguments $dryRunArguments -StandardErrorPath $dryRunError
    if ($dryRunPrefix -ne $environmentPrefix -and (Test-Path -LiteralPath $dryRunPrefix)) {
        throw "Conda dry run unexpectedly created its planning prefix: $dryRunPrefix"
    }
    $dryRunPath = Join-Path $AuditOutputPath "conda-dry-run.json"
    $dryRunJson | Set-Content -LiteralPath $dryRunPath -Encoding UTF8
    $dryRun = $dryRunJson | ConvertFrom-Json

    $plannedPython = @($dryRun.actions.LINK | Where-Object { $_.name -eq "python" })
    $plannedPyChrono = @($dryRun.actions.LINK | Where-Object { $_.name -eq "pychrono" })
    if ($plannedPython.Count -ne 1 -or -not $plannedPython[0].version.StartsWith("3.13.")) {
        throw "The solver did not select exactly one Python 3.13 package."
    }
    if ($plannedPyChrono.Count -ne 1 -or
        $plannedPyChrono[0].version -ne $pychronoVersion -or
        $plannedPyChrono[0].build_string -ne $pychronoBuild) {
        throw "The solver did not select the pinned PyChrono release build."
    }
    if ($plannedPyChrono[0].channel -ne $projectChronoChannel -or
        $plannedPyChrono[0].base_url -ne "https://conda.anaconda.org/$projectChronoChannel") {
        throw "The selected PyChrono package is not from the official Project Chrono channel."
    }

    $pythonSpec = "python=$($plannedPython[0].version)=$($plannedPython[0].build_string)"
    if (-not $reusedExistingEnvironment) {
        $createError = Join-Path $AuditOutputPath "conda-create.stderr.txt"
        $createArguments = @(
            "create",
            "--yes",
            "--prefix", $environmentPrefix,
            "--no-default-packages",
            "--override-channels",
            "--strict-channel-priority",
            "-c", $projectChronoChannel,
            "-c", $condaForgeChannel,
            $pythonSpec,
            $pychronoSpec
        )
        Invoke-Conda -CondaPath $condaPath -Arguments $createArguments -StandardErrorPath $createError |
            Set-Content -LiteralPath (Join-Path $AuditOutputPath "conda-create.stdout.txt") -Encoding UTF8
    }

    if (-not (Test-Path -LiteralPath $pychronoPython -PathType Leaf)) {
        throw "PyChrono interpreter was not created: $pychronoPython"
    }

    $listError = Join-Path $AuditOutputPath "conda-list.stderr.txt"
    $listJson = Invoke-Conda -CondaPath $condaPath -Arguments @(
        "list", "--json", "--prefix", $environmentPrefix
    ) -StandardErrorPath $listError
    $listJson | Set-Content -LiteralPath (Join-Path $AuditOutputPath "conda-list.json") -Encoding UTF8
    $parsedInstalledPackages = $listJson | ConvertFrom-Json
    $installedPackages = @($parsedInstalledPackages | ForEach-Object { $_ })
    if (@($installedPackages | Where-Object { $_.name -eq "yadof" }).Count -ne 0) {
        throw "The shared PyChrono environment unexpectedly contains yadof."
    }
    $installedPython = @($installedPackages | Where-Object { $_.name -eq "python" })
    $installedPyChrono = @($installedPackages | Where-Object { $_.name -eq "pychrono" })
    if ($installedPython.Count -ne 1 -or
        $installedPython[0].version -ne $plannedPython[0].version -or
        $installedPython[0].build_string -ne $plannedPython[0].build_string) {
        throw "Installed Python does not match the pinned dry-run selection."
    }
    if ($installedPyChrono.Count -ne 1 -or
        $installedPyChrono[0].version -ne $pychronoVersion -or
        $installedPyChrono[0].build_string -ne $pychronoBuild -or
        $installedPyChrono[0].channel -notmatch "projectchrono") {
        throw "Installed PyChrono does not match the official pinned release build."
    }
    $plannedPackageKeys = @($dryRun.actions.LINK | ForEach-Object {
        "$($_.name)|$($_.version)|$($_.build_string)"
    } | Sort-Object)
    $installedPackageKeys = @($installedPackages | ForEach-Object {
        "$($_.name)|$($_.version)|$($_.build_string)"
    } | Sort-Object)
    $packageDifference = @(Compare-Object -ReferenceObject $plannedPackageKeys -DifferenceObject $installedPackageKeys)
    if ($packageDifference.Count -ne 0) {
        $differenceText = ($packageDifference | Out-String).Trim()
        throw "Installed packages differ from the recorded solver plan:`n$differenceText"
    }

    $explicitError = Join-Path $AuditOutputPath "conda-explicit.stderr.txt"
    Invoke-Conda -CondaPath $condaPath -Arguments @(
        "list", "--explicit", "--md5", "--prefix", $environmentPrefix
    ) -StandardErrorPath $explicitError |
        Set-Content -LiteralPath (Join-Path $AuditOutputPath "conda-explicit.txt") -Encoding UTF8

    $historyError = Join-Path $AuditOutputPath "conda-history.stderr.txt"
    Invoke-Conda -CondaPath $condaPath -Arguments @(
        "env", "export", "--from-history", "--prefix", $environmentPrefix
    ) -StandardErrorPath $historyError |
        Set-Content -LiteralPath (Join-Path $AuditOutputPath "environment-from-history.yml") -Encoding UTF8

    $infoError = Join-Path $AuditOutputPath "conda-info.stderr.txt"
    Invoke-Conda -CondaPath $condaPath -Arguments @("info", "--json") -StandardErrorPath $infoError |
        Set-Content -LiteralPath (Join-Path $AuditOutputPath "conda-info.json") -Encoding UTF8

    $packageLock = @(Get-ChildItem -LiteralPath (Join-Path $environmentPrefix "conda-meta") -Filter "*.json" |
        Sort-Object Name |
        ForEach-Object {
            $metadata = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            [ordered]@{
                name = $metadata.name
                version = $metadata.version
                build = $metadata.build
                build_number = $metadata.build_number
                channel = $metadata.channel
                subdir = $metadata.subdir
                url = $metadata.url
                sha256 = $metadata.sha256
                md5 = $metadata.md5
            }
        })
    $packageLock | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath (Join-Path $AuditOutputPath "installed-package-lock.json") -Encoding UTF8

    $smokeScratch = Join-Path $AuditOutputPath "smoke-scratch"
    New-Item -ItemType Directory -Path $smokeScratch -Force | Out-Null
    $smokeScriptPath = Join-Path $AuditOutputPath "pychrono-smoke.py"
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "pychrono_smoke.py") -Destination $smokeScriptPath

    $runtimePathEntries = @(
        $environmentPrefix,
        (Join-Path $environmentPrefix "Library\mingw-w64\bin"),
        (Join-Path $environmentPrefix "Library\usr\bin"),
        (Join-Path $environmentPrefix "Library\bin"),
        (Join-Path $environmentPrefix "Scripts"),
        (Join-Path $environmentPrefix "bin")
    )
    $runtimePath = (($runtimePathEntries + [Environment]::GetEnvironmentVariable("Path", "Machine")) -join ";")
    $smokeErrorPath = Join-Path $AuditOutputPath "pychrono-smoke.stderr.txt"
    $smokeOutputPath = Join-Path $AuditOutputPath "pychrono-smoke.stdout.txt"
    $smokeStartInfo = [Diagnostics.ProcessStartInfo]::new()
    $smokeStartInfo.FileName = $pychronoPython
    $smokeStartInfo.Arguments = "-B -s -P `"$smokeScriptPath`""
    $smokeStartInfo.WorkingDirectory = $smokeScratch
    $smokeStartInfo.UseShellExecute = $false
    $smokeStartInfo.CreateNoWindow = $true
    $smokeStartInfo.RedirectStandardOutput = $true
    $smokeStartInfo.RedirectStandardError = $true
    $smokeEnvironmentNames = @(
        "Path", "PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE",
        "PYTHONDONTWRITEBYTECODE", "TEMP", "TMP",
        "YADOF_EXPECTED_PYCHRONO_PYTHON", "YADOF_EXPECTED_PYCHRONO_VERSION",
        "YADOF_EXPECTED_PYCHRONO_BUILD"
    )
    $smokeEnvironmentBefore = @{}
    foreach ($name in $smokeEnvironmentNames) {
        $smokeEnvironmentBefore[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }
    try {
        [Environment]::SetEnvironmentVariable("Path", $runtimePath, "Process")
        [Environment]::SetEnvironmentVariable("PYTHONPATH", $null, "Process")
        [Environment]::SetEnvironmentVariable("PYTHONHOME", $null, "Process")
        [Environment]::SetEnvironmentVariable("PYTHONNOUSERSITE", "1", "Process")
        [Environment]::SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "1", "Process")
        [Environment]::SetEnvironmentVariable("TEMP", $smokeScratch, "Process")
        [Environment]::SetEnvironmentVariable("TMP", $smokeScratch, "Process")
        [Environment]::SetEnvironmentVariable("YADOF_EXPECTED_PYCHRONO_PYTHON", $pychronoPython, "Process")
        [Environment]::SetEnvironmentVariable("YADOF_EXPECTED_PYCHRONO_VERSION", $pychronoVersion, "Process")
        [Environment]::SetEnvironmentVariable("YADOF_EXPECTED_PYCHRONO_BUILD", $pychronoBuild, "Process")
        $smokeProcess = [Diagnostics.Process]::Start($smokeStartInfo)
        if (-not $smokeProcess.WaitForExit(120000)) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $smokeProcess.Id /T /F | Out-Null
            throw "PyChrono mechanics smoke exceeded 120 seconds."
        }
        $smokeJson = $smokeProcess.StandardOutput.ReadToEnd().Trim()
        $smokeError = $smokeProcess.StandardError.ReadToEnd().Trim()
        $smokeProcess.WaitForExit()
    } finally {
        foreach ($name in $smokeEnvironmentNames) {
            [Environment]::SetEnvironmentVariable($name, $smokeEnvironmentBefore[$name], "Process")
        }
    }
    $smokeJson | Set-Content -LiteralPath $smokeOutputPath -Encoding UTF8
    $smokeError | Set-Content -LiteralPath $smokeErrorPath -Encoding UTF8
    if ($smokeProcess.ExitCode -ne 0) {
        throw "PyChrono mechanics smoke failed with exit code $($smokeProcess.ExitCode): $smokeError"
    }
    $smokeResult = $smokeJson | ConvertFrom-Json
    if ($smokeResult.yadof_importable -or $smokeResult.pythonpath_present -or $smokeResult.user_site_enabled) {
        throw "PyChrono smoke reported an unclean child environment."
    }
    $smokeJson | Set-Content -LiteralPath (Join-Path $AuditOutputPath "pychrono-smoke.json") -Encoding UTF8

    $provenance = [ordered]@{
        schema_version = 1
        installed_at = (Get-Date).ToString("o")
        miniforge = [ordered]@{
            version = $miniforgeVersion
            release_url = "https://github.com/conda-forge/miniforge/releases/tag/$miniforgeVersion"
            installer_url = $installerUrl
            installer_file = $installerFileName
            sha256 = $actualInstallerSha256
            sha256_sidecar = $sidecarSha256
            authenticode_status = [string]$signature.Status
            signer = $signature.SignerCertificate.Subject
            signer_thumbprint = $signature.SignerCertificate.Thumbprint
            installation_type = "AllUsers"
            prefix = $miniforgeRoot
            add_to_path = $false
            register_python = $false
            conda_init = $false
            auto_activate_base = $false
            resumed_existing_prefix = $resumedExistingPrefix
            reused_existing_pychrono_environment = $reusedExistingEnvironment
        }
        pychrono = [ordered]@{
            channel = $projectChronoChannel
            version = $pychronoVersion
            build = $pychronoBuild
            package_url = "https://api.anaconda.org/download/projectchrono/pychrono/$pychronoVersion/win-64/pychrono-$pychronoVersion-$pychronoBuild.conda"
            python_version = $plannedPython[0].version
            python_build = $plannedPython[0].build_string
            prefix = $environmentPrefix
            interpreter = $pychronoPython
        }
    }
    $provenance | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $AuditOutputPath "runtime-provenance.json") -Encoding UTF8

    New-Item -ItemType Directory -Path $sharedAuditPath -Force | Out-Null
    Get-ChildItem -LiteralPath $AuditOutputPath -File | Copy-Item -Destination $sharedAuditPath -Force

    Set-ExplicitSharedAcl -Path $miniforgeRoot
    Set-ExplicitSharedAcl -Path $environmentPrefix

    $rootAcl = Get-Acl -LiteralPath $miniforgeRoot
    $environmentAcl = Get-Acl -LiteralPath $environmentPrefix
    [ordered]@{
        miniforge_root = [ordered]@{
            path = $miniforgeRoot
            owner = [string]$rootAcl.Owner
            sddl = $rootAcl.Sddl
        }
        pychrono_environment = [ordered]@{
            path = $environmentPrefix
            owner = [string]$environmentAcl.Owner
            sddl = $environmentAcl.Sddl
        }
    } | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath (Join-Path $AuditOutputPath "acl-after.json") -Encoding UTF8

    [Environment]::SetEnvironmentVariable(
        "YADOF_PYCHRONO_PYTHON",
        $pychronoPython,
        "Machine"
    )
    if ([Environment]::GetEnvironmentVariable("YADOF_PYCHRONO_PYTHON", "Machine") -ne $pychronoPython) {
        throw "Machine-level YADOF_PYCHRONO_PYTHON was not set correctly."
    }

    $baselineAfter = Get-HostBaseline
    Assert-BaselineUnchanged -Before $baselineBefore -After $baselineAfter
    $baselineAfter | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $AuditOutputPath "host-baseline-after.json") -Encoding UTF8

    $status = "success"
} catch {
    $failure = [ordered]@{
        message = $_.Exception.Message
        category = [string]$_.CategoryInfo.Category
        script_stack_trace = $_.ScriptStackTrace
    }
    throw
} finally {
    $result = [ordered]@{
        schema_version = 1
        status = $status
        completed_at = (Get-Date).ToString("o")
        miniforge_root = $miniforgeRoot
        pychrono_prefix = $environmentPrefix
        pychrono_python = $pychronoPython
        audit_output = $AuditOutputPath
        shared_audit = $sharedAuditPath
        failure = $failure
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Stop-Transcript | Out-Null
    if ($status -eq "success" -and (Test-Path -LiteralPath $sharedAuditPath -PathType Container)) {
        Get-ChildItem -LiteralPath $AuditOutputPath -File |
            Copy-Item -Destination $sharedAuditPath -Force
    }
}
