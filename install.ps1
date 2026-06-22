param(
    [string]$Version = "latest"
)

$ErrorActionPreference = "Stop"

$Repo = if ($env:MIRRORVIEW_GITHUB_REPO) { $env:MIRRORVIEW_GITHUB_REPO } else { "Zhuanz/MirrorView" }
$InstallBase = if ($env:MIRRORVIEW_INSTALL_BASE) { $env:MIRRORVIEW_INSTALL_BASE } else { Join-Path $HOME ".mirrorview-tui" }

$archRaw = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLower()
switch ($archRaw) {
    "x64" { $Arch = "x64" }
    "arm64" { $Arch = "arm64" }
    default {
        Write-Error "[MirrorView TUI] Unsupported architecture: $archRaw"
        exit 1
    }
}

if ($Version -eq "latest") {
    $ReleaseApi = "https://api.github.com/repos/$Repo/releases/latest"
}
else {
    $Tag = $Version
    if (-not $Tag.StartsWith("tui-v")) {
        $Tag = "tui-v$Tag"
    }
    $ReleaseApi = "https://api.github.com/repos/$Repo/releases/tags/$Tag"
}

Write-Host "[MirrorView TUI] Resolving release ($Version) for windows-$Arch ..."
$release = Invoke-RestMethod -Uri $ReleaseApi -Headers @{ "User-Agent" = "mirrorview-installer" }

$pattern = "mirrorview-tui-.*-windows-$Arch\.zip$"
$asset = $release.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
if (-not $asset) {
    Write-Error "[MirrorView TUI] No prebuilt asset found for windows-$Arch."
    exit 1
}

$TagName = $release.tag_name
if (-not $TagName) {
    Write-Error "[MirrorView TUI] Invalid release metadata."
    exit 1
}

$TargetDir = Join-Path $InstallBase $TagName
if (Test-Path $TargetDir) {
    Remove-Item -Path $TargetDir -Recurse -Force
}
New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null

$tmpZip = Join-Path $env:TEMP $asset.name
Write-Host "[MirrorView TUI] Downloading $($asset.name) ..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tmpZip

Write-Host "[MirrorView TUI] Installing into $TargetDir ..."
Expand-Archive -Path $tmpZip -DestinationPath $TargetDir -Force
Remove-Item -Path $tmpZip -Force -ErrorAction SilentlyContinue

$envFile = Join-Path $InstallBase ".env"
if (-not (Test-Path $envFile)) {
@"
# MirrorView TUI runtime config
DEEPSEEK_API_KEY=sk-xxxx
"@ | Out-File -FilePath $envFile -Encoding utf8 -Force
}

$exePath = Join-Path $TargetDir "MirrorView TUI.exe"
if (-not (Test-Path $exePath)) {
    $fallback = Join-Path $TargetDir "mirrorview-tui.exe"
    if (Test-Path $fallback) {
        $exePath = $fallback
    }
    else {
        Write-Error "[MirrorView TUI] Missing executable in package."
        exit 1
    }
}

$runnerBat = Join-Path $InstallBase "mirrorview-tui.bat"
@"
@echo off
start "" "$exePath"
"@ | Out-File -FilePath $runnerBat -Encoding ascii -Force

function New-Shortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Save()
}

$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "MirrorView TUI.lnk"
New-Shortcut -ShortcutPath $desktopShortcut -TargetPath $exePath -WorkingDirectory $TargetDir

$startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "MirrorView"
New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
$startMenuShortcut = Join-Path $startMenuDir "MirrorView TUI.lnk"
New-Shortcut -ShortcutPath $startMenuShortcut -TargetPath $exePath -WorkingDirectory $TargetDir

Write-Host ""
Write-Host "[MirrorView TUI] Installation complete."
Write-Host "1) Set your key in: $envFile"
Write-Host "2) Start app by double-clicking:"
Write-Host "   - Desktop shortcut: $desktopShortcut"
Write-Host "   - Start Menu: $startMenuShortcut"
Write-Host ""
