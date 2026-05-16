/**
 * ghost//snail — M5Stick Plus2 Firmware
 * Reads IMU + I2C bus, streams JSON telemetry, renders stage on LCD.
 * Serial: 115200 baud over USB-C  (bidirectional JSON)
 *
 * PlatformIO: board = m5stick-c-plus2  (or m5stick-c-plus)
 * Frameworks: arduino, M5Unified
 */

#include <M5Unified.h>
#include <ArduinoJson.h>
#include <Wire.h>

// ── Config ────────────────────────────────────────────────────────────────────
static const uint32_t TX_INTERVAL_MS  = 500;   // telemetry every 500 ms
static const uint32_t DISPLAY_PAGE_MS = 4000;  // rotate display page every 4 s
static const uint32_t IMU_SAMPLE_MS   = 50;    // IMU samples every 50 ms

// ── State (received from Mac) ─────────────────────────────────────────────────
struct DownStream {
  int   stage  = 0;
  int   str    = 10;
  int   intel  = 10;
  int   dex    = 10;
  int   hunger = 80;
  int   xp     = 0;
  char  state[32] = "Dormant";
};

// ── IMU rolling average ───────────────────────────────────────────────────────
static float acc_x = 0, acc_y = 0, acc_z = 0;
static float avg_x = 0, avg_y = 0, avg_z = 0;
static uint8_t sample_count = 0;
static float   peak_mag     = 0;
static bool    shake_event  = false;

// ── Timing ────────────────────────────────────────────────────────────────────
static uint32_t last_tx      = 0;
static uint32_t last_page    = 0;
static uint32_t last_imu     = 0;
static uint8_t  display_page = 0;

// ── State ─────────────────────────────────────────────────────────────────────
static DownStream ds;
static bool       btn_a_pressed = false;

// ── Stage names ───────────────────────────────────────────────────────────────
static const char* STAGE_NAMES[] = {
  "Hatchling",
  "Wandering Shell",
  "Phantom Crawler",
  "Data Drifter",
  "Ghost Protocol",
  "Apex Phantom"
};
static const uint32_t STAGE_COLORS[] = {
  0x001F00,   // dim green
  0x003800,
  0x005000,
  0x006800,
  0x009000,
  0x00FF88,   // full bright at apex
};

// ── I2C scanner ───────────────────────────────────────────────────────────────
static char i2c_result[32] = "STANDALONE";

void scanI2C() {
  Wire.begin();
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      if      (addr == 0x5C) snprintf(i2c_result, sizeof(i2c_result), "ENV_IV_0x5C");
      else if (addr == 0x62) snprintf(i2c_result, sizeof(i2c_result), "TOF_EYE_0x62");
      else if (addr == 0x68) snprintf(i2c_result, sizeof(i2c_result), "IMU_EXT_0x68");
      else                   snprintf(i2c_result, sizeof(i2c_result), "MODULE_0x%02X", addr);
      return;
    }
  }
  snprintf(i2c_result, sizeof(i2c_result), "STANDALONE");
}

// ── IMU sampling ─────────────────────────────────────────────────────────────
void sampleIMU() {
  auto imu = M5.Imu.getGData();
  acc_x += imu.x; acc_y += imu.y; acc_z += imu.z;
  sample_count++;

  float mag = sqrtf(imu.x*imu.x + imu.y*imu.y + imu.z*imu.z);
  if (mag > peak_mag) peak_mag = mag;
  if (mag > 3.0f)     shake_event = true;
}

void flushIMU() {
  if (sample_count > 0) {
    avg_x = acc_x / sample_count;
    avg_y = acc_y / sample_count;
    avg_z = acc_z / sample_count;
    acc_x = acc_y = acc_z = 0;
    sample_count = 0;
  }
}

// ── Draw helpers ──────────────────────────────────────────────────────────────
static const int LCD_W = 240;
static const int LCD_H = 135;

