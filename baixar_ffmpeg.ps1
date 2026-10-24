# Baixa o FFmpeg e coloca ffmpeg.exe e ffprobe.exe na pasta bin\ do Rotevo.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin = Join-Path $root 'bin'

if ((Test-Path (Join-Path $bin 'ffmpeg.exe')) -and (Test-Path (Join-Path $bin 'ffprobe.exe'))) {
    Write-Host 'FFmpeg ja esta na pasta bin. Nada a fazer.'
    exit 0
}

New-Item -ItemType Directory -Force -Path $bin | Out-Null
$tmp = Join-Path $env:TEMP 'rotevo_ffmpeg'
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$zip = Join-Path $tmp 'ffmpeg.zip'

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$urls = @(
    'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
    'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
)

$ok = $false
foreach ($u in $urls) {
    try {
        Write-Host "Baixando o FFmpeg (pode levar alguns minutos): $u"
        Invoke-WebRequest -Uri $u -OutFile $zip -UseBasicParsing
        $ok = $true
        break
    } catch {
        Write-Host "Falhou: $($_.Exception.Message)"
    }
}
if (-not $ok) {
    Write-Host 'Nao consegui baixar o FFmpeg. Confira a internet ou copie ffmpeg.exe e ffprobe.exe para a pasta bin manualmente.'
    exit 1
}

Write-Host 'Extraindo...'
Expand-Archive -Path $zip -DestinationPath $tmp -Force
foreach ($name in 'ffmpeg.exe', 'ffprobe.exe') {
    $file = Get-ChildItem -Path $tmp -Recurse -Filter $name | Select-Object -First 1
    if ($file) { Copy-Item $file.FullName $bin -Force }
}
Remove-Item $tmp -Recurse -Force

if ((Test-Path (Join-Path $bin 'ffmpeg.exe')) -and (Test-Path (Join-Path $bin 'ffprobe.exe'))) {
    Write-Host 'FFmpeg instalado em bin\ com sucesso.'
} else {
    Write-Host 'Algo deu errado: ffmpeg.exe ou ffprobe.exe nao foram encontrados no arquivo baixado.'
    exit 1
}
