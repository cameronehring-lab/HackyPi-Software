/**
 * ghost//snail — M5Stick Plus2  //  BASE_LINK Firmware
 * Minimal baseline: IMU Z-force → JSON over USB serial at 2 Hz.
 *
 * PlatformIO: see platformio.ini  (board = m5stick-c-plus2)
 */

#include <M5Unified.h>

static unsigned long lastTx = 0;
static const int     TX_MS  = 500;   // 2 Hz telemetry

// Rolling peak tracker — resets each transmit cycle
static float peakZ = 0.0f;

void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);

    Serial.begin(115200);

    M5.Lcd.fillScreen(BLACK);
    M5.Lcd.setTextColor(GREEN, BLACK);
    M5.Lcd.setTextSize(2);
    M5.Lcd.setCursor(10, 10);
    M5.Lcd.println("ghost//snail");
    M5.Lcd.setTextSize(1);
    M5.Lcd.setCursor(10, 50);
    M5.Lcd.println("BASE_LINK READY");
    M5.Lcd.setCursor(10, 68);
    M5.Lcd.println("Awaiting Mac...");
}

void loop() {
    M5.update();

    // Sample IMU continuously for responsive peak detection
    auto imu  = M5.Imu.getGData();
    float z   = fabsf(imu.z);
    if (z > peakZ) peakZ = z;

    // Transmit at 2 Hz
    if (millis() - lastTx >= TX_MS) {
        lastTx = millis();

        // Build lean JSON packet
        String pkt = "{";
        pkt += "\"IMU_Z_Force\":" + String(z,    2) + ",";
        pkt += "\"IMU_Z_Peak\":"  + String(peakZ, 2) + ",";
        pkt += "\"IMU_X\":"       + String(imu.x, 2) + ",";
        pkt += "\"IMU_Y\":"       + String(imu.y, 2);
        pkt += "}";
        Serial.println(pkt);

        // Update LCD with live value
        M5.Lcd.fillRect(0, 90, 240, 30, BLACK);
        M5.Lcd.setCursor(10, 90);
        M5.Lcd.setTextSize(1);
        M5.Lcd.setTextColor(GREEN, BLACK);
        M5.Lcd.printf("Z: %.2fG  PEAK: %.2fG", z, peakZ);

        peakZ = 0.0f;  // reset peak after transmit
    }
}
