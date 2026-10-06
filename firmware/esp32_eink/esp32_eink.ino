// esp32_eink.ino — Firmware mínimo: recibe páginas 400x300 por Serial y las
// muestra en la pantalla E-Ink. Toda la lógica vive en el PC.
//
// Librerías (Arduino IDE > Gestor de librerías):
//   - GxEPD2 (Jean-Marc Zingg)  — revisado contra 1.6.9
//   - Adafruit GFX Library      — dependencia de GxEPD2
//
// Formato de bitmap: 400x300, 1 bit por píxel, filas de arriba abajo,
// 50 bytes por fila, bit más significativo = píxel de la izquierda,
// 1 = NEGRO, 0 = BLANCO. Total 15000 bytes.
//
// IMPORTANTE: nada de Serial.print() aquí. El puerto serie transporta tramas
// binarias; para depurar usa sendLog(), que va dentro de una trama LOG.

#include <SPI.h>

// En el ESP32-C3 SuperMini el puerto USB es el USB nativo del chip. Para que
// Serial vaya por él hay que activar en el IDE: Herramientas > USB CDC On Boot
// > Enabled. Si no, Serial saldría por los pines 20/21 y el PC no recibiría nada.
#if defined(CONFIG_IDF_TARGET_ESP32C3) && !ARDUINO_USB_CDC_ON_BOOT
  #error "ESP32-C3: activa Herramientas > USB CDC On Boot > Enabled"
#endif
#include "config.h"
#if defined(EINK_PANEL_GDEY042Z98)
  #include <GxEPD2_3C.h>
#else
  #include <GxEPD2_BW.h>
#endif
#include "protocol.h"

#if ENABLE_WIFI
  #if __has_include("secrets.h")
    #include "secrets.h"
  #else
    #error "Falta secrets.h: copia secrets.example.h como secrets.h y pon tu red Wi-Fi"
  #endif
  #include <WiFi.h>
  #include <ESPmDNS.h>
#endif

// ---------------------------------------------------------------------------
// Selección de panel (ver config.h)
// EPD_BUSY_LEVEL: nivel de BUSY mientras el panel trabaja. GxEPD2 no lo expone;
// copiado de cada driver (SSD1683 = HIGH, el resto = LOW).
// ---------------------------------------------------------------------------
#if defined(EINK_PANEL_GDEY042T81)
  #define EPD_CLASS GxEPD2_420_GDEY042T81
  #define EPD_BUSY_LEVEL HIGH
#elif defined(EINK_PANEL_GDEY042Z98)
  #define EPD_CLASS GxEPD2_420c_GDEY042Z98
  #define EPD_BUSY_LEVEL HIGH
#elif defined(EINK_PANEL_GYE042A87)
  #define EPD_CLASS GxEPD2_420_GYE042A87
  #define EPD_BUSY_LEVEL HIGH
#elif defined(EINK_PANEL_GDEW042T2)
  #define EPD_CLASS GxEPD2_420
  #define EPD_BUSY_LEVEL LOW
#elif defined(EINK_PANEL_GDEW042M01)
  #define EPD_CLASS GxEPD2_420_M01
  #define EPD_BUSY_LEVEL LOW
#elif defined(EINK_PANEL_SE0420NQ04)
  #define EPD_CLASS GxEPD2_420_SE0420NQ04
  #define EPD_BUSY_LEVEL LOW
#else
  #error "Elige el panel en config.h (sección 1). Verifica antes el controlador de tu pantalla."
#endif

#if defined(EINK_PANEL_GDEY042Z98)
// El panel de tres colores no tiene refresco parcial, pero el SSD1683 admite un
// refresco solo blanco/negro "diferencial" (refresh_bw, ~1,5 s y casi sin
// parpadeo): mueve solo los píxeles que cambian entre la imagen anterior (RAM
// 0x26) y la nueva (0x24). GxEPD2 no apaga después la alimentación del panel
// (el comando 0xDC la deja encendida), así que esta subclase lo hace a mano.
class PanelBw : public EPD_CLASS {
 public:
  using EPD_CLASS::EPD_CLASS;
  void powerOffAfterBw() {
    _writeCommand(0x22);
    _writeData(0xC3);  // apagar analógico y oscilador
    _writeCommand(0x20);
    _waitWhileBusy("powerOffAfterBw", power_off_time);
  }
};
  #define HAS_BW_REFRESH 1
