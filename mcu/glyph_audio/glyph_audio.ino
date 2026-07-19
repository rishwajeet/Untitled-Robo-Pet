// glyph_audio.ino — Glyph C6 (ESP32-C6) as Bittu's voice box.
// Listens on TCP :8301, receives raw PCM (16-bit mono), plays via I2S.
// The UNO Q streams TTS audio to it over WiFi (see linux/audio_c6.py).
//
// ASK HELP DESK: which pins the kit speaker module uses on the Glyph, and
// whether it's I2S (3 pins: BCLK/WS/DIN) or analog. Adjust PIN_* below.
// Board: "ESP32C6 Dev Module" (arduino-esp32 core 3.x). Library: ESP_I2S (built in).

#include <WiFi.h>
#include <ESP_I2S.h>

const char *SSID = "CHANGE_ME";      // phone hotspot — same net as UNO Q
const char *PASS = "CHANGE_ME";

#define SAMPLE_RATE 24000            // matches OpenAI TTS wav output
#define PIN_BCLK 4                   // I2S bit clock   } verify against the
#define PIN_WS   5                   // I2S word select } speaker module /
#define PIN_DOUT 6                   // I2S data out    } help desk

I2SClass i2s;
WiFiServer server(8301);

void setup() {
  Serial.begin(115200);
  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.print("\nAudio node IP: ");
  Serial.println(WiFi.localIP());   // <- put this IP in C6_IP on the UNO Q

  i2s.setPins(PIN_BCLK, PIN_WS, PIN_DOUT);
  i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
  server.begin();
}

uint8_t buf[1024];

void loop() {
  WiFiClient client = server.accept();
  if (!client) { delay(10); return; }
  Serial.println("stream start");
  while (client.connected()) {
    int n = client.read(buf, sizeof(buf));
    if (n > 0) i2s.write(buf, n);
    else if (n < 0) break;
  }
  client.stop();
  Serial.println("stream end");
}