void drawPage0() {
  // Ghost-snail stage + vitals
  M5.Lcd.fillScreen(0x000A00);

  // Stage color frame
  uint32_t col = STAGE_COLORS[min(ds.stage, 5)];
  M5.Lcd.drawRect(2, 2, LCD_W-4, LCD_H-4, col);
  M5.Lcd.drawRect(3, 3, LCD_W-6, LCD_H-6, col);

  // Stage number — large centered
  M5.Lcd.setTextSize(4);
  M5.Lcd.setTextColor(col, 0x000A00);
  char stage_s[4];
  snprintf(stage_s, sizeof(stage_s), "%d", ds.stage);
  int tx = (LCD_W - strlen(stage_s)*24) / 2;
  M5.Lcd.setCursor(tx, 14);
  M5.Lcd.print(stage_s);

  // Stage name
  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(col, 0x000A00);
  const char* sname = STAGE_NAMES[min(ds.stage, 5)];
  M5.Lcd.setCursor((LCD_W - strlen(sname)*6) / 2, 58);
  M5.Lcd.print(sname);

  // XP bar
  int xp_w = min(LCD_W - 20, (int)((ds.xp % 100) * (LCD_W-20) / 100));
  M5.Lcd.fillRect(10, 76, LCD_W-20, 6, 0x001500);
  M5.Lcd.fillRect(10, 76, xp_w,     6, col);
  M5.Lcd.setTextColor(0x008040, 0x000A00);
  M5.Lcd.setCursor(10, 88);
  M5.Lcd.printf("XP %d", ds.xp);

  // Hunger bar
  int h_w = min(LCD_W - 20, ds.hunger * (LCD_W-20) / 100);
  M5.Lcd.fillRect(10, 100, LCD_W-20, 5, 0x001500);
  M5.Lcd.fillRect(10, 100, h_w,      5, ds.hunger > 50 ? col : 0xFF4000);
  M5.Lcd.setCursor(10, 110);
  M5.Lcd.setTextColor(0x006030, 0x000A00);
  M5.Lcd.printf("HUNGER %d%%", ds.hunger);
}

void drawPage1() {
  // RPG stats
  M5.Lcd.fillScreen(0x000A00);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(0x00FF88, 0x000A00);
  M5.Lcd.setCursor(4, 4);
  M5.Lcd.print("// RPG MATRIX");

  const char* labels[] = {"STR","INT","DEX"};
  int         vals[]   = {ds.str, ds.intel, ds.dex};
  for (int i = 0; i < 3; i++) {
    int y    = 22 + i*35;
    int pct  = min(100, (vals[i] - 10) * 2);
    int bw   = (LCD_W - 20) * pct / 100;
    M5.Lcd.fillRect(10, y+14, LCD_W-20, 8, 0x001500);
    M5.Lcd.fillRect(10, y+14, bw,        8, 0x00CC66);
    M5.Lcd.setCursor(10, y+2);
    M5.Lcd.printf("%s  %d", labels[i], vals[i]);
  }

  M5.Lcd.setCursor(4, 125);
  M5.Lcd.setTextColor(0x004020, 0x000A00);
  M5.Lcd.printf("STATE: %s", ds.state);
}

void drawPage2() {
  // IMU + sensor data
  M5.Lcd.fillScreen(0x000A00);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(0x00FF88, 0x000A00);
  M5.Lcd.setCursor(4, 4);
  M5.Lcd.print("// IMU TELEMETRY");

  float mag = sqrtf(avg_x*avg_x + avg_y*avg_y + avg_z*avg_z);
  M5.Lcd.setCursor(4, 20);
  M5.Lcd.printf("X: %+.2fG", avg_x);
  M5.Lcd.setCursor(4, 36);
  M5.Lcd.printf("Y: %+.2fG", avg_y);
  M5.Lcd.setCursor(4, 52);
  M5.Lcd.printf("Z: %+.2fG", avg_z);
  M5.Lcd.setCursor(4, 68);
  M5.Lcd.printf("MAG: %.2fG", mag);
  M5.Lcd.setCursor(4, 84);
  M5.Lcd.printf("PEAK: %.2fG", peak_mag);

  M5.Lcd.setCursor(4, 104);
  M5.Lcd.setTextColor(shake_event ? 0xFF8800 : 0x004020, 0x000A00);
  M5.Lcd.printf("I2C: %s", i2c_result);
}

