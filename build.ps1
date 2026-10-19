param([string]$DistDirectory = 'dist')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$originalPath = $env:PATH
& ./.venv/Scripts/python.exe scripts/prepare_version.py
if ($LASTEXITCODE -ne 0) { throw 'Version metadata failed' }
try {
    # Prevent unrelated tools' ICU/OpenSSL DLLs on PATH from being bundled over Windows DLLs.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$PSScriptRoot\.venv\Scripts"
    & ./.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --distpath $DistDirectory --name '截图聊天' --icon assets/scissors.ico --version-file .release-build/version-info.txt --additional-hooks-dir hooks --add-data 'assets;assets' --add-data 'LICENSE;.' --add-data 'THIRD_PARTY_NOTICES.md;.' --add-data 'licenses;licenses' --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtPdf main.py
} finally {
    $env:PATH = $originalPath
}
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Write-Output "Ready: $DistDirectory/截图聊天.exe"
