# Protocolo serie PC ↔ ESP32 (v1)

Referencias de implementación: `firmware/esp32_eink/protocol.h` (C++) y `device/protocol.py` (Python).
Un test compila el parser C++ en el PC y comprueba que ambos coinciden.

## Trama

Todos los enteros en little-endian.

| Campo   | Bytes | Descripción |
|---------|-------|-------------|
| SYNC    | 2     | `A5 5A` |
| TYPE    | 1     | Tipo de mensaje |
| SEQ     | 1     | Número de secuencia (0–255, cíclico). Cada lado lleva el suyo |
| LEN     | 2     | Longitud del payload (máx. 15005 en el ESP32) |
| PAYLOAD | LEN   | Datos |
| CRC     | 2     | CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) de TYPE…PAYLOAD |

Los receptores ignoran cualquier byte anterior a `A5 5A` (mensajes del bootloader al arrancar).
El ESP32 descarta una trama a medias si pasa más de 1 s sin recibir bytes.

## Mensajes PC → ESP32

| Tipo | Nombre | Payload | Respuesta |
|------|--------|---------|-----------|
| 0x01 | PING   | — | HELLO |
| 0x10 | PAGE   | `u16 página, u16 total, u8 flags, bitmap[15000]` | ACK al **terminar** el refresco |
| 0x11 | CLEAR  | — | ACK al terminar |

Flags de PAGE: bit 0 = pedir refresco parcial (el firmware fuerza uno completo cada `FULL_REFRESH_EVERY`).

## Mensajes ESP32 → PC

| Tipo | Nombre | Payload |
|------|--------|---------|
| 0x80 | HELLO  | `u8 versión, u16 ancho, u16 alto, u8 capacidades` (bit 0 botones, bit 1 parcial). Se envía al arrancar y como respuesta a PING |
| 0x81 | ACK    | `u8 seq confirmado, u8 estado` (0 OK, 1 CRC erróneo, 2 longitud errónea, 3 tipo desconocido, 4 demasiado largo, 5 pantalla ocupada: BUSY no se liberó) |
| 0x90 | BUTTON | `u8 botón` (1 siguiente, 2 anterior, 3 seleccionar) |
| 0x9F | LOG    | Texto UTF-8 de depuración |

## Bitmap

400 × 300, 1 bit por píxel, filas de arriba abajo, 50 bytes por fila, MSB = píxel izquierdo,
**1 = negro**, 0 = blanco. 15000 bytes.

## Control de flujo

El PC envía una petición y espera su ACK antes de mandar la siguiente (una en vuelo). Como el ACK de
PAGE llega cuando el panel ya ha terminado de refrescar, nunca entran datos mientras el ESP32 está
bloqueado refrescando. Ante `BAD_CRC` o sin respuesta, el PC reintenta (2 veces por defecto).

El PC escribe cada trama en trozos de 256 bytes con 5 ms de pausa: el USB nativo del ESP32-C3
descarta bytes si recibe los 15 KB de una PAGE de golpe, y la trama incompleta se pierde sin ACK.

Antes de refrescar, el ESP32 comprueba que BUSY esté libre (espera hasta 2 s). Si no lo está
(pantalla desconectada o colgada), responde enseguida `DISPLAY_BUSY` en lugar de bloquearse; el PC
no reintenta ese estado. Con `EINK_NO_DISPLAY 1` en `config.h` el firmware ni siquiera toca la
pantalla y responde `OK` al instante: sirve para probar solo el enlace.

## Wi-Fi

Las mismas tramas, sin cambios, sobre TCP. Con `ENABLE_WIFI 1` en `config.h` el ESP32 se conecta a
la red de `secrets.h` (copia de `secrets.example.h`, fuera del repositorio), escucha en el puerto
`WIFI_TCP_PORT` (3333) y se anuncia por mDNS como `eink.local`. Admite un cliente a la vez: si se
conecta otro, sustituye al anterior. El USB sigue activo; cada canal tiene su propio parser y las
respuestas (ACK, LOG) salen por el canal de la última orden recibida.

En el PC, `WiFiDisplayDevice` (`device/wifi.py`). Por TCP no hacen falta los trozos de 256 B con
pausa que necesita el USB nativo del C3.
