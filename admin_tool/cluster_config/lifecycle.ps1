param(
    [ValidateSet('Snapshot','Stop','Start','Restore','Protect','ExecuteAcl')][string]$Action,
    [string]$PlanPath,
    [string]$TargetPath
)
$ErrorActionPreference = 'Stop'
$taskName = 'Yadof-frpc'
function Stop-Condor {
    $service = Get-Service -Name condor -ErrorAction Stop
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name condor -Force
        $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(45))
    }
}
function Stop-FrpcTask {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $taskName
        $deadline = [datetime]::UtcNow.AddSeconds(20)
        while ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running') {
            if ([datetime]::UtcNow -gt $deadline) { throw 'The managed frpc task did not stop' }
            Start-Sleep -Milliseconds 200
        }
    }
}
switch ($Action) {
    'Protect' {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($sid in @($identity, 'S-1-5-18', 'S-1-5-32-544') | Select-Object -Unique) {
            $principal = New-Object Security.Principal.SecurityIdentifier($sid)
            $rule = New-Object Security.AccessControl.FileSystemAccessRule($principal, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
            $acl.AddAccessRule($rule)
        }
        Set-Acl -LiteralPath $TargetPath -AclObject $acl
    }
    'ExecuteAcl' {
        & icacls.exe $TargetPath /grant '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)M' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Cannot grant HTCondor execute-directory permissions' }
    }
    'Snapshot' {
        $service = Get-CimInstance Win32_Service -Filter "Name='condor'"
        if (-not $service) { throw 'HTCondor Windows service condor is not installed' }
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        $snapshot = @{ startMode=$service.StartMode; running=($service.State -eq 'Running'); taskXml=$null; taskRunning=$false }
        if ($task) {
            $snapshot.taskXml = Export-ScheduledTask -TaskName $taskName
            $snapshot.taskRunning = ($task.State -eq 'Running')
        }
        $snapshot | ConvertTo-Json -Compress
    }
    'Stop' {
        Stop-Condor
        Stop-FrpcTask
    }
    'Start' {
        $plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($plan.detached) {
            Set-Service -Name condor -StartupType Disabled
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($task) { Disable-ScheduledTask -TaskName $taskName | Out-Null }
            break
        }
        if ($plan.mode -eq 'frp') {
            $taskAction = New-ScheduledTaskAction -Execute $plan.frpc_exe -Argument ('-c "' + $plan.frpc_config + '"') -WorkingDirectory (Split-Path -Parent $plan.frpc_exe)
            $trigger = New-ScheduledTaskTrigger -AtStartup
            $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
            $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
            Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
            Start-ScheduledTask -TaskName $taskName
            Start-Sleep -Seconds 2
            if ((Get-ScheduledTask -TaskName $taskName).State -ne 'Running') { throw 'frpc task did not stay running; check frpc configuration and token-file permissions' }
        } else {
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($task) { Disable-ScheduledTask -TaskName $taskName | Out-Null }
        }
        Set-Service -Name condor -StartupType Automatic
        Start-Service -Name condor
        (Get-Service condor).WaitForStatus('Running', [TimeSpan]::FromSeconds(45))
    }
    'Restore' {
        $snapshot = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Stop-Condor
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($task) {
            Stop-FrpcTask
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
        if ($snapshot.taskXml) {
            Register-ScheduledTask -TaskName $taskName -Xml $snapshot.taskXml -Force | Out-Null
            if ($snapshot.taskRunning) { Start-ScheduledTask -TaskName $taskName }
        }
        $startMode = @{ Auto='Automatic'; Manual='Manual'; Disabled='Disabled' }[$snapshot.startMode]
        Set-Service -Name condor -StartupType $startMode
        if ($snapshot.running) { Start-Service -Name condor }
    }
}
