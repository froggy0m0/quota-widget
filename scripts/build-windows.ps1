param(
    [string]$Python = "python",
    [string]$OutputDirectory = "$PSScriptRoot\..\releases",
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION must contain major.minor.patch.' }
if (-not (Select-String -LiteralPath (Join-Path $root 'CHANGELOG.md') -SimpleMatch "## v$version " -Quiet)) {
    throw 'Add the release version to CHANGELOG.md before building.'
}
$releaseName = "QuotaWidget-v$version-windows-x64"
$releaseDir = Join-Path $OutputDirectory "v$version"
$appOutput = Join-Path $releaseDir "$releaseName.exe"
$checksumOutput = Join-Path $releaseDir 'SHA256SUMS.txt'
if ((Test-Path -LiteralPath $appOutput) -or (Test-Path -LiteralPath $checksumOutput)) {
    throw 'This release already exists. Bump VERSION and CHANGELOG.md to create a new release.'
}
$buildRoot = Join-Path $env:TEMP ('QuotaWidget-build-' + [guid]::NewGuid().ToString('N'))
$sourceRoot = Join-Path $buildRoot 'source'
$workRoot = Join-Path $buildRoot 'work'
$distRoot = Join-Path $buildRoot 'dist'
$log = Join-Path $buildRoot 'build.log'
$utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Path $sourceRoot -Force | Out-Null
try {
    foreach ($name in @('VERSION','requirements.txt')) {
        Copy-Item -LiteralPath (Join-Path $root $name) -Destination $sourceRoot
    }
    foreach ($name in @('src','assets','tests','scripts')) {
        Copy-Item -LiteralPath (Join-Path $root $name) -Destination $sourceRoot -Recurse
    }
    $versionTuple = ($version.Replace('.', ',') + ',0')
    $versionResource = @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($versionTuple), prodvers=($versionTuple), mask=0x3f,
                   flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', ''),
    StringStruct('FileDescription', 'Quota Widget for Codex and Claude'),
    StringStruct('FileVersion', '$version'),
    StringStruct('InternalName', 'QuotaWidget'),
    StringStruct('OriginalFilename', '$releaseName.exe'),
    StringStruct('ProductName', 'Quota Widget'),
    StringStruct('ProductVersion', '$version')
  ])]), VarFileInfo([VarStruct('Translation', [1033,1200])])])
"@
    $versionFile = Join-Path $sourceRoot 'version-info.txt'
    [IO.File]::WriteAllText($versionFile, $versionResource, $utf8)
    $previousPythonPath = $env:PYTHONPATH
    Push-Location $sourceRoot
    try {
        if (-not $SkipInstall) {
            $p = Start-Process -FilePath $Python -ArgumentList @('-m','pip','install','-r','scripts\requirements-build.txt') -NoNewWindow -Wait -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
            if ($p.ExitCode -ne 0) { Get-Content $log, "$log.err"; throw 'Build dependency installation failed.' }
        }
        $env:PYTHONPATH = Join-Path $sourceRoot 'src'
        $p = Start-Process -FilePath $Python -ArgumentList @('-m','unittest','discover','-s','tests','-v') -NoNewWindow -Wait -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
        Get-Content $log, "$log.err"
        if ($p.ExitCode -ne 0) { throw 'Windows Python tests failed.' }
        $arguments = @('-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
            '--name', $releaseName, '--add-data', ('"{0}\assets;assets"' -f $sourceRoot),
            '--add-data', ('"{0}\VERSION;."' -f $sourceRoot),
            '--version-file', ('"{0}"' -f $versionFile), '--hidden-import','PIL._tkinter_finder',
            '--distpath', ('"{0}"' -f $distRoot), '--workpath', ('"{0}"' -f $workRoot),
            '--specpath', ('"{0}"' -f $workRoot), 'src\main.py')
        $p = Start-Process -FilePath $Python -ArgumentList $arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
        Get-Content $log -Tail 12
        if ($p.ExitCode -ne 0) { Get-Content "$log.err" -Tail 25; throw 'PyInstaller failed.' }
    } finally {
        $env:PYTHONPATH = $previousPythonPath
        Pop-Location
    }
    $builtExe = Join-Path $distRoot "$releaseName.exe"
    if (-not (Test-Path -LiteralPath $builtExe -PathType Leaf)) { throw 'Release EXE was not created.' }
    $reader = [IO.BinaryReader]::new([IO.File]::OpenRead($builtExe))
    try {
        $reader.BaseStream.Position = 0x3c
        $peOffset = $reader.ReadInt32()
        $reader.BaseStream.Position = $peOffset + 4
        if ($reader.ReadUInt16() -ne 0x8664) { throw 'The release must be built with Windows x64 Python.' }
    } finally { $reader.Dispose() }
    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
    [IO.File]::Copy($builtExe, $appOutput, $false)
    try {
        $hash = (Get-FileHash -LiteralPath $appOutput -Algorithm SHA256).Hash.ToLowerInvariant()
        [IO.File]::WriteAllText($checksumOutput, "$hash  $releaseName.exe`n", $utf8)
    } catch {
        Remove-Item -LiteralPath $appOutput
        throw
    }
    Write-Output "Release: $appOutput"
    Write-Output "SHA256:  $hash"
} finally {
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}
