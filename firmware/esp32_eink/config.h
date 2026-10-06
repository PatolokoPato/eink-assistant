// config.h — Ajustes de hardware. REVISAR ANTES DE COMPILAR.
#pragma once

// ---------------------------------------------------------------------------
// 1) PANEL E-INK: deja activo EXACTAMENTE UNO.
//
//    Tu pantalla: WeAct Studio 4.2" (AliExpress 1005009677805398), controlador
//    SSD1683, confirmado con el ejemplo oficial de WeAct para GxEPD2.
//      - Variante "4.2-Black-White"     -> EINK_PANEL_GDEY042T81
//      - Variante "4.2-Black-White-Red" -> EINK_PANEL_GDEY042Z98  (activada: la tuya)
//    La de tres colores refresca mucho más lento (~25 s) y no admite refresco
//    parcial. El rojo no se usa: las páginas son blanco/negro.
// ---------------------------------------------------------------------------
//#define EINK_PANEL_GDEY042T81    // SSD1683 B/N   — WeAct 4.2" B/N, Good Display GDEY042T81, Waveshare 4.2" V2
#define EINK_PANEL_GDEY042Z98      // SSD1683 B/N/R — WeAct 4.2" B/N/Rojo, Good Display GDEY042Z98
//#define EINK_PANEL_GYE042A87     // SSD1683 B/N   — paneles GY-E042A87
//#define EINK_PANEL_GDEW042T2     // IL0398  B/N   — Good Display GDEW042T2, Waveshare 4.2" V1
//#define EINK_PANEL_GDEW042M01    // UC8176  B/N   — Good Display GDEW042M01
//#define EINK_PANEL_SE0420NQ04    // UC8276C B/N   — paneles SE0420NQ04

// ---------------------------------------------------------------------------
// 2) PINES. Se eligen solos según la placa seleccionada en el Arduino IDE.
// ---------------------------------------------------------------------------
#if defined(CONFIG_IDF_TARGET_ESP32C3)
  // ESP32-C3 SuperMini. Pines expuestos: 0-10, 20, 21.
  // Evitados a propósito:
  //   2, 8, 9 -> pines de arranque (strapping); 8 es además el LED azul y
  //              9 el botón BOOT.
  //   20, 21  -> UART0, por donde el bootloader escribe al arrancar.
  #define PIN_EPD_SCK    4
  #define PIN_EPD_MOSI   6
  #define PIN_EPD_CS     7
  #define PIN_EPD_DC     5
  #define PIN_EPD_RST   10
  #define PIN_EPD_BUSY   3
  #define PIN_BTN_PREV   0
  #define PIN_BTN_NEXT   1
#else
  // ESP32 clásico (DevKit), bus VSPI.
  #define PIN_EPD_SCK   18
  #define PIN_EPD_MOSI  23
  #define PIN_EPD_CS     5
  #define PIN_EPD_DC    17
  #define PIN_EPD_RST   16
  #define PIN_EPD_BUSY   4
  #define PIN_BTN_PREV  32   // GPIO 34-39 no tienen pull-up interno
  #define PIN_BTN_NEXT  33
#endif

// Duración del pulso de reset en ms. WeAct usa 50 en sus ejemplos. Las placas
// "driver" de Waveshare con circuito de reset propio necesitan 2.
#define EPD_RESET_MS  50

// Velocidad SPI hacia el panel.
#define EPD_SPI_HZ    4000000

// Rotación: 0 o 2 (horizontal 400x300). 1/3 darían 300x400 y no coinciden con
// el formato de página.
#define EINK_ROTATION  0

// Tras cuántos refrescos parciales se fuerza uno completo (evita "ghosting").
#define FULL_REFRESH_EVERY  8

// 1 = no tocar la pantalla: PAGE y CLEAR responden OK al instante. Solo para
// probar el enlace PC <-> ESP32 sin el panel conectado. En uso normal, 0.
#define EINK_NO_DISPLAY  0

// Antes de refrescar se espera como mucho esto a que BUSY quede libre. Si no
// se libera (panel desconectado o colgado) se responde DISPLAY_BUSY en vez de
// entrar en la espera de GxEPD2, que escribe "Busy Timeout!" en Serial.
#define EPD_BUSY_PRECHECK_MS  2000

// 1 = mandar LOGs de cada paso del refresco y, cada 2 s mientras se espera a
// BUSY, el tiempo transcurrido. Para diagnosticar cuelgues. En uso normal, 0.
#define EPD_DEBUG_LOG  1

// ---------------------------------------------------------------------------
// 3) SERIE
// ---------------------------------------------------------------------------
// Con un conversor CP2102/CH340 debe coincidir con --baud en el PC (si hay
// errores de CRC, baja a 460800 o 115200 en ambos lados).
// En el ESP32-C3 SuperMini (USB nativo) el valor da igual: siempre va a la
// velocidad del USB.
#define SERIAL_BAUD   921600
#define SERIAL_RX_BUFFER  4096

// Si una trama se queda a medias más de este tiempo, se descarta.
#define FRAME_TIMEOUT_MS  1000

// ---------------------------------------------------------------------------
// 4) WI-FI. Las mismas tramas que por USB, sobre TCP. El USB sigue funcionando.
//    La red y la contraseña van en secrets.h (copia de secrets.example.h), que
//    no se sube al repositorio.
// ---------------------------------------------------------------------------
#ifndef ENABLE_WIFI         // el binario publicado se compila con -DENABLE_WIFI=0 (sin secrets.h)
  #define ENABLE_WIFI   1
#endif
#define WIFI_HOSTNAME   "eink"     // el PC la encuentra como eink.local
#define WIFI_TCP_PORT   3333       // debe coincidir con device/wifi.py
// Potencia de emisión. Muchos ESP32-C3 SuperMini no conectan a la máxima por
// su antena. Con 8,5 dBm el router rechazaba la conexión (señal ~-78 dBm);
// con 15 dBm conecta. Si falla, prueba WIFI_POWER_11dBm o WIFI_POWER_19_5dBm.
#define WIFI_TX_POWER   WIFI_POWER_15dBm

// ---------------------------------------------------------------------------
// 5) BOTONES (Fase 2). Conectar entre el GPIO y GND (pull-up interno).
//    Los pines están en la sección 2.
// ---------------------------------------------------------------------------
#define ENABLE_BUTTONS  0
#define BTN_DEBOUNCE_MS 40