void drawPage3() {
  // Deduction / connection status
  M5.Lcd.fillScreen(0x000A00);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(0x00FF88, 0x000A00);
  M5.Lcd.setCursor(4, 4);
  M5.Lcd.print("// DEDUCTION");
  M5.Lcd.setCursor(4, 22);
  M5.Lcd.setTextColor(0x00FFAA, 0x000A00);
  M5.Lcd.print(ds.state);

  // Simple ghost ASCII art placeholder
  M5.Lcd.setTextSize(2);
  M5.Lcd.setTextColor(STAGE_COLORS[min(ds.stage, 5)], 0x000A00);
  M5.Lcd.setCursor(80, 55);  M5.Lcd.print(". .");
  M5.Lcd.setCursor(72, 75);  M5.Lcd.print("(o o)");
  M5.Lcd.setCursor(80, 95);  M5.Lcd.print(" )|(");
}

void updateDisplay() {
  switch (display_page % 4) {
    case 0: drawPage0(); break;
    case 1: drawPage1(); break;
    case 2: drawPage2(); break;
    case 3: drawPage3(); break;
  }
}

// ── Downstream JSON parser ────────────────────────────────────────────────────
void parseDownstream(const String& raw) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, raw) != DeserializationError::Ok) return;

  ds.stage  = doc["stage"]  | ds.stage;
  ds.str    = doc["str"]    | ds.str;
  ds.intel  = doc["intel"]  | ds.intel;
  ds.dex    = doc["dex"]    | ds.dex;
  ds.hunger = doc["hunger"] | ds.hunger;
  ds.xp     = doc["xp"]    | ds.xp;

  const char* st = doc["state"];
  if (st) snprintf(ds.state, sizeof(ds.state), "%s", st);
}

// ── Telemetry JSON builder ────────────────────────────────────────────────────
void sendTelemetry() {
  StaticJsonDocument<256> doc;
  doc["imu_x"]  = avg_x;
  doc["imu_y"]  = avg_y;
  doc["imu_z"]  = avg_z;
  doc["shake"]  = shake_event;
  doc["i2c"]    = i2c_result;
  doc["btn_a"]  = btn_a_pressed;
  doc["uptime"] = millis() / 1000;

  serializeJson(doc, Serial);
  Serial.println();

  // Reset single-shot flags
  shake_event   = false;
  btn_a_pressed = false;
  peak_mag      = 0;
}

// ── Arduino entry points ──────────────────────────────────────────────────────
void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);

  M5.Lcd.fillScreen(0x000000);
  M5.Lcd.setTextColor(0x00FF88, 0x000000);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(10, 10);
  M5.Lcd.println("ghost//snail");
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(10, 50);
  M5.Lcd.println("VMU BOOTING...");

  scanI2C();

  delay(800);
  updateDisplay();
}

void loop() {
  M5.update();
  uint32_t now = millis();

  // ── IMU sampling ──
  if (now - last_imu >= IMU_SAMPLE_MS) {
    sampleIMU();
    last_imu = now;
  }

  // ── Button A: feed action (sends btn_a flag on next packet) ──
  if (M5.BtnA.wasPressed()) {
    btn_a_pressed = true;
    display_page++;
    updateDisplay();
  }

  // ── Telemetry transmit ──
  if (now - last_tx >= TX_INTERVAL_MS) {
    flushIMU();
    sendTelemetry();
    last_tx = now;
  }

  // ── Downstream receive ──
  if (Serial.available() > 0) {
    String raw = Serial.readStringUntil('\n');
    raw.trim();
    if (raw.startsWith("{")) {
      parseDownstream(raw);
      updateDisplay();  // refresh immediately when Mac sends new data
    }
  }

  // ── Auto-rotate display ──
  if (now - last_page >= DISPLAY_PAGE_MS) {
    display_page++;
    updateDisplay();
    last_page = now;
  }
}
