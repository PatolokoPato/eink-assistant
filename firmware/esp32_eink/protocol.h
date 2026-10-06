// protocol.h — Protocolo de tramas PC <-> ESP32 (sin dependencias de Arduino).
//
// Formato de trama (todos los enteros en little-endian):
//
//   +------+------+------+-----+---------+-----------------+---------+
//   | 0xA5 | 0x5A | TYPE | SEQ | LEN(u16)| PAYLOAD[LEN]    | CRC(u16)|
//   +------+------+------+-----+---------+-----------------+---------+
//
//   CRC = CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) calculado sobre
//         TYPE, SEQ, LEN y PAYLOAD (no incluye los bytes de sincronía).
//
// Este fichero es la referencia en C++ del protocolo. La implementación en
// Python vive en device/protocol.py y ambas deben mantenerse idénticas
// (tests/test_firmware_parser.py las compara compilando este fichero con g++).

#pragma once
#include <stddef.h>
#include <stdint.h>

namespace proto {

constexpr uint8_t SYNC0 = 0xA5;
constexpr uint8_t SYNC1 = 0x5A;
constexpr uint8_t VERSION = 1;

// PC -> ESP32
constexpr uint8_t T_PING  = 0x01;  // payload vacío. Respuesta: HELLO
constexpr uint8_t T_PAGE  = 0x10;  // u16 page, u16 total, u8 flags, bitmap. Respuesta: ACK
constexpr uint8_t T_CLEAR = 0x11;  // payload vacío. Respuesta: ACK

// ESP32 -> PC
constexpr uint8_t T_HELLO  = 0x80;  // u8 version, u16 width, u16 height, u8 caps
constexpr uint8_t T_ACK    = 0x81;  // u8 seq confirmado, u8 status
constexpr uint8_t T_BUTTON = 0x90;  // u8 botón
constexpr uint8_t T_LOG    = 0x9F;  // texto UTF-8 (depuración)

// Estado en ACK
constexpr uint8_t ST_OK           = 0;
constexpr uint8_t ST_BAD_CRC      = 1;
constexpr uint8_t ST_BAD_LENGTH   = 2;
constexpr uint8_t ST_UNKNOWN_TYPE = 3;
constexpr uint8_t ST_TOO_LONG     = 4;
constexpr uint8_t ST_DISPLAY_BUSY = 5;  // BUSY no se liberó: pantalla ausente o colgada

// Flags de PAGE
constexpr uint8_t PF_PARTIAL = 0x01;  // pedir refresco parcial si el panel lo admite

// Capacidades en HELLO
constexpr uint8_t CAP_BUTTONS = 0x01;
constexpr uint8_t CAP_PARTIAL = 0x02;

// Botones
constexpr uint8_t BTN_NEXT     = 1;
constexpr uint8_t BTN_PREVIOUS = 2;
constexpr uint8_t BTN_SELECT   = 3;

constexpr size_t HEADER_SIZE = 6;  // sync(2) + type + seq + len(2)
constexpr size_t CRC_SIZE = 2;
constexpr size_t PAGE_HEADER_SIZE = 5;  // u16 page, u16 total, u8 flags

inline uint16_t crc16_update(uint16_t crc, uint8_t b) {
  crc ^= (uint16_t)b << 8;
  for (int i = 0; i < 8; i++) {
    crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}

inline uint16_t crc16(const uint8_t* data, size_t len, uint16_t crc = 0xFFFF) {
  for (size_t i = 0; i < len; i++) crc = crc16_update(crc, data[i]);
  return crc;
}

inline uint16_t rd16(const uint8_t* p) { return (uint16_t)(p[0] | (p[1] << 8)); }
inline void wr16(uint8_t* p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }

// Construye una trama completa en `out`. Devuelve el tamaño o 0 si no cabe.
inline size_t encode(uint8_t type, uint8_t seq, const uint8_t* payload, uint16_t len,
                     uint8_t* out, size_t cap) {
  size_t total = HEADER_SIZE + len + CRC_SIZE;
  if (total > cap) return 0;
  out[0] = SYNC0; out[1] = SYNC1; out[2] = type; out[3] = seq;
  wr16(out + 4, len);
  for (uint16_t i = 0; i < len; i++) out[HEADER_SIZE + i] = payload[i];
  wr16(out + HEADER_SIZE + len, crc16(out + 2, 4 + len));
  return total;
}

struct Frame {
  uint8_t type;
  uint8_t seq;
  uint16_t len;
  const uint8_t* payload;
};

enum class Result : uint8_t { None, Frame, BadCrc, TooLong };

// Parser incremental: se le pasa byte a byte lo que llega por el puerto.
// Ignora cualquier basura previa a 0xA5 0x5A (p. ej. mensajes de arranque
// del bootloader del ESP32).
class Parser {
 public:
  Parser(uint8_t* buf, size_t cap) : buf_(buf), cap_(cap) {}

  void reset() { st_ = S_SYNC0; }
  bool idle() const { return st_ == S_SYNC0; }

  Result feed(uint8_t b) {
    switch (st_) {
      case S_SYNC0:
        if (b == SYNC0) st_ = S_SYNC1;
        break;
      case S_SYNC1:
        st_ = (b == SYNC1) ? S_TYPE : (b == SYNC0 ? S_SYNC1 : S_SYNC0);
        break;
      case S_TYPE:
        type_ = b; crc_ = crc16_update(0xFFFF, b); st_ = S_SEQ;
        break;
      case S_SEQ:
        seq_ = b; crc_ = crc16_update(crc_, b); st_ = S_LEN0;
        break;
      case S_LEN0:
        len_ = b; crc_ = crc16_update(crc_, b); st_ = S_LEN1;
        break;
      case S_LEN1:
        len_ |= (uint16_t)b << 8; crc_ = crc16_update(crc_, b);
        if (len_ > cap_) { st_ = S_SYNC0; return Result::TooLong; }
        pos_ = 0;
        st_ = len_ ? S_PAYLOAD : S_CRC0;
        break;
      case S_PAYLOAD:
        buf_[pos_++] = b; crc_ = crc16_update(crc_, b);
        if (pos_ >= len_) st_ = S_CRC0;
        break;
      case S_CRC0:
        rxcrc_ = b; st_ = S_CRC1;
        break;
      case S_CRC1:
        rxcrc_ |= (uint16_t)b << 8;
        st_ = S_SYNC0;
        return (rxcrc_ == crc_) ? Result::Frame : Result::BadCrc;
    }
    return Result::None;
  }

  // Válido tras Result::Frame (y type/seq también tras BadCrc/TooLong).
  Frame frame() const { return Frame{type_, seq_, len_, buf_}; }

 private:
  enum State : uint8_t { S_SYNC0, S_SYNC1, S_TYPE, S_SEQ, S_LEN0, S_LEN1, S_PAYLOAD, S_CRC0, S_CRC1 };
  uint8_t* buf_;
  size_t cap_;
  State st_ = S_SYNC0;
  uint8_t type_ = 0, seq_ = 0;
  uint16_t len_ = 0, pos_ = 0, crc_ = 0, rxcrc_ = 0;
};

}  // namespace proto
