/*
 * ESP32-CAM + INMP441 I2S Microphone Firmware
 * ============================================
 * Serves camera snapshots + live microphone audio over WiFi HTTP.
 *
 * Endpoints:
 *   GET /snapshot     → JPEG image from camera
 *   GET /audio        → Chunked PCM audio stream (16kHz, 16-bit, mono)
 *   GET /status       → JSON health check
 *
 * Hardware:
 *   Board:  AI-Thinker ESP32-CAM (or ESP32-S3-CAM)
 *   Mic:    INMP441 I2S MEMS microphone
 *
 * Wiring (ESP32-CAM — when NOT using SD card slot):
 *   INMP441 SCK  → GPIO 14
 *   INMP441 WS   → GPIO 15
 *   INMP441 SD   → GPIO 13
 *   INMP441 L/R  → GND (left channel)
 *   INMP441 VDD  → 3.3V
 *   INMP441 GND  → GND
 *
 * Wiring (ESP32-S3 — more GPIOs available):
 *   INMP441 SCK  → GPIO 42
 *   INMP441 WS   → GPIO 41
 *   INMP441 SD   → GPIO 2
 *   INMP441 L/R  → GND
 *   INMP441 VDD  → 3.3V
 *   INMP441 GND  → GND
 *
 * Build:
 *   Arduino IDE → Board: "AI Thinker ESP32-CAM"
 *   Partition:  "Huge APP (3MB No OTA/1MB SPIFFS)"
 *   Or PlatformIO: board = esp32cam
 */

#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"
#include <driver/i2s.h>

// ─── WiFi credentials ───────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ─── Camera pins (AI-Thinker ESP32-CAM) ─────────────────────────────
#define PWDN_GPIO    32
#define RESET_GPIO   -1
#define XCLK_GPIO     0
#define SIOD_GPIO    26
#define SIOC_GPIO    27
#define Y9_GPIO      35
#define Y8_GPIO      34
#define Y7_GPIO      39
#define Y6_GPIO      36
#define Y5_GPIO      21
#define Y4_GPIO      19
#define Y3_GPIO      18
#define Y2_GPIO       5
#define VSYNC_GPIO   25
#define HREF_GPIO    23
#define PCLK_GPIO    22

// ─── I2S Microphone pins (INMP441) ──────────────────────────────────
// Using pins freed when SD card is NOT used.
// If using ESP32-S3, change to GPIO 42/41/2 respectively.
#define I2S_SCK_PIN   14   // Serial Clock (BCLK)
#define I2S_WS_PIN    15   // Word Select (LRCLK)
#define I2S_SD_PIN    13   // Serial Data (DOUT from mic)

// ─── I2S audio config ───────────────────────────────────────────────
#define I2S_PORT       I2S_NUM_0
#define SAMPLE_RATE    16000   // 16kHz — backend expects this
#define SAMPLE_BITS    16
#define DMA_BUF_COUNT  4
#define DMA_BUF_LEN    1024
#define AUDIO_CHUNK    1024    // Bytes per HTTP chunk (~32ms at 16kHz/16bit)

// ─── Camera config ──────────────────────────────────────────────────
#define FRAME_SIZE FRAMESIZE_VGA   // 640x480 — good balance
#define JPEG_QUALITY 12            // 0-63, lower = better quality

// Built-in LED (flash) — GPIO 4 on AI-Thinker
#define LED_GPIO 4

WebServer server(80);

