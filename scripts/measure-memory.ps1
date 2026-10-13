param(
    [int]$DurationSeconds = 125,
    [int]$SampleIntervalSeconds = 5,
    [string]$ExecutablePath = "$env:LOCALAPPDATA\QuotaWidget\app\QuotaWidget\QuotaWidget.exe",
    [string]$OutputPath = "$PSScriptRoot\memory-samples.csv"
)
$ErrorActionPreference = 'Stop'
$exe = $ExecutablePath
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build the portable app first.' }
$main = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
$samples = [System.Collections.Generic.List[object]]::new()
$start = [datetime]::UtcNow
try {
    while (([datetime]::UtcNow - $start).TotalSeconds -lt $DurationSeconds) {
        $all = @(Get-CimInstance Win32_Process)
        $ids = [System.Collections.Generic.HashSet[int]]::new()
        [void]$ids.Add($main.Id)
        $changed = $true
        while ($changed) {
            $changed = $false
            foreach ($proc in $all) {
                if ($ids.Contains([int]$proc.ParentProcessId) -and $ids.Add([int]$proc.ProcessId)) { $changed = $true }
            }
        }
        $totalWorkingSet = [int64]0
        $totalPrivate = [int64]0
        $entries = foreach ($id in $ids) {
            try {
                $p = Get-Process -Id $id -ErrorAction Stop
                $totalWorkingSet += $p.WorkingSet64
                $totalPrivate += $p.PrivateMemorySize64
                [pscustomobject]@{ Id = $id; Name = $p.ProcessName; WorkingSetMiB = [math]::Round($p.WorkingSet64 / 1MB, 2); PrivateMiB = [math]::Round($p.PrivateMemorySize64 / 1MB, 2) }
            } catch { }
        }
        $samples.Add([pscustomobject]@{
            TimeUtc = [datetime]::UtcNow.ToString('o')
            ElapsedSeconds = [math]::Round(([datetime]::UtcNow - $start).TotalSeconds, 1)
            Processes = ($entries | ConvertTo-Json -Compress)
            TotalWorkingSetMiB = [math]::Round($totalWorkingSet / 1MB, 2)
            TotalPrivateMiB = [math]::Round($totalPrivate / 1MB, 2)
        })
        Start-Sleep -Seconds $SampleIntervalSeconds
        if ($main.HasExited) { throw 'Widget exited during measurement.' }
    }
} finally {
    if (-not $main.HasExited) {
        [void]$main.CloseMainWindow()
        if (-not $main.WaitForExit(5000)) { Stop-Process -Id $main.Id -Force }
    }
}
$samples | Export-Csv -LiteralPath $OutputPath -NoTypeInformation -Encoding UTF8
$samples[0], $samples[$samples.Count - 1] | Format-Table ElapsedSeconds, Processes, TotalWorkingSetMiB, TotalPrivateMiB -AutoSize
Write-Output "Samples saved to $OutputPath"
