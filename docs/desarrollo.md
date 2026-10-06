# Guía de desarrollo

## Estructura

```
eink-assistant/
├── ui/                      # programa de escritorio (tkinter + icono en la bandeja)
│   ├── app.py               # ventana, bandeja, atajos, API local
│   ├── controller.py        # hilo único que habla con la pantalla
│   ├── views.py             # vistas disponibles (añadir una = una entrada en VIEWS)
│   ├── hotkeys.py           # atajos de teclado globales (RegisterHotKey)
│   ├── local_api.py         # API en 127.0.0.1:8765 que usa el servidor MCP
│   └── claude_desktop.py    # registro del servidor MCP en Claude Desktop
├── display/                 # dibuja las páginas; no sabe nada del ESP32
├── device/                  # transporte; la app solo usa DisplayDevice
│   ├── base.py              # DisplayDevice, ButtonEvent, DeviceInfo
│   ├── protocol.py          # tramas A5 5A + CRC16 (ver protocolo.md)
│   ├── usb.py               # USBDisplayDevice (autodetecta el COM)
│   ├── wifi.py              # WiFiDisplayDevice (TCP + mDNS propio)
│   └── simulator.py         # ESP32 falso para probar sin hardware
├── ai/                      # ChatbotProvider: Claude (API de Anthropic)
├── sources/                 # datos: weather.py (Open-Meteo), system.py (psutil)
├── mcp_server/eink_mcp.py   # servidor MCP para Claude Desktop
├── firmware/esp32_eink/     # sketch de Arduino (config.h, protocol.h, secrets.example.h)
├── packaging/               # PyInstaller + Inno Setup → instalador
├── tools/                   # utilidades de línea de comandos
├── tests/
└── docs/
```

Principios:

- El ESP32 es lo más simple posible: solo recibe bitmaps de 400×300 y 1 bit por píxel. Toda la
  lógica va en el PC.
- `firmware/esp32_eink/protocol.h` y `device/protocol.py` deben coincidir.
  `tests/test_firmware_parser.py` lo comprueba compilando el `.h` con g++, si está instalado.

## Ejecutar desde el código

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

.venv\Scripts\pythonw.exe -m ui                 # programa (ventana + bandeja, sin consola)
.venv\Scripts\pythonw.exe -m ui --minimized     # directamente en la bandeja
```

Herramientas de línea de comandos. No funcionan con el programa abierto, porque solo uno puede
usar la pantalla a la vez:

```powershell
.venv\Scripts\python.exe -m tools.send_test_image --list-ports
.venv\Scripts\python.exe -m tools.send_test_image --port COM5            # patrón de prueba
.venv\Scripts\python.exe -m tools.send_test_image --simulate             # sin hardware → out/sim/*.png
.venv\Scripts\python.exe -m tools.show_home --preview out/home.png       # solo genera la imagen
.venv\Scripts\python.exe -m tools.show_calendar --port COM5 --month 2026-12
.venv\Scripts\python.exe -m tools.make_docs_images                       # capturas de docs/img
```

Variables de entorno:

| Variable | Para qué |
|---|---|
| `EINK_PORT`, `EINK_BAUD` | Puerto y velocidad para las herramientas de `tools/` |
| `EINK_CITY`, `EINK_LAT`, `EINK_LON` | Ubicación del tiempo (por defecto, Madrid) |
| `ANTHROPIC_API_KEY`, `EINK_AI_MODEL` | Asistente propio |
| `EINK_API_PORT` | Puerto de la API local (8765) |
| `EINK_SIEMPRE` | `1`/`0`: fuerza que Claude Desktop envíe todas sus respuestas |

Para registrar el servidor MCP en Claude Desktop desde el código: `instalar_mcp_claude.cmd`
(doble clic). Después, cierra Claude Desktop desde la bandeja.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest
```

Incluyen un ESP32 simulado (por "USB" y por TCP), así que no hace falta hardware.

## Firmware

Ver la [guía de instalación, sección 3B](instalacion.md#b-compilarlo-con-el-arduino-ide). Desde la
línea de comandos, con el `arduino-cli` que trae el Arduino IDE 2:

```powershell
arduino-cli compile --fqbn "esp32:esp32:esp32c3:CDCOnBoot=cdc" --export-binaries firmware\esp32_eink
```

`EPD_DEBUG_LOG 1` en `config.h` manda por el protocolo el registro de cada refresco (aparece en
`app.log`). **No escribas con `Serial.print` en el firmware**: el puerto transporta tramas
binarias; usa `sendLog()`.

Los binarios que compiles con Wi-Fi llevan tu contraseña dentro: no los publiques. `build/`,
`*.bin` y `secrets.h` están en `.gitignore`.

## Generar una versión

1. Sube `__version__` en `ui/__init__.py`.
2. Ejecuta:
   ```powershell
   powershell -ExecutionPolicy Bypass -File packaging\build_release.ps1
   ```
   Necesita PyInstaller (`pip install pyinstaller`), Inno Setup 6
   (`winget install JRSoftware.InnoSetup`) y el Arduino IDE 2. El script pasa los tests y genera en
   `out\release\`:
   - El instalador.
   - El firmware compilado **sin Wi-Fi**. El script comprueba que no contenga tu contraseña.
   - `SHA256SUMS.txt`.
3. Publica la versión en GitHub con esos ficheros:
   ```powershell
   gh release create vX.Y.Z out\release\* --title "vX.Y.Z" --notes "..."
   ```

## Uso desde código

```python
from device import USBDisplayDevice, WiFiDisplayDevice
from display.page import Page

with USBDisplayDevice("COM5") as display:            # o WiFiDisplayDevice("eink.local")
    display.on_button(lambda ev: print("botón", ev))  # corre en su propio hilo
    display.send_page(Page.from_image(img, number=1, total=3))
```

## Ideas pendientes

- Botones físicos ◀ ▶ en el ESP32 (`ENABLE_BUTTONS 1`, GPIO 0 y 1) para pasar páginas.
- Micrófono + reconocimiento de voz.
- Actualizar el firmware por Wi-Fi (OTA).
- Configurar el Wi-Fi sin recompilar (portal de configuración).