// Tres colores: 2 buffers de 15 KB (B/N + rojo). Solo se dibuja en negro.
GxEPD2_3C<PanelBw, EPD_CLASS::HEIGHT> display(
    PanelBw(PIN_EPD_CS, PIN_EPD_DC, PIN_EPD_RST, PIN_EPD_BUSY));
#else
  #define HAS_BW_REFRESH 0
GxEPD2_BW<EPD_CLASS, EPD_CLASS::HEIGHT> display(
    EPD_CLASS(PIN_EPD_CS, PIN_EPD_DC, PIN_EPD_RST, PIN_EPD_BUSY));
#endif

constexpr uint16_t PAGE_W = 400;
constexpr uint16_t PAGE_H = 300;
constexpr size_t BITMAP_SIZE = (size_t)PAGE_W * PAGE_H / 8;  // 15000
constexpr size_t MAX_PAYLOAD = proto::PAGE_HEADER_SIZE + BITMAP_SIZE;

// Un canal por cada vía de entrada (USB y TCP), cada uno con su parser: así
// una trama a medias por una vía no se mezcla con bytes de la otra.
struct Channel {
  Stream* io;
  uint8_t* buf;
  proto::Parser parser;
  uint32_t lastByteMs;
  Channel(Stream* s, uint8_t* b) : io(s), buf(b), parser(b, MAX_PAYLOAD), lastByteMs(0) {}
};
static uint8_t usbBuf[MAX_PAYLOAD];
static Channel usbChan(&Serial, usbBuf);
#if ENABLE_WIFI
static uint8_t tcpBuf[MAX_PAYLOAD];
static WiFiServer server(WIFI_TCP_PORT);
static WiFiClient client;
static Channel tcpChan(&client, tcpBuf);
static bool wifiUp = false;
#endif
// Por dónde salen las tramas: el canal de la última orden recibida (sus ACK y
// los LOG del refresco vuelven a quien la mandó).
static Stream* out = &Serial;
static uint8_t txSeq = 0;
static uint8_t partialCount = 0;
// Lo que hay ahora en pantalla: el refresco diferencial necesita la imagen anterior.
static uint8_t shownBitmap[BITMAP_SIZE];
static bool shownValid = false;

// Refresco parcial: B/N diferencial en el panel de 3 colores, o el parcial
// rápido de GxEPD2 en los paneles B/N que lo tienen.
static bool panelHasPartial() {
  return HAS_BW_REFRESH || display.epd2.hasFastPartialUpdate;
}

// ---------------------------------------------------------------------------
// Envío de tramas al PC
// ---------------------------------------------------------------------------
static void sendFrame(uint8_t type, const uint8_t* payload, uint16_t len) {
  uint8_t hdr[proto::HEADER_SIZE] = {proto::SYNC0, proto::SYNC1, type, txSeq++, 0, 0};
  proto::wr16(hdr + 4, len);
  uint16_t crc = proto::crc16(hdr + 2, 4);
  crc = proto::crc16(payload, len, crc);
  uint8_t tail[2];
  proto::wr16(tail, crc);
  out->write(hdr, sizeof(hdr));
  if (len) out->write(payload, len);
  out->write(tail, 2);
  out->flush();
}

static void sendHello() {
  uint8_t p[6];
  p[0] = proto::VERSION;
  proto::wr16(p + 1, display.width());
  proto::wr16(p + 3, display.height());
  uint8_t caps = 0;
  if (ENABLE_BUTTONS) caps |= proto::CAP_BUTTONS;
  if (panelHasPartial()) caps |= proto::CAP_PARTIAL;
  p[5] = caps;
  sendFrame(proto::T_HELLO, p, sizeof(p));
}

static void sendAck(uint8_t seq, uint8_t status) {
  uint8_t p[2] = {seq, status};
  sendFrame(proto::T_ACK, p, 2);
}

