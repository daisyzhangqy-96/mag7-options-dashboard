$taskName = "MAG7 Options Daily Refresh"
$bat = "C:\Users\daisyzhang\options-dashboard\deploy-silent.bat"
$wd  = "C:\Users\daisyzhang\options-dashboard"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "removed existing task"
}

$action   = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $wd
$trigger  = New-ScheduledTaskTrigger -Daily -At 9:15PM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Daily MAG7 options refresh + push to GitHub Pages at 21:15 Beijing (US pre-market)" | Out-Null

Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
(Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo) | Select-Object NextRunTime, LastRunTime
