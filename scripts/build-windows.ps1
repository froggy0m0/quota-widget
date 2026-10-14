param(
    [string]$Python = "python",
    [string]$OutputDirectory = "$env:LOCALAPPDATA\QuotaWidget\app",
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $env:LOCALAPPDATA 'QuotaWidget\build-source'
$workRoot = Join-Path $env:LOCALAPPDATA 'QuotaWidget\build-work'
$appOutput = Join-Path $OutputDirectory 'QuotaWidget'
$buildLog = Join-Path $env:TEMP 'codex-quota-widget-build.log'
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
if (Test-Path -LiteralPath $appOutput) { Remove-Item -LiteralPath $appOutput -Recurse -Force }
foreach ($directory in @('src','scripts')) { Copy-Item (Join-Path $root $directory) -Destination $buildRoot -Recurse -Force }
Copy-Item (Join-Path $root 'requirements.txt') -Destination $buildRoot -Force
Copy-Item (Join-Path $root 'assets') -Destination $buildRoot -Recurse -Force
Copy-Item (Join-Path $root 'tests') -Destination $buildRoot -Recurse -Force
Copy-Item (Join-Path $root 'README.md') -Destination $buildRoot -Force
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $buildRoot 'src'
Push-Location $buildRoot
try {
    if (-not $SkipInstall) {
        $proc = Start-Process -FilePath $Python -ArgumentList @('-m', 'pip', 'install', '-r', 'scripts\requirements-build.txt') -NoNewWindow -Wait -PassThru -RedirectStandardOutput $buildLog -RedirectStandardError "$buildLog.err"
        if ($proc.ExitCode -ne 0) {
            Get-Content $buildLog, "$buildLog.err"
            throw "Could not install packaging dependencies (exit $($proc.ExitCode))."
        }
    }
    $proc = Start-Process -FilePath $Python -ArgumentList @('-m', 'unittest', 'discover', '-s', 'tests', '-v') -NoNewWindow -Wait -PassThru -RedirectStandardOutput $buildLog -RedirectStandardError "$buildLog.err"
    Get-Content $buildLog, "$buildLog.err"
    if ($proc.ExitCode -ne 0) { throw "Windows Python tests failed (exit $($proc.ExitCode))." }
    $buildArgs = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
        '--name', 'QuotaWidget', '--add-data', "$buildRoot\assets;assets",
        '--hidden-import', 'PIL._tkinter_finder', '--distpath', $OutputDirectory,
        '--workpath', $workRoot, '--specpath', $workRoot, 'src\main.py')
    $proc = Start-Process -FilePath $Python -ArgumentList $buildArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput $buildLog -RedirectStandardError "$buildLog.err"
    Get-Content $buildLog -Tail 25
    if ($proc.ExitCode -ne 0) {
        Get-Content "$buildLog.err"
        throw "PyInstaller failed (exit $($proc.ExitCode))."
    }
    Copy-Item README.md (Join-Path $OutputDirectory 'QuotaWidget\README.md') -Force
    @'
@echo off
start "" "%~dp0QuotaWidget.exe" %*
'@ | Set-Content -Encoding Ascii (Join-Path $OutputDirectory 'QuotaWidget\Start-Widget.cmd')
    Write-Output "Portable app: $OutputDirectory\QuotaWidget"
} finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