static void sendLog(const char* msg) {
  sendFrame(proto::T_LOG, (const uint8_t*)msg, (uint16_t)strlen(msg));
}

// ---------------------------------------------------------------------------
// Pantalla
// ---------------------------------------------------------------------------
// GxEPD2 espera a BUSY con un timeout de hasta 25 s por paso y, si vence,
// escribe "Busy Timeout!" en Serial. Para no llegar ahí con el panel ausente,
// BUSY tiene un pull hacia el nivel "ocupado" (ver setup) y se comprueba antes
// de refrescar: un pin al aire se lee como ocupado y se responde DISPLAY_BUSY.
static bool waitDisplayIdle() {
  uint32_t start = millis();
  while (digitalRead(PIN_EPD_BUSY) == EPD_BUSY_LEVEL) {
    if (millis() - start > EPD_BUSY_PRECHECK_MS) return false;
    delay(1);
  }
  return true;
}

#if EPD_DEBUG_LOG
static uint32_t refreshStartMs = 0;
static uint32_t busyLogMs = 0;

static void dbg(const char* step) {
  char m[64];
  snprintf(m, sizeof(m), "%s (t=%lu ms, BUSY=%d)", step,
           (unsigned long)(millis() - refreshStartMs), digitalRead(PIN_EPD_BUSY));
  sendLog(m);
}

// Sustituye al delay(1) de la espera de GxEPD2 (ver setup).
static void onBusyWait(const void*) {
  delay(1);
  if (millis() - busyLogMs >= 2000) {
    busyLogMs = millis();
    dbg("esperando BUSY");
  }
}
  #define DBG(step) dbg(step)
#else
  #define DBG(step) ((void)0)
#endif

static void showBitmap(const uint8_t* bitmap, bool wantPartial) {
  bool partial = wantPartial && panelHasPartial() && shownValid &&
                 partialCount < FULL_REFRESH_EVERY;
  partialCount = partial ? partialCount + 1 : 0;

#if EPD_DEBUG_LOG
  refreshStartMs = busyLogMs = millis();
#endif
#if HAS_BW_REFRESH
  if (partial) {
    // El bitmap de la página usa 1 = negro; la RAM del panel, 1 = blanco.
    DBG("refresco B/N: inicio");
    display.epd2.writeImagePartToPrevious(shownBitmap, 0, 0, PAGE_W, PAGE_H, 0, 0, PAGE_W, PAGE_H, true);
    display.epd2.writeImagePartToCurrent(bitmap, 0, 0, PAGE_W, PAGE_H, 0, 0, PAGE_W, PAGE_H, true);
    display.epd2.refresh_bw(0, 0, PAGE_W, PAGE_H);
    display.epd2.powerOffAfterBw();
    DBG("refresco B/N: fin");
    memcpy(shownBitmap, bitmap, BITMAP_SIZE);
    return;
  }
#endif
  DBG(partial ? "refresco parcial: inicio" : "refresco completo: inicio");
  display.setFullWindow();
  display.fillScreen(GxEPD_WHITE);
  display.drawBitmap(0, 0, bitmap, PAGE_W, PAGE_H, GxEPD_BLACK);
  display.display(partial);  // bloquea hasta terminar el refresco
  display.powerOff();
  DBG("refresco: fin");
  memcpy(shownBitmap, bitmap, BITMAP_SIZE);
  shownValid = true;
}

static void clearScreen() {
#if EPD_DEBUG_LOG
  refreshStartMs = busyLogMs = millis();
#endif
  DBG("borrado: inicio");
  display.setFullWindow();
  display.fillScreen(GxEPD_WHITE);
  display.display(false);
  display.powerOff();
  DBG("borrado: fin");
  memset(shownBitmap, 0, BITMAP_SIZE);  // todo blanco
  shownValid = true;
  partialCount = 0;
}

