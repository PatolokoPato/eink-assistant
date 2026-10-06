// Compila protocol.h del firmware en el PC y lo alimenta con bytes de stdin.
// Lo usa tests/test_firmware_parser.py para comprobar que C++ y Python coinciden.
#include <cstdio>
#include <vector>
#include "../firmware/esp32_eink/protocol.h"

int main() {
  static uint8_t buf[15005];
  proto::Parser parser(buf, sizeof(buf));
  int c;
  while ((c = std::getchar()) != EOF) {
    proto::Result r = parser.feed((uint8_t)c);
    proto::Frame f = parser.frame();
    if (r == proto::Result::Frame)
      std::printf("FRAME %u %u %u %04x\n", f.type, f.seq, f.len, proto::crc16(f.payload, f.len));
    else if (r == proto::Result::BadCrc)
      std::printf("BADCRC %u\n", f.seq);
    else if (r == proto::Result::TooLong)
      std::printf("TOOLONG %u\n", f.seq);
  }
  // Trama codificada en C++ para que Python la decodifique.
  uint8_t out[32];
  const uint8_t pl[2] = {0x2A, 0x00};
  size_t n = proto::encode(proto::T_ACK, 0x2A, pl, 2, out, sizeof(out));
  std::printf("ENCODED");
  for (size_t i = 0; i < n; i++) std::printf(" %02x", out[i]);
  std::printf("\n");
}
