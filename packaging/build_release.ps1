# Genera los ficheros de una versión publicable en out\release\:
#   - EInkAssistant-Setup-<versión>.exe  (instalador del programa, Inno Setup)
#   - esp32_eink-c3-usb-<versión>.bin    (firmware SIN Wi-Fi: no lleva ninguna contraseña)
#   - SHA256SUMS.txt
#
# Requisitos: .venv con requirements-dev.txt + pyinstaller, Inno Setup 6 y el
# Arduino IDE 2 (con el core esp32 y las librerías GxEPD2 y Adafruit GFX).
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_release.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"

$Version = & $Py -c "from ui import __version__; print(__version__)"
Write-Host "== E-Ink Assistant $Version ==" -ForegroundColor Cyan

$Release = Join-Path $Root "out\release"
Remove-Item -Recurse -Force $Release -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Release, "out\build" | Out-Null

Write-Host "-- Tests"
& $Py -m pytest -q
if ($LASTEXITCODE) { throw "Fallan los tests" }

Write-Host "-- Icono"
& $Py -c "from ui.app import make_icon; make_icon(256).save(r'out\build\eink-assistant.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(256,256)])"

Write-Host "-- Ejecutables (PyInstaller)"
& $Py -m PyInstaller packaging\eink_assistant.spec --noconfirm --distpath out\dist --workpath out\build\pyi
if ($LASTEXITCODE) { throw "Falló PyInstaller" }

Write-Host "-- Instalador (Inno Setup)"
$Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { throw "No encuentro Inno Setup 6 (winget install JRSoftware.InnoSetup)" }
& $Iscc /Q "/DAppVersion=$Version" packaging\installer.iss
if ($LASTEXITCODE) { throw "Falló Inno Setup" }

Write-Host "-- Firmware sin Wi-Fi (ESP32-C3)"
$Cli = "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
$FwOut = Join-Path $Root "out\build\firmware"
& $Cli compile --fqbn "esp32:esp32:esp32c3:CDCOnBoot=cdc" --output-dir $FwOut `
    --build-property "compiler.cpp.extra_flags=-DENABLE_WIFI=0" firmware\esp32_eink
if ($LASTEXITCODE) { throw "Falló la compilación del firmware" }
$Fw = Join-Path $Release "esp32_eink-c3-usb-$Version.bin"
Copy-Item (Join-Path $FwOut "esp32_eink.ino.merged.bin") $Fw

# Comprobación de seguridad: el firmware publicado no puede llevar la contraseña Wi-Fi local.
$Secrets = "firmware\esp32_eink\secrets.h"
if (Test-Path $Secrets) {
    $m = Select-String -Path $Secrets -Pattern 'WIFI_PASSWORD\s+"([^"]+)"'
    if ($m) {
        $pw = $m.Matches[0].Groups[1].Value
        $leak = & $Py -c "import sys; print(sys.argv[2].encode() in open(sys.argv[1],'rb').read())" $Fw $pw
        if ($leak -ne "False") { throw "¡El firmware publicado contiene la contraseña Wi-Fi! No se publica." }
    }
}

Write-Host "-- SHA256"
Get-ChildItem $Release -File | ForEach-Object {
    "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
} | Set-Content (Join-Path $Release "SHA256SUMS.txt") -Encoding ascii

Write-Host "`nListo:" -ForegroundColor Green
Get-ChildItem $Release | Format-Table Name, @{n="MB"; e={"{0:N1}" -f ($_.Length / 1MB)}} -AutoSize