// ─── Camera init ────────────────────────────────────────────────────
bool initCamera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;
    config.pin_d0       = Y2_GPIO;
    config.pin_d1       = Y3_GPIO;
    config.pin_d2       = Y4_GPIO;
    config.pin_d3       = Y5_GPIO;
    config.pin_d4       = Y6_GPIO;
    config.pin_d5       = Y7_GPIO;
    config.pin_d6       = Y8_GPIO;
    config.pin_d7       = Y9_GPIO;
    config.pin_xclk     = XCLK_GPIO;
    config.pin_pclk     = PCLK_GPIO;
    config.pin_vsync    = VSYNC_GPIO;
    config.pin_href     = HREF_GPIO;
    config.pin_sccb_sda = SIOD_GPIO;
    config.pin_sccb_scl = SIOC_GPIO;
    config.pin_pwdn     = PWDN_GPIO;
    config.pin_reset    = RESET_GPIO;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.grab_mode    = CAMERA_GRAB_LATEST;

    // Use PSRAM if available for higher resolution
    if (psramFound()) {
        config.frame_size   = FRAME_SIZE;
        config.jpeg_quality = JPEG_QUALITY;
        config.fb_count     = 2;
        config.fb_location  = CAMERA_FB_IN_PSRAM;
    } else {
        config.frame_size   = FRAMESIZE_QVGA;  // 320x240 without PSRAM
        config.jpeg_quality = 15;
        config.fb_count     = 1;
        config.fb_location  = CAMERA_FB_IN_DRAM;
    }

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[CAM] Init failed: 0x%x\n", err);
        return false;
    }

    // Adjust sensor settings for better image quality
    sensor_t *s = esp_camera_sensor_get();
    if (s) {
        s->set_brightness(s, 1);     // Slightly brighter
        s->set_saturation(s, -1);    // Slightly desaturated
        s->set_whitebal(s, 1);       // Auto white balance ON
        s->set_awb_gain(s, 1);
        s->set_exposure_ctrl(s, 1);  // Auto exposure ON
        s->set_aec2(s, 1);
        s->set_gain_ctrl(s, 1);      // Auto gain ON
    }

    Serial.println("[CAM] Camera initialized OK");
    return true;
}

// ─── I2S Microphone init ────────────────────────────────────────────
bool initMicrophone() {
    i2s_config_t i2s_config = {
        .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate          = SAMPLE_RATE,
        .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count        = DMA_BUF_COUNT,
        .dma_buf_len          = DMA_BUF_LEN,
        .use_apll             = false,
        .tx_desc_auto_clear   = false,
        .fixed_mclk           = 0,
    };

    i2s_pin_config_t pin_config = {
        .bck_io_num   = I2S_SCK_PIN,
        .ws_io_num    = I2S_WS_PIN,
        .data_out_num = I2S_PIN_NO_CHANGE,   // No speaker output
        .data_in_num  = I2S_SD_PIN,          // Mic data input
    };

    esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
    if (err != ESP_OK) {
        Serial.printf("[MIC] I2S driver install failed: 0x%x\n", err);
        return false;
    }

    err = i2s_set_pin(I2S_PORT, &pin_config);
    if (err != ESP_OK) {
        Serial.printf("[MIC] I2S pin config failed: 0x%x\n", err);
        return false;
    }

    Serial.printf("[MIC] I2S microphone initialized OK (%dHz)\n", SAMPLE_RATE);
    return true;
}

// ─── HTTP Handlers ──────────────────────────────────────────────────

void handleSnapshot() {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        server.send(503, "text/plain", "Camera capture failed");
        return;
    }

    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.sendHeader("Cache-Control", "no-cache");
    server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
    esp_camera_fb_return(fb);
}

void handleAudioStream() {
    WiFiClient client = server.client();

    // Send HTTP headers for chunked PCM stream
    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: application/octet-stream");
    client.println("Access-Control-Allow-Origin: *");
    client.println("Cache-Control: no-cache");
    client.println("Transfer-Encoding: chunked");
    client.println("X-Audio-Rate: 16000");
    client.println("X-Audio-Bits: 16");
    client.println("X-Audio-Channels: 1");
    client.println();

    // Stream audio chunks as long as client is connected
    int16_t samples[AUDIO_CHUNK / 2];
    size_t bytes_read;

    Serial.println("[MIC] Audio stream started");

    while (client.connected()) {
        esp_err_t err = i2s_read(
            I2S_PORT,
            (void*)samples,
            AUDIO_CHUNK,
            &bytes_read,
            portMAX_DELAY
        );

        if (err != ESP_OK || bytes_read == 0) {
            continue;
        }

        // Send as HTTP chunked transfer
        char hex_len[16];
        snprintf(hex_len, sizeof(hex_len), "%X\r\n", (unsigned int)bytes_read);
        client.print(hex_len);
        client.write((uint8_t*)samples, bytes_read);
        client.print("\r\n");
    }

    // End chunked transfer
    client.print("0\r\n\r\n");
    Serial.println("[MIC] Audio stream ended");
}

