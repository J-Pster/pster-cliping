<#
.SYNOPSIS
  Baixa um build estatico de ffmpeg/ffprobe pra Windows (com libass, exigido pelo
  burn-in de legenda do engine, ver engine/CLAUDE.md) e extrai so os .exe pra
  resources/ffmpeg, sem precisar de ffmpeg ja instalado na maquina.
#>

$ErrorActionPreference = 'Stop'

$AppRoot = Split-Path -Parent $PSScriptRoot
$ResourcesDir = Join-Path $AppRoot 'resources'
$FfmpegDir = Join-Path $ResourcesDir 'ffmpeg'
$TmpDir = Join-Path $AppRoot '.runtime-tmp\ffmpeg'

# Build "gpl" da BtbN (https://github.com/BtbN/FFmpeg-Builds): estatico, licenca GPL,
# inclui libass. "master-latest" e um link estavel que a BtbN sempre mantem apontando
# pro ultimo build verde.
$FfmpegZipUrl = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'

if (Test-Path $FfmpegDir) { Remove-Item -Recurse -Force $FfmpegDir }
New-Item -ItemType Directory -Force -Path $FfmpegDir, $TmpDir | Out-Null

Write-Host "== Baixando ffmpeg (BtbN gpl build) =="
$ZipPath = Join-Path $TmpDir 'ffmpeg.zip'
Invoke-WebRequest -Uri $FfmpegZipUrl -OutFile $ZipPath
$ExtractDir = Join-Path $TmpDir 'ffmpeg-extract'
Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force

$BinDir = Get-ChildItem -Path $ExtractDir -Directory | Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName 'bin' }
Copy-Item (Join-Path $BinDir 'ffmpeg.exe') $FfmpegDir
Copy-Item (Join-Path $BinDir 'ffprobe.exe') $FfmpegDir

if (Test-Path $TmpDir) { Remove-Item -Recurse -Force $TmpDir }

Write-Host "== OK: resources/ffmpeg pronto =="
