#include <Arduino.h>
#include <WiFi.h>

// ===================== User config =====================
static constexpr uint16_t TCP_PORT = 5000;

static const char *WIFI_SSID = "COYOO-2.4G";
static const char *WIFI_PASSWORD = "G1702120305";

static constexpr uint16_t FRAME_MAGIC = 0xA55A;
static constexpr int8_t SAMPLE_DATA[] = {1, 2, 3, 4, 5, 6, 7, 8};

struct __attribute__((packed)) TcpFrame {
    uint16_t magic;
    uint32_t frameIndex;
    uint32_t microsTime;
    int8_t data[sizeof(SAMPLE_DATA)];
};

// ===================== TCP sender =====================
WiFiServer server(TCP_PORT);
WiFiClient client;
uint32_t frameCounter = 0;

void startWiFi()
{
    WiFi.mode(WIFI_OFF);
    delay(100);

    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.printf("Connecting to Wi-Fi SSID: %s", WIFI_SSID);
    while (WiFi.status() != WL_CONNECTED) {
        delay(300);
        Serial.print('.');
    }
    Serial.println();
    Serial.print("ESP32 IP address: ");
    Serial.println(WiFi.localIP());
}

void waitForClient()
{
    if (client && client.connected()) {
        return;
    }
    
    if (client) {
        client.stop();
    }

    client = server.available();
    if (client) {
        client.setNoDelay(true);
        client.setTimeout(1);
        Serial.print("TCP client connected from ");
        Serial.println(client.remoteIP());
    }
}

bool writeAll(const uint8_t *data, size_t length)
{
    size_t offset = 0;
    uint16_t idleLoops = 0;

    while (offset < length && client && client.connected()) {
        const size_t sent = client.write(data + offset, length - offset);
        if (sent > 0) {
            offset += sent;
            idleLoops = 0;
            continue;
        }

        delay(1);
        if (++idleLoops > 1000) {
            break;
        }
    }

    return offset == length;
}

TcpFrame makeFrame()
{
    TcpFrame frame = {};
    frame.magic = FRAME_MAGIC;
    frame.frameIndex = frameCounter++;
    frame.microsTime = micros();

    for (size_t i = 0; i < sizeof(SAMPLE_DATA); ++i) {
        frame.data[i] = SAMPLE_DATA[i];
    }

    return frame;
}

void setup()
{
    Serial.begin(115200);
    delay(300);

    startWiFi();
    server.begin();
    Serial.printf("TCP server listening on port %u\r\n", TCP_PORT);
}

void loop()
{
    waitForClient();

    if (!client || !client.connected()) {
        delay(1);
        return;
    }

    const TcpFrame frame = makeFrame();
    if (!writeAll(reinterpret_cast<const uint8_t *>(&frame), sizeof(frame))) {
        Serial.println("TCP write failed. Closing client.");
        client.stop();
    }
}
