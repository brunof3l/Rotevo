# Cria (ou recria) o atalho "Script Video Maker" na area de trabalho.
# Rode com: powershell -ExecutionPolicy Bypass -File criar_atalho.ps1

$projeto = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $projeto "venv\Scripts\pythonw.exe"
$appPy = Join-Path $projeto "app.py"

if (-not (Test-Path $pythonw)) {
    Write-Host "venv nao encontrada. Rode setup.bat primeiro." -ForegroundColor Red
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$atalho = Join-Path $desktop "Script Video Maker.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($atalho)
$lnk.TargetPath = $pythonw
$lnk.Arguments = "`"$appPy`""
$lnk.WorkingDirectory = $projeto
$lnk.Description = "Cola o roteiro e gera o video narrado com gameplay de fundo"
$lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,18"  # icone de video
$lnk.Save()

Write-Host "Atalho criado: $atalho" -ForegroundColor Green