// ---------------------------------------------------------------------------
// Tramas recibidas
// ---------------------------------------------------------------------------
static void handleFrame(const proto::Frame& f) {
  switch (f.type) {
    case proto::T_PING:
      sendHello();
      break;

    case proto::T_PAGE: {
      if (f.len != MAX_PAYLOAD) { sendAck(f.seq, proto::ST_BAD_LENGTH); break; }
#if !EINK_NO_DISPLAY
      if (!waitDisplayIdle()) { sendAck(f.seq, proto::ST_DISPLAY_BUSY); break; }
      uint8_t flags = f.payload[4];
      showBitmap(f.payload + proto::PAGE_HEADER_SIZE, flags & proto::PF_PARTIAL);
#endif
      // El ACK se envía al TERMINAR el refresco: el PC no manda nada más
      // mientras tanto, así no se desborda el buffer de recepción.
      sendAck(f.seq, proto::ST_OK);
      break;
    }

    case proto::T_CLEAR:
#if !EINK_NO_DISPLAY
      if (!waitDisplayIdle()) { sendAck(f.seq, proto::ST_DISPLAY_BUSY); break; }
      clearScreen();
#endif
      sendAck(f.seq, proto::ST_OK);
      break;

    default:
      sendAck(f.seq, proto::ST_UNKNOWN_TYPE);
  }
}

static void pollChannel(Channel& ch) {
  if (!ch.parser.idle() && millis() - ch.lastByteMs > FRAME_TIMEOUT_MS) {
    ch.parser.reset();  // trama a medias abandonada
  }
  while (ch.io->available() > 0) {
    ch.lastByteMs = millis();
    proto::Result r = ch.parser.feed((uint8_t)ch.io->read());
    if (r == proto::Result::None) continue;
    out = ch.io;
    if (r == proto::Result::Frame) {
      handleFrame(ch.parser.frame());
    } else if (r == proto::Result::BadCrc) {
      sendAck(ch.parser.frame().seq, proto::ST_BAD_CRC);
    } else if (r == proto::Result::TooLong) {
      sendAck(ch.parser.frame().seq, proto::ST_TOO_LONG);
    }
  }
}

// ---------------------------------------------------------------------------
// Wi-Fi: servidor TCP con un solo cliente (el PC). Si se conecta otro, sustituye
// al anterior (p. ej. el PC se reinició sin cerrar la conexión).
// ---------------------------------------------------------------------------
#if ENABLE_WIFI
// Motivo de la última desconexión (lo rellena la tarea de Wi-Fi; se registra
// desde loop() para no escribir en el puerto desde dos tareas). 15 = handshake
// fallido (¿contraseña?), 201 = no encuentra la red, 2/202 = autenticación.
static volatile int wifiReason = 0;

static void scanForNetwork() {
  WiFi.disconnect();
  int n = WiFi.scanNetworks();
  char m[64];
  int found = -1;
  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i) == WIFI_SSID) { found = i; break; }
  }
  if (found >= 0) {
    snprintf(m, sizeof(m), "Escaneo: red encontrada, %d dBm, canal %d", (int)WiFi.RSSI(found),
             (int)WiFi.channel(found));
  } else {
    snprintf(m, sizeof(m), "Escaneo: red NO encontrada (%d redes visibles)", n);
  }
  WiFi.scanDelete();
  sendLog(m);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

