# Contexto para Claude Code

Asistente de escritorio: un PC con Windows hace todo el trabajo (IA, voz, renderizado) y un ESP32 solo
muestra bitmaps 400×300 en una E-Ink y lee botones. El README es la página pública del proyecto
(GitHub); la guía de usuario está en docs/instalacion.md, la técnica en docs/desarrollo.md y el
protocolo en docs/protocolo.md. Las versiones se generan con packaging/build_release.ps1.

## Hardware real
- Dos **ESP32-C3 SuperMini** con USB nativo (USB-Serial/JTAG, VID 303A); el número de COM cambia al
  reconectar, se distinguen por el número de serie (la MAC) que muestra `list_ports`. Una es la
  cableada a la pantalla y la otra, de repuesto. La de la pantalla da "Failed to start stub flasher"
  con el IDE; se graba con el esptool 5.x del core (`Arduino15\packages\esp32\tools\esptool_py\5.3.1`)
  con `--no-stub --baud 115200 --after watchdog-reset`. Para cambios del programa basta grabar
  `esp32_eink.ino.bin` en 0x10000 (~70 s); la imagen completa `merged.bin` en 0x0 tarda ~4,5 min.
- **WeAct Studio 4.2" blanco/negro/rojo**, controlador SSD1683, clase GxEPD2 `GxEPD2_420c_GDEY042Z98`.
  Ya está seleccionada en `firmware/esp32_eink/config.h`. Refresco completo de ~25 s, sin refresco
  parcial.
- Cableado (C3): SDA→6, SCL→4, CS→7, D/C→5, RES→10, BUSY→3, VCC→3.3. No usar GPIO 2, 8, 9, 20, 21.
- Arduino IDE: placa "ESP32C3 Dev Module", **USB CDC On Boot = Enabled**. Librerías GxEPD2 y
  Adafruit GFX.

## Estado (6 oct 2026)
- Fase 1 escrita y probada solo contra el simulador: 18 tests en verde y el firmware compila (25 %
  de flash).
- Primera prueba real superada con la pantalla: página mostrada en ~10 s.
  Clave: el USB nativo del C3 pierde bytes si la PAGE llega de golpe; `device/usb.py` la envía en
  trozos de 256 B con 5 ms de pausa. `EPD_DEBUG_LOG` sigue a 1 en `config.h` (LOGs del refresco).
- Wi-Fi (fase 7) grabado y probado en la placa de la pantalla: TCP 3333, `eink.local`. Windows no
  resuelve `.local` por sí solo; `device/wifi.py` hace su propia consulta mDNS. La señal llega
  floja (~-78 dBm) en la red principal: a 8,5 dBm de emisión el router la rechazaba (motivo 202);
  a 15 dBm conecta, aunque tarda a veces. Ahora la placa va en un segundo router con su propia
  subred (conecta en ~4 s); el PC llega a ella porque está en las dos redes (cable a la principal,
  Wi-Fi a la segunda). Ahorro de energía Wi-Fi desactivado. El firmware manda LOGs de
  diagnóstico por USB mientras no conecta (estado, motivo, escaneo).
- Credenciales en `firmware/esp32_eink/secrets.h` (en `.gitignore`; plantilla en
  `secrets.example.h`). Los binarios de `build/` llevan la contraseña: nunca subirlos. La ubicación
  del tiempo del usuario está en variables de entorno de usuario (EINK_CITY/LAT/LON), no en el código.
- Python 3.12 instalado en Windows. `python` y `pip` a secas abren la Microsoft Store (alias de
  ejecución) y PowerShell bloquea `Activate.ps1`, así que hay que usar siempre
  `.venv\Scripts\python.exe`.

## Comandos
```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m tools.send_test_image --port COM4
.venv\Scripts\python.exe -m tools.send_test_image --simulate
.venv\Scripts\python.exe -m pytest
.venv\Scripts\pythonw.exe -m ui        # programa de escritorio (bandeja); ocupa el COM mientras está abierto
```
El programa guarda preferencias y registro en `%APPDATA%\eink-assistant\` (`settings.json`, `app.log`).
Claude Desktop escribe en la E-Ink vía MCP (`mcp_server/eink_mcp.py`, registrado como «eink» en
`%APPDATA%\Claude\claude_desktop_config.json`), que llama a la API local del programa
(`ui/local_api.py`, 127.0.0.1:8765). Solo el programa abre el COM.

## Reglas del proyecto
- El ESP32 debe seguir siendo lo más simple posible; toda la lógica va en el PC.
- La aplicación solo habla con `DisplayDevice` (`device/base.py`); el transporte es intercambiable.
- `firmware/esp32_eink/protocol.h` y `device/protocol.py` deben coincidir; lo comprueba
  `tests/test_firmware_parser.py`.
- No escribir texto en `Serial` desde el firmware: el puerto transporta tramas binarias (usar `sendLog`).
- Avanzar fase por fase (ver el README), sin mezclar IA, GUI y hardware en la misma iteración.