void handleStatus() {
    String json = "{";
    json += "\"status\":\"ok\",";
    json += "\"camera\":true,";
    json += "\"microphone\":true,";
    json += "\"sample_rate\":" + String(SAMPLE_RATE) + ",";
    json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
    json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
    json += "\"psram\":" + String(psramFound() ? "true" : "false") + ",";
    json += "\"free_heap\":" + String(ESP.getFreeHeap());
    json += "}";

    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "application/json", json);
}

void handleRoot() {
    String html = "<html><head><title>ESP32 Smart Glasses</title></head><body>";
    html += "<h1>ESP32-CAM + INMP441 Smart Glasses</h1>";
    html += "<h2>Endpoints</h2>";
    html += "<ul>";
    html += "<li><a href='/snapshot'>/snapshot</a> — JPEG camera frame</li>";
    html += "<li><a href='/audio'>/audio</a> — PCM audio stream (16kHz/16bit/mono)</li>";
    html += "<li><a href='/status'>/status</a> — JSON health status</li>";
    html += "</ul>";
    html += "<h2>Live Camera</h2>";
    html += "<img src='/snapshot' style='max-width:640px' />";
    html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
    html += "</body></html>";

    server.send(200, "text/html", html);
}

// ─── Setup ──────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    Serial.println("\n\n=== ESP32 Smart Glasses Firmware ===\n");

    // LED off
    pinMode(LED_GPIO, OUTPUT);
    digitalWrite(LED_GPIO, LOW);

    // WiFi
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("[WIFI] Connecting");
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("\n[WIFI] FAILED — restarting in 5s");
        delay(5000);
        ESP.restart();
    }

    Serial.printf("\n[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());

    // Camera
    if (!initCamera()) {
        Serial.println("[CAM] FATAL: Camera init failed — restarting");
        delay(3000);
        ESP.restart();
    }

    // Microphone
    if (!initMicrophone()) {
        Serial.println("[MIC] WARNING: Mic init failed — running camera-only mode");
    }

    // HTTP routes
    server.on("/", handleRoot);
    server.on("/snapshot", handleSnapshot);
    server.on("/audio", handleAudioStream);
    server.on("/status", handleStatus);
    server.begin();

    Serial.println("\n=== Ready ===");
    Serial.printf("  Camera:  http://%s/snapshot\n", WiFi.localIP().toString().c_str());
    Serial.printf("  Audio:   http://%s/audio\n", WiFi.localIP().toString().c_str());
    Serial.printf("  Status:  http://%s/status\n", WiFi.localIP().toString().c_str());
    Serial.println();

    // Flash LED briefly to indicate ready
    digitalWrite(LED_GPIO, HIGH);
    delay(200);
    digitalWrite(LED_GPIO, LOW);
}

// ─── Loop ───────────────────────────────────────────────────────────
void loop() {
    server.handleClient();

    // Reconnect WiFi if lost
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WIFI] Lost connection — reconnecting...");
        WiFi.reconnect();
        int attempts = 0;
        while (WiFi.status() != WL_CONNECTED && attempts < 20) {
            delay(500);
            attempts++;
        }
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("[WIFI] Reconnect failed — restarting");
            delay(3000);
            ESP.restart();
        }
        Serial.printf("[WIFI] Reconnected: %s\n", WiFi.localIP().toString().c_str());
    }
}