static void setupWifi() {
  WiFi.onEvent([](WiFiEvent_t, WiFiEventInfo_t info) {
    wifiReason = info.wifi_sta_disconnected.reason;
  }, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  WiFi.persistent(false);  // no guardar la red en la flash (NVS) del ESP32
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(WIFI_HOSTNAME);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  WiFi.setTxPower(WIFI_TX_POWER);
  // Sin ahorro de energía: con él la radio dormita entre balizas del router y
  // se pierden los primeros paquetes de cada conexión del PC.
  WiFi.setSleep(false);
}

static void pollWifi() {
  static uint32_t lastStatusLogMs = 0;
  wl_status_t st = WiFi.status();
  bool up = st == WL_CONNECTED;
  if (up != wifiUp) {
    wifiUp = up;
    Stream* prev = out;
    out = &Serial;  // los avisos de estado, por USB
    if (up) {
      MDNS.end();
      MDNS.begin(WIFI_HOSTNAME);
      MDNS.addService("eink", "tcp", WIFI_TCP_PORT);
      server.begin();
      server.setNoDelay(true);
      char m[48];
      snprintf(m, sizeof(m), "Wi-Fi conectado: %s", WiFi.localIP().toString().c_str());
      sendLog(m);
    } else {
      sendLog("Wi-Fi desconectado");
    }
    out = prev;
  }
  if (!up) {
    // Diagnóstico mientras no conecta. Estados: 1 = no ve la red (¿lejos o solo
    // 5 GHz?), 4 = conexión rechazada (¿contraseña?), 6 = desconectado/intentando.
    if (millis() - lastStatusLogMs >= 10000) {
      static uint8_t ticks = 0;
      lastStatusLogMs = millis();
      Stream* prev = out;
      out = &Serial;
      char m[64];
      snprintf(m, sizeof(m), "Wi-Fi sin conectar (estado %d, motivo %d)", (int)st, (int)wifiReason);
      sendLog(m);
      if (++ticks % 3 == 0) scanForNetwork();  // cada 30 s sin conexión
      out = prev;
    }
    return;
  }
  if (server.hasClient()) {
    if (client) client.stop();
    client = server.accept();
    client.setNoDelay(true);
    tcpChan.parser.reset();
  }
  if (client.connected()) {
    pollChannel(tcpChan);
  } else if (out == &client) {
    out = &Serial;  // el PC se fue: los botones vuelven por USB
  }
}
#endif

// ---------------------------------------------------------------------------
// Botones (Fase 2)
// ---------------------------------------------------------------------------
#if ENABLE_BUTTONS
struct Button {
  uint8_t pin, id;
  bool stable, last;
  uint32_t changedMs;
};
static Button buttons[] = {
  {PIN_BTN_PREV, proto::BTN_PREVIOUS, HIGH, HIGH, 0},
  {PIN_BTN_NEXT, proto::BTN_NEXT, HIGH, HIGH, 0},
};

static void pollButtons() {
  uint32_t now = millis();
  for (auto& b : buttons) {
    bool v = digitalRead(b.pin);
    if (v != b.last) { b.last = v; b.changedMs = now; }
    if (v != b.stable && now - b.changedMs >= BTN_DEBOUNCE_MS) {
      b.stable = v;
      if (v == LOW) {  // pulsado (pull-up)
        uint8_t id = b.id;
        sendFrame(proto::T_BUTTON, &id, 1);
      }
    }
  }
}
#endif

// ---------------------------------------------------------------------------
void setup() {
  Serial.setRxBufferSize(SERIAL_RX_BUFFER);  // antes de begin()
  Serial.begin(SERIAL_BAUD);

#if ENABLE_BUTTONS
  for (auto& b : buttons) pinMode(b.pin, INPUT_PULLUP);
#endif

#if !EINK_NO_DISPLAY
  SPI.begin(PIN_EPD_SCK, -1, PIN_EPD_MOSI, PIN_EPD_CS);
  // serial_diag_bitrate = 0: GxEPD2 NO debe escribir en Serial.
  display.init(0, true, EPD_RESET_MS, false, SPI,
               SPISettings(EPD_SPI_HZ, MSBFIRST, SPI_MODE0));
  display.setRotation(EINK_ROTATION);
  display.setTextColor(GxEPD_BLACK);
  // Después de init(), que deja BUSY como INPUT sin pull. El panel lo maneja
  // activamente, así que el pull solo decide qué se lee con el pin al aire.
  pinMode(PIN_EPD_BUSY, EPD_BUSY_LEVEL == HIGH ? INPUT_PULLUP : INPUT_PULLDOWN);
#if EPD_DEBUG_LOG
  display.epd2.setBusyCallback(onBusyWait);
#endif
#endif

  sendHello();  // el PC lo usa para saber que el ESP32 ha arrancado
#if EINK_NO_DISPLAY
  sendLog("esp32_eink listo (EINK_NO_DISPLAY: sin pantalla)");
#else
  sendLog(waitDisplayIdle() ? "esp32_eink listo" : "esp32_eink listo, pero BUSY ocupado: revisa la pantalla");
#endif
#if ENABLE_WIFI
  setupWifi();
#endif
}

void loop() {
  pollChannel(usbChan);
#if ENABLE_WIFI
  pollWifi();
#endif
#if ENABLE_BUTTONS
  pollButtons();
#endif
}
