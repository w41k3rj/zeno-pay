#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_Fingerprint.h>
#include <Keypad.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <mbedtls/sha256.h>
#include <time.h>
#include <esp32-hal-rgb-led.h>

#include "server_config.h"
#include "generated_server_config.h"

LiquidCrystal_I2C lcd(kLcdI2cAddress, kLcdColumns, kLcdRows);

HardwareSerial localFingerSerial(1);
HardwareSerial rs485Serial(2);
Adafruit_Fingerprint localFinger = Adafruit_Fingerprint(&localFingerSerial);

const byte ROWS = 4;
const byte COLS = 4;
char keys[ROWS][COLS] = {
  // The connected keypad is electrically transposed relative to the
  // printed legend, so the lookup table is transposed to make the
  // reported key match the label the user presses.
  {'1', '4', '7', '*'},
  {'2', '5', '8', '0'},
  {'3', '6', '9', '#'},
  {'A', 'B', 'C', 'D'}
};

byte rowPins[ROWS] = {kKeypadRow1Pin, kKeypadRow2Pin, kKeypadRow3Pin, kKeypadRow4Pin};
byte colPins[COLS] = {kKeypadCol1Pin, kKeypadCol2Pin, kKeypadCol3Pin, kKeypadCol4Pin};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

enum class RgbMode : uint8_t {
  Boot,
  WiFiConnect,
  Ready,
  Warning,
  Error,
  Scan,
  Success
};

enum class RequestFailureKind : uint8_t {
  None,
  WiFiOffline,
  TlsSetup,
  ServerConnection,
  ServerPayload
};

bool wifiReady = false;
bool serverReady = false;
bool localSensorReady = false;
bool remoteSensorReady = false;
bool remoteTransportReady = false;
bool systemBooting = true;
bool wifiConnecting = false;
unsigned long lastHeartbeatAtMs = 0;
unsigned long lastTlsClockSyncAttemptAtMs = 0;
unsigned long lastRgbStepAtMs = 0;
unsigned long rgbTemporaryUntilMs = 0;
uint16_t rgbAnimationPhase = 0;
RgbMode rgbTemporaryMode = RgbMode::Boot;
RequestFailureKind lastRequestFailureKind = RequestFailureKind::None;

String currentAccountCode = "";
String currentUserName = "";

char readKeypadKey();
void updateRgbStatus();
RgbMode getBaseRgbMode();
void refreshRgbStatus();
void setTemporaryRgbMode(RgbMode mode, unsigned long holdMs);
void setRgbColor(uint8_t red, uint8_t green, uint8_t blue);
void pauseWithRgb(unsigned long pauseMs);
void updateStatusLeds();
void buzz(uint8_t times, unsigned int onMs = 100, unsigned int offMs = 70);
String formatLcdLine(String value);
void printLcdLine(uint8_t row, const String &value);
void showMessage(const String &line1, const String &line2 = "", const String &line3 = "", const String &line4 = "", unsigned long pauseMs = 0);
void displayHome();
void showZkReaderInfo();
bool ensureWiFi();
bool ensureServerReady(bool quiet = false);
void updateServerReady(bool ready, const char *reason = "", int httpCode = 0, bool forceLog = false);
void setRequestFailure(RequestFailureKind kind);
bool clockLooksValid();
bool ensureClockForTls();
bool sendHeartbeatIfDue(bool force = false);
String promptDigits(const String &title, const String &subtitle, uint8_t minLength, uint8_t maxLength, bool maskInput = false);
String maskValue(size_t length);
String extractMessage(const JsonDocument &doc, const String &fallback);
bool postJson(const String &path, JsonDocument &requestDoc, JsonDocument &responseDoc, int &httpCode, bool quiet = false);
void runRegistrationFlow();
void runPaymentFlow();
bool requestRegistrationSlot(const String &accountSuffix, uint16_t &slotId, String &accountCode);
bool enrollFingerprint(uint16_t slotId);
bool waitForFinger(bool requireFinger, unsigned long timeoutMs);
bool downloadStoredTemplateHash(uint16_t slotId, String &hashHex);
bool readTemplatePacketHash(String &hashHex);
String sha256ToHex(const uint8_t *data, size_t len);
String buildFallbackFingerprintHash(uint16_t slotId, const String &accountCode);
bool registerUserOnServer(const String &accountSuffix, const String &phoneNumber, const String &nidaNumber, const String &pin, uint16_t slotId, const String &fingerprintHash, const String &fingerprintSource);
bool matchLocalFingerprint(uint16_t &slotId);
bool identifyLocalUser(uint16_t slotId);
bool verifyPaymentOnServer(uint16_t slotId, const String &pin, float amount);

void setup() {
  Serial.begin(115200);

  pinMode(kLedPowerPin, OUTPUT);
  pinMode(kLedAs608Pin, OUTPUT);
  pinMode(kLedZkPin, OUTPUT);
  pinMode(kLedWifiPin, OUTPUT);
  pinMode(kBuzzerPin, OUTPUT);
  digitalWrite(kLedPowerPin, HIGH);
  digitalWrite(kBuzzerPin, LOW);

#ifdef RGB_BUILTIN
  if (kEnableRgbStatusLed) {
    pinMode(RGB_BUILTIN, OUTPUT);
    setRgbColor(0, 0, kRgbStatusBrightness);
  }
#endif

  if (kLcdSdaPin >= 0 && kLcdSclPin >= 0) {
    Wire.begin(kLcdSdaPin, kLcdSclPin);
  } else {
    Wire.begin();
  }
  lcd.init();
  lcd.backlight();
  showMessage("W41K3RJ Pay", "Booting system");

  localFingerSerial.begin(kLocalFingerprintBaud, SERIAL_8N1, kLocalFingerprintRxPin, kLocalFingerprintTxPin);
  localFinger.begin(kLocalFingerprintBaud);
  localSensorReady = localFinger.verifyPassword();
  if (localSensorReady) {
    uint8_t packetStatus = localFinger.setPacketSize(FINGERPRINT_PACKET_SIZE_32);
    localFinger.getParameters();
    Serial.printf("[FINGER] AS608 packet size %s, active=%u bytes\n",
                  packetStatus == FINGERPRINT_OK ? "set" : "unchanged",
                  localFinger.packet_len);
  }

  // The F12 is wired as an RS485 slave reader, but raw template
  // capture/matching on the ESP32 is not available from this project yet.
  remoteTransportReady = kZkReaderTransportConfigured;
  remoteSensorReady = kZkReaderPowerPresent;

  systemBooting = false;
  wifiReady = ensureWiFi();
  updateStatusLeds();

  if (!localSensorReady) {
    showMessage("AS608 offline", "Check TX RX GND", "Local pay blocked", "", 1800);
  }

  if (wifiReady) {
    buzz(1, 80, 40);
    if (!ensureServerReady(false)) {
      showMessage("Server offline", "Press D to sync", "No register/pay", "", 1600);
    }
  }

  displayHome();
  Serial.println("System ready.");
  Serial.printf("LCD I2C: SDA=%d SCL=%d ADDR=0x%02X\n", kLcdSdaPin, kLcdSclPin, kLcdI2cAddress);
  Serial.printf("Keypad rows: %u %u %u %u\n", kKeypadRow1Pin, kKeypadRow2Pin, kKeypadRow3Pin, kKeypadRow4Pin);
  Serial.printf("Keypad cols: %u %u %u %u\n", kKeypadCol1Pin, kKeypadCol2Pin, kKeypadCol3Pin, kKeypadCol4Pin);
  Serial.println("Open dashboard with HTTPS on port 8443.");
}

void loop() {
  updateRgbStatus();
  sendHeartbeatIfDue();

  char key = readKeypadKey();
  if (!key) {
    pauseWithRgb(20);
    return;
  }

  if (key == 'A') {
    runRegistrationFlow();
    displayHome();
    return;
  }

  if (key == 'B' || key == '#') {
    runPaymentFlow();
    displayHome();
    return;
  }

  if (key == 'D') {
    ensureServerReady(false);
    displayHome();
    return;
  }

  if (key == 'C') {
    showZkReaderInfo();
    displayHome();
    return;
  }
}

char readKeypadKey() {
  char key = keypad.getKey();
  if (key && kLogKeypadToSerial) {
    Serial.printf("[KEYPAD] %c\n", key);
  }
  return key;
}

void setRgbColor(uint8_t red, uint8_t green, uint8_t blue) {
#ifdef RGB_BUILTIN
  if (kEnableRgbStatusLed) {
    neopixelWrite(RGB_BUILTIN, red, green, blue);
  }
#else
  (void) red;
  (void) green;
  (void) blue;
#endif
}

RgbMode getBaseRgbMode() {
  if (systemBooting) {
    return RgbMode::Boot;
  }

  if (wifiConnecting) {
    return RgbMode::WiFiConnect;
  }

  if (!wifiReady || !serverReady || !localSensorReady) {
    return RgbMode::Error;
  }

  if (!remoteSensorReady || !remoteTransportReady) {
    return RgbMode::Warning;
  }

  return RgbMode::Ready;
}

void refreshRgbStatus() {
  lastRgbStepAtMs = 0;
  updateRgbStatus();
}

void setRequestFailure(RequestFailureKind kind) {
  lastRequestFailureKind = kind;
}

void setTemporaryRgbMode(RgbMode mode, unsigned long holdMs) {
  rgbTemporaryMode = mode;
  rgbTemporaryUntilMs = holdMs == 0 ? 0 : millis() + holdMs;
  refreshRgbStatus();
}

void updateRgbStatus() {
#ifdef RGB_BUILTIN
  if (!kEnableRgbStatusLed) {
    return;
  }

  unsigned long now = millis();
  if (rgbTemporaryUntilMs != 0 &&
      static_cast<long>(now - rgbTemporaryUntilMs) >= 0) {
    rgbTemporaryUntilMs = 0;
  }

  if (now - lastRgbStepAtMs < kRgbStatusStepMs) {
    return;
  }
  lastRgbStepAtMs = now;
  rgbAnimationPhase = (rgbAnimationPhase + 12) % 512;

  const uint16_t triangle =
      rgbAnimationPhase < 256 ? rgbAnimationPhase : 511 - rgbAnimationPhase;
  const uint8_t floor = 6;
  const uint8_t pulse = floor +
      ((static_cast<uint32_t>(triangle) * (kRgbStatusBrightness - floor)) / 255);
  const bool blinkOn = rgbAnimationPhase < 256;
  const RgbMode activeMode =
      rgbTemporaryUntilMs != 0 ? rgbTemporaryMode : getBaseRgbMode();

  switch (activeMode) {
    case RgbMode::Boot:
      setRgbColor(0, pulse / 4, pulse);
      break;
    case RgbMode::WiFiConnect:
      setRgbColor(0, pulse / 2, pulse);
      break;
    case RgbMode::Ready:
      setRgbColor(0, pulse, 0);
      break;
    case RgbMode::Warning:
      setRgbColor(pulse, pulse / 3, 0);
      break;
    case RgbMode::Error:
      setRgbColor(blinkOn ? pulse : 0, 0, 0);
      break;
    case RgbMode::Scan:
      setRgbColor(pulse / 3, 0, pulse);
      break;
    case RgbMode::Success:
      setRgbColor(0, blinkOn ? pulse : 0, blinkOn ? pulse / 6 : 0);
      break;
  }
#endif
}

void pauseWithRgb(unsigned long pauseMs) {
  unsigned long start = millis();
  while (millis() - start < pauseMs) {
    updateRgbStatus();
    delay(10);
  }
}

void updateStatusLeds() {
  digitalWrite(kLedPowerPin, HIGH);
  digitalWrite(kLedAs608Pin, localSensorReady ? HIGH : LOW);
  digitalWrite(kLedZkPin, remoteSensorReady ? HIGH : LOW);
  digitalWrite(kLedWifiPin, wifiReady ? HIGH : LOW);
  refreshRgbStatus();
}

void buzz(uint8_t times, unsigned int onMs, unsigned int offMs) {
  for (uint8_t i = 0; i < times; ++i) {
    digitalWrite(kBuzzerPin, HIGH);
    pauseWithRgb(onMs);
    digitalWrite(kBuzzerPin, LOW);
    if (i + 1 < times) {
      pauseWithRgb(offMs);
    }
  }
}

String formatLcdLine(String value) {
  value.toUpperCase();
  if (value.length() > kLcdColumns) {
    value = value.substring(0, kLcdColumns);
  }
  while (value.length() < kLcdColumns) {
    value += ' ';
  }
  return value;
}

void printLcdLine(uint8_t row, const String &value) {
  lcd.setCursor(0, row);
  lcd.print(formatLcdLine(value));
}

void showMessage(const String &line1, const String &line2, const String &line3, const String &line4, unsigned long pauseMs) {
  printLcdLine(0, line1);
  printLcdLine(1, line2);
  printLcdLine(2, line3);
  printLcdLine(3, line4);
  if (pauseMs > 0) {
    pauseWithRgb(pauseMs);
  }
}

void displayHome() {
  updateStatusLeds();
  printLcdLine(0, "W41K3RJ BIOMETRIX");
  printLcdLine(1, "A REG   B PAY");
  printLcdLine(2,
               String(wifiReady ? "WF OK " : "WF -- ") +
               String(serverReady ? "SV OK " : "SV -- ") +
               String(localSensorReady ? "FP OK" : "FP --"));
  printLcdLine(3, "C ZK INFO D SYNC");
}

void showZkReaderInfo() {
  showMessage("ZKTeco F12", "RS485 slave only", "No direct enroll", "No server match", 2600);
  showMessage("Use AS608 here", "Or USB reader", "like ZK8500R", "for real SDK", 2600);
}

bool ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    wifiReady = true;
    wifiConnecting = false;
    updateStatusLeds();
    return true;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);

  if (kUseStaticIp) {
    WiFi.config(kDeviceIp, kGateway, kSubnet, kDns1, kDns2);
  }

  wifiReady = false;
  serverReady = false;
  wifiConnecting = true;
  updateStatusLeds();
  WiFi.begin(kWifiSsid, kWifiPassword);
  showMessage("Connecting WiFi", kWifiSsid, "Please wait...");

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    pauseWithRgb(250);
  }

  wifiReady = WiFi.status() == WL_CONNECTED;
  wifiConnecting = false;
  if (wifiReady && kValidateServerCertificate) {
    ensureClockForTls();
  }
  updateStatusLeds();
  return wifiReady;
}

void updateServerReady(bool ready, const char *reason, int httpCode, bool forceLog) {
  if (forceLog || serverReady != ready) {
    Serial.printf("[SERVER] %s", ready ? "OK" : "FAIL");
    if (reason && reason[0] != '\0') {
      Serial.printf(" %s", reason);
    }
    if (httpCode != 0) {
      Serial.printf(" (HTTP %d)", httpCode);
    }
    Serial.println();
  }
  serverReady = ready;
  updateStatusLeds();
}

bool ensureServerReady(bool quiet) {
  if (!ensureWiFi()) {
    updateServerReady(false, "wifi-offline", 0, true);
    if (!quiet) {
      setTemporaryRgbMode(RgbMode::Error, 1500);
      showMessage("WiFi offline", "No server access", "", "", 1500);
    }
    return false;
  }

  if (sendHeartbeatIfDue(true)) {
    return true;
  }

  if (!quiet) {
    setTemporaryRgbMode(RgbMode::Error, 1500);
    showMessage("Server offline", "Check PC server", "Press D to sync", "", 1500);
  }
  return false;
}

bool clockLooksValid() {
  time_t now = time(nullptr);
  return now >= static_cast<time_t>(kTlsMinimumUnixTime);
}

bool ensureClockForTls() {
  if (!kValidateServerCertificate) {
    return false;
  }

  if (clockLooksValid()) {
    return true;
  }

  if (lastTlsClockSyncAttemptAtMs != 0 &&
      millis() - lastTlsClockSyncAttemptAtMs < 30000) {
    return clockLooksValid();
  }

  lastTlsClockSyncAttemptAtMs = millis();
  configTime(0, 0, kNtpServer1, kNtpServer2, kNtpServer3);

  unsigned long start = millis();
  while (!clockLooksValid() && millis() - start < kTlsClockSyncTimeoutMs) {
    pauseWithRgb(200);
  }

  if (clockLooksValid()) {
    Serial.println("TLS clock synced for HTTPS verification.");
    return true;
  }

  Serial.println("TLS clock sync not ready. HTTPS may use insecure fallback.");
  return false;
}

bool sendHeartbeatIfDue(bool force) {
  if (!force && millis() - lastHeartbeatAtMs < kHeartbeatIntervalMs) {
    return serverReady;
  }

  if (!ensureWiFi()) {
    updateServerReady(false, "wifi-offline", 0, force);
    return false;
  }

  JsonDocument requestDoc;
  requestDoc["terminal_id"] = kTerminalId;
  requestDoc["machine_name"] = kMachineName;
  requestDoc["ip_address"] = WiFi.localIP().toString();
  requestDoc["wifi_ssid"] = kWifiSsid;
  requestDoc["wifi_connected"] = true;
  requestDoc["local_sensor_active"] = localSensorReady;
  requestDoc["remote_sensor_active"] = remoteSensorReady;
  requestDoc["remote_sensor_transport_ready"] = remoteTransportReady;
  requestDoc["remote_sensor_model"] = kZkReaderModel;
  requestDoc["remote_sensor_transport"] = kZkReaderTransport;
  requestDoc["remote_enrollment_supported"] = kZkReaderDirectEnrollmentSupported;
  requestDoc["remote_server_match_supported"] = kZkReaderServerSideMatchingSupported;
  requestDoc["remote_power_note"] = kZkReaderPowerNote;
  requestDoc["remote_wiring_note"] = kZkReaderWiringNote;
  requestDoc["owner_account_code"] = kOwnerAccountCode;
  requestDoc["location_name"] = kMachineLocationName;
  requestDoc["location_link"] = kMachineLocationLink;
  requestDoc["firmware_version"] = kFirmwareVersion;

  JsonDocument responseDoc;
  int httpCode = 0;
  if (postJson("/heartbeat", requestDoc, responseDoc, httpCode, true) && httpCode == HTTP_CODE_OK) {
    lastHeartbeatAtMs = millis();
    updateServerReady(true, "heartbeat", httpCode, true);
    return true;
  }

  updateServerReady(false, "heartbeat", httpCode, true);
  return false;
}

String promptDigits(const String &title, const String &subtitle, uint8_t minLength, uint8_t maxLength, bool maskInput) {
  String value = "";
  showMessage(title, subtitle, "# next * back D del");

  while (true) {
    sendHeartbeatIfDue();

    char key = readKeypadKey();
    if (!key) {
      pauseWithRgb(20);
      continue;
    }

    if (key == '*') {
      return "";
    }

    if (key == '#') {
      if (value.length() >= minLength) {
        return value;
      }
      buzz(1, 40, 20);
      continue;
    }

    if (key == 'D') {
      if (value.length() > 0) {
        value.remove(value.length() - 1);
      }
    } else if (key >= '0' && key <= '9' && value.length() < maxLength) {
      value += key;
    }

    lcd.setCursor(0, 3);
    lcd.print("                    ");
    lcd.setCursor(0, 3);
    lcd.print(maskInput ? maskValue(value.length()) : value);
  }
}

String maskValue(size_t length) {
  String masked = "";
  masked.reserve(length);
  for (size_t i = 0; i < length; ++i) {
    masked += '*';
  }
  return masked;
}

String extractMessage(const JsonDocument &doc, const String &fallback) {
  if (doc["message"].is<const char *>()) {
    return doc["message"].as<String>();
  }
  if (doc["error"].is<const char *>()) {
    return doc["error"].as<String>();
  }
  return fallback;
}

bool postJson(const String &path, JsonDocument &requestDoc, JsonDocument &responseDoc, int &httpCode, bool quiet) {
  httpCode = 0;
  setRequestFailure(RequestFailureKind::None);

  if (!ensureWiFi()) {
    setRequestFailure(RequestFailureKind::WiFiOffline);
    updateServerReady(false, "wifi-offline", 0, !quiet);
    if (!quiet) {
      setTemporaryRgbMode(RgbMode::Error, 1200);
      showMessage("WiFi offline", "Cannot reach", "server", "", 1200);
    }
    return false;
  }

  String url = String(kServerBaseUrl) + path;

  String body;
  serializeJson(requestDoc, body);
  bool useSecureTls = kValidateServerCertificate && ensureClockForTls();
  if (!useSecureTls && !kAllowInsecureTlsFallback) {
    setRequestFailure(RequestFailureKind::TlsSetup);
    if (!quiet) {
      setTemporaryRgbMode(RgbMode::Error, 1500);
      showMessage("TLS setup error", "Clock/cert failed", "", "", 1500);
    }
    return false;
  }

  bool attemptedFallback = false;

  while (true) {
    WiFiClientSecure client;
    if (useSecureTls) {
      client.setCACert(kServerCaCert);
    } else {
      client.setInsecure();
    }

    HTTPClient http;
    if (!http.begin(client, url)) {
      if (useSecureTls && kAllowInsecureTlsFallback && !attemptedFallback) {
        attemptedFallback = true;
        useSecureTls = false;
        Serial.printf("HTTPS begin failed for %s. Retrying with insecure local HTTPS.\n", path.c_str());
        continue;
      }

      setRequestFailure(RequestFailureKind::ServerConnection);
      if (!quiet) {
        updateServerReady(false, path.c_str(), 0, true);
        setTemporaryRgbMode(RgbMode::Error, 1200);
        showMessage("HTTPS error", "Bad TLS setup", "", "", 1200);
      }
      return false;
    }

    http.addHeader("Content-Type", "application/json");
    http.setTimeout(8000);

    httpCode = http.POST(body);
    String responseBody = http.getString();
    http.end();

    if (httpCode <= 0) {
      if (useSecureTls && kAllowInsecureTlsFallback && !attemptedFallback) {
        attemptedFallback = true;
        useSecureTls = false;
        Serial.printf("Secure HTTPS failed for %s (code %d). Retrying with insecure local HTTPS.\n",
                      path.c_str(), httpCode);
        continue;
      }

      setRequestFailure(RequestFailureKind::ServerConnection);
      if (!quiet) {
        updateServerReady(false, path.c_str(), httpCode, true);
        setTemporaryRgbMode(RgbMode::Error, 1200);
        showMessage("Server offline", "Check PC server", "", "", 1200);
      }
      return false;
    }

    if (responseBody.length() == 0) {
      updateServerReady(true, path.c_str(), httpCode, false);
      return true;
    }

    DeserializationError error = deserializeJson(responseDoc, responseBody);
    if (error) {
      setRequestFailure(RequestFailureKind::ServerPayload);
      if (!quiet) {
        updateServerReady(false, path.c_str(), httpCode, true);
        setTemporaryRgbMode(RgbMode::Error, 1200);
        showMessage("JSON error", "Bad server data", "", "", 1200);
      }
      return false;
    }

    updateServerReady(true, path.c_str(), httpCode, false);
    return true;
  }
}

void runRegistrationFlow() {
  if (!localSensorReady) {
    showMessage("AS608 required", "Local sensor only", "ZKTeco not ready", "", 1800);
    return;
  }

  if (!ensureServerReady(false)) {
    return;
  }

  String accountSuffix = promptDigits("Account number", "Digits only", 1, 12, false);
  if (accountSuffix.length() == 0) {
    return;
  }

  String phoneNumber = promptDigits("Phone number", "10-15 digits", 10, 15, false);
  if (phoneNumber.length() == 0) {
    return;
  }

  String nidaNumber = promptDigits("NIDA number", "20 digits", 20, 20, false);
  if (nidaNumber.length() == 0) {
    return;
  }

  String pin = promptDigits("Set PIN", "4 digits", 4, 4, true);
  if (pin.length() == 0) {
    return;
  }

  uint16_t slotId = 0;
  String accountCode;
  if (!requestRegistrationSlot(accountSuffix, slotId, accountCode)) {
    return;
  }

  showMessage("Account ready", accountCode, String("Slot ") + String(slotId), "Scan twice", 1400);

  if (!enrollFingerprint(slotId)) {
    return;
  }

  String fingerprintHash;
  String fingerprintSource = "as608";
  if (!downloadStoredTemplateHash(slotId, fingerprintHash)) {
    fingerprintHash = buildFallbackFingerprintHash(slotId, accountCode);
    fingerprintSource = "as608-slot-fallback";
    Serial.printf("[FINGER] Template upload failed for slot %u, using fallback hash.\n", slotId);
  }

  if (!registerUserOnServer(accountSuffix, phoneNumber, nidaNumber, pin, slotId, fingerprintHash, fingerprintSource)) {
    return;
  }

  sendHeartbeatIfDue(true);
  setTemporaryRgbMode(RgbMode::Success, 2200);
  buzz(2, 120, 90);
  showMessage("Register success", accountCode, "Bal TZS 100000", "", 2200);
}

void runPaymentFlow() {
  if (!localSensorReady) {
    showMessage("AS608 required", "Local pay blocked", "", "", 1500);
    return;
  }

  if (!ensureServerReady(false)) {
    return;
  }

  String amountText = promptDigits("Enter amount", "Min 500", 1, 8, false);
  if (amountText.length() == 0) {
    return;
  }

  float amount = amountText.toFloat();
  if (amount < kPaymentMinimum) {
    showMessage("Amount too low", String("Min TZS ") + String(kPaymentMinimum), "", "", 1500);
    return;
  }

  uint16_t slotId = 0;
  if (!matchLocalFingerprint(slotId)) {
    return;
  }

  if (!identifyLocalUser(slotId)) {
    return;
  }

  String pin = promptDigits("Enter PIN", currentAccountCode, 4, 4, true);
  if (pin.length() == 0) {
    return;
  }

  verifyPaymentOnServer(slotId, pin, amount);
}

bool requestRegistrationSlot(const String &accountSuffix, uint16_t &slotId, String &accountCode) {
  JsonDocument requestDoc;
  requestDoc["account_suffix"] = accountSuffix;

  JsonDocument responseDoc;
  int httpCode = 0;
  if (!postJson("/register-slot", requestDoc, responseDoc, httpCode)) {
    return false;
  }

  if (httpCode != HTTP_CODE_OK || !responseDoc["success"].as<bool>()) {
    setTemporaryRgbMode(RgbMode::Error, 1600);
    showMessage("Slot request bad", extractMessage(responseDoc, "Try again"), "", "", 1600);
    return false;
  }

  slotId = responseDoc["local_sensor_slot"].as<uint16_t>();
  accountCode = responseDoc["account_code"].as<String>();
  return true;
}

bool waitForFinger(bool requireFinger, unsigned long timeoutMs) {
  setTemporaryRgbMode(RgbMode::Scan, timeoutMs);
  unsigned long start = millis();
  while (millis() - start < timeoutMs) {
    sendHeartbeatIfDue();

    if (readKeypadKey() == '*') {
      return false;
    }

    uint8_t status = localFinger.getImage();
    if (requireFinger && status == FINGERPRINT_OK) {
      return true;
    }
    if (!requireFinger && status == FINGERPRINT_NOFINGER) {
      return true;
    }
    pauseWithRgb(40);
  }
  return false;
}

bool enrollFingerprint(uint16_t slotId) {
  showMessage("Place finger", "First scan", "* cancel");
  if (!waitForFinger(true, 25000)) {
    setTemporaryRgbMode(RgbMode::Error, 1200);
    showMessage("First scan stop", "Timed out/cancel", "", "", 1200);
    return false;
  }

  if (localFinger.image2Tz(1) != FINGERPRINT_OK) {
    setTemporaryRgbMode(RgbMode::Error, 1500);
    showMessage("First scan bad", "Place finger well", "", "", 1500);
    return false;
  }

  showMessage("Remove finger", "Wait a moment");
  if (!waitForFinger(false, 15000)) {
    setTemporaryRgbMode(RgbMode::Error, 1200);
    showMessage("Remove failed", "Try again", "", "", 1200);
    return false;
  }

  showMessage("Place same finger", "Second scan", "* cancel");
  if (!waitForFinger(true, 25000)) {
    setTemporaryRgbMode(RgbMode::Error, 1200);
    showMessage("Second scan stop", "Timed out/cancel", "", "", 1200);
    return false;
  }

  if (localFinger.image2Tz(2) != FINGERPRINT_OK) {
    setTemporaryRgbMode(RgbMode::Error, 1500);
    showMessage("Second scan bad", "Try again", "", "", 1500);
    return false;
  }

  if (localFinger.createModel() != FINGERPRINT_OK) {
    setTemporaryRgbMode(RgbMode::Error, 1500);
    showMessage("Finger mismatch", "Use same finger", "", "", 1500);
    return false;
  }

  localFinger.deleteModel(slotId);
  if (localFinger.storeModel(slotId) != FINGERPRINT_OK) {
    setTemporaryRgbMode(RgbMode::Error, 1500);
    showMessage("Store failed", "Sensor full/error", "", "", 1500);
    return false;
  }

  return true;
}

bool downloadStoredTemplateHash(uint16_t slotId, String &hashHex) {
  uint8_t status = localFinger.loadModel(slotId);
  if (status != FINGERPRINT_OK) {
    Serial.printf("[FINGER] loadModel(%u) failed: 0x%02X\n", slotId, status);
    return false;
  }

  status = localFinger.getModel();
  if (status != FINGERPRINT_OK) {
    Serial.printf("[FINGER] getModel(%u) failed: 0x%02X\n", slotId, status);
    return false;
  }

  return readTemplatePacketHash(hashHex);
}

bool readTemplatePacketHash(String &hashHex) {
  uint8_t packetSeed[64] = {0};
  Adafruit_Fingerprint_Packet packet(FINGERPRINT_DATAPACKET, sizeof(packetSeed), packetSeed);

  mbedtls_sha256_context shaContext;
  mbedtls_sha256_init(&shaContext);
  mbedtls_sha256_starts_ret(&shaContext, 0);

  while (true) {
    uint8_t status = localFinger.getStructuredPacket(&packet, 2000);
    if (status != FINGERPRINT_OK) {
      Serial.printf("[FINGER] getStructuredPacket failed: 0x%02X\n", status);
      mbedtls_sha256_free(&shaContext);
      return false;
    }

    if (packet.type != FINGERPRINT_DATAPACKET && packet.type != FINGERPRINT_ENDDATAPACKET) {
      Serial.printf("[FINGER] Unexpected packet type: 0x%02X\n", packet.type);
      mbedtls_sha256_free(&shaContext);
      return false;
    }

    size_t payloadSize = packet.length >= 2 ? packet.length - 2 : 0;
    if (payloadSize > 0) {
      mbedtls_sha256_update_ret(&shaContext, packet.data, payloadSize);
    }

    if (packet.type == FINGERPRINT_ENDDATAPACKET) {
      break;
    }
  }

  uint8_t hashBytes[32];
  mbedtls_sha256_finish_ret(&shaContext, hashBytes);
  mbedtls_sha256_free(&shaContext);

  hashHex = sha256ToHex(hashBytes, sizeof(hashBytes));
  return true;
}

String sha256ToHex(const uint8_t *data, size_t len) {
  static const char hexChars[] = "0123456789abcdef";
  String value;
  value.reserve(len * 2);

  for (size_t i = 0; i < len; ++i) {
    value += hexChars[(data[i] >> 4) & 0x0F];
    value += hexChars[data[i] & 0x0F];
  }

  return value;
}

String buildFallbackFingerprintHash(uint16_t slotId, const String &accountCode) {
  String seed = String(kTerminalId) + "|" + accountCode + "|" + String(slotId) + "|as608-slot";
  uint8_t hashBytes[32];
  mbedtls_sha256_context shaContext;
  mbedtls_sha256_init(&shaContext);
  mbedtls_sha256_starts_ret(&shaContext, 0);
  mbedtls_sha256_update_ret(
      &shaContext,
      reinterpret_cast<const unsigned char *>(seed.c_str()),
      seed.length());
  mbedtls_sha256_finish_ret(&shaContext, hashBytes);
  mbedtls_sha256_free(&shaContext);
  return sha256ToHex(hashBytes, sizeof(hashBytes));
}

bool registerUserOnServer(const String &accountSuffix, const String &phoneNumber, const String &nidaNumber, const String &pin, uint16_t slotId, const String &fingerprintHash, const String &fingerprintSource) {
  JsonDocument requestDoc;
  requestDoc["account_suffix"] = accountSuffix;
  requestDoc["phone_number"] = phoneNumber;
  requestDoc["nida_number"] = nidaNumber;
  requestDoc["pin"] = pin;
  requestDoc["fingerprint_hash"] = fingerprintHash;
  requestDoc["local_sensor_slot"] = slotId;
  requestDoc["fingerprint_source"] = fingerprintSource;
  requestDoc["account_type"] = "customer";

  JsonDocument responseDoc;
  int httpCode = 0;
  if (!postJson("/register", requestDoc, responseDoc, httpCode)) {
    return false;
  }

  if (httpCode != HTTP_CODE_OK || !responseDoc["success"].as<bool>()) {
    setTemporaryRgbMode(RgbMode::Error, 1800);
    showMessage("Register rejected", extractMessage(responseDoc, "Try again"), "", "", 1800);
    return false;
  }

  currentAccountCode = responseDoc["user"]["account_code"].as<String>();
  currentUserName = responseDoc["user"]["name"].as<String>();
  return true;
}

bool matchLocalFingerprint(uint16_t &slotId) {
  setTemporaryRgbMode(RgbMode::Scan, 30000);
  showMessage("Payment mode", "Scan customer", "finger on AS608", "* cancel");
  unsigned long start = millis();

  while (millis() - start < 30000) {
    sendHeartbeatIfDue();

    if (readKeypadKey() == '*') {
      return false;
    }

    uint8_t status = localFinger.getImage();
    if (status == FINGERPRINT_NOFINGER) {
      pauseWithRgb(40);
      continue;
    }

    if (status != FINGERPRINT_OK) {
      setTemporaryRgbMode(RgbMode::Error, 900);
      showMessage("Finger read err", "Try again", "", "", 900);
      setTemporaryRgbMode(RgbMode::Scan, 30000);
      showMessage("Payment mode", "Scan customer", "finger on AS608", "* cancel");
      continue;
    }

    status = localFinger.image2Tz();
    if (status != FINGERPRINT_OK) {
      setTemporaryRgbMode(RgbMode::Error, 900);
      showMessage("Bad fingerprint", "Place finger well", "", "", 900);
      setTemporaryRgbMode(RgbMode::Scan, 30000);
      showMessage("Payment mode", "Scan customer", "finger on AS608", "* cancel");
      continue;
    }

    status = localFinger.fingerFastSearch();
    if (status != FINGERPRINT_OK) {
      setTemporaryRgbMode(RgbMode::Error, 1200);
      showMessage("Not recognized", "Register first", "", "", 1200);
      return false;
    }

    if (localFinger.confidence < kFingerprintConfidenceThreshold) {
      setTemporaryRgbMode(RgbMode::Error, 1200);
      showMessage("Low confidence", "Use same finger", "", "", 1200);
      return false;
    }

    slotId = localFinger.fingerID;
    return true;
  }

  setTemporaryRgbMode(RgbMode::Error, 1200);
  showMessage("Scan timeout", "No finger found", "", "", 1200);
  return false;
}

bool identifyLocalUser(uint16_t slotId) {
  JsonDocument requestDoc;
  requestDoc["local_sensor_slot"] = slotId;

  JsonDocument responseDoc;
  int httpCode = 0;
  if (!postJson("/identify", requestDoc, responseDoc, httpCode)) {
    return false;
  }

  if (httpCode != HTTP_CODE_OK || !responseDoc["success"].as<bool>()) {
    setTemporaryRgbMode(RgbMode::Error, 1500);
    showMessage("Lookup failed", extractMessage(responseDoc, "No account"), "", "", 1500);
    return false;
  }

  currentAccountCode = responseDoc["user"]["account_code"].as<String>();
  currentUserName = responseDoc["user"]["name"].as<String>();
  showMessage("User found", currentAccountCode, "Enter PIN now", "", 1000);
  return true;
}

bool verifyPaymentOnServer(uint16_t slotId, const String &pin, float amount) {
  JsonDocument requestDoc;
  requestDoc["local_sensor_slot"] = slotId;
  requestDoc["pin"] = pin;
  requestDoc["amount"] = amount;
  requestDoc["terminal_id"] = kTerminalId;

  JsonDocument responseDoc;
  int httpCode = 0;
  if (!postJson("/verify", requestDoc, responseDoc, httpCode, true)) {
    setTemporaryRgbMode(RgbMode::Error, 2000);
    buzz(1, 220, 40);
    if (lastRequestFailureKind == RequestFailureKind::WiFiOffline) {
      showMessage("WiFi offline", "Payment not sent", "Retry after sync", "", 2000);
    } else {
      showMessage("Server error", "Payment not sent", "Retry payment", "", 2000);
    }
    currentAccountCode = "";
    currentUserName = "";
    return false;
  }

  if (httpCode >= 500) {
    setTemporaryRgbMode(RgbMode::Error, 2000);
    buzz(1, 220, 40);
    showMessage("Server error", extractMessage(responseDoc, "Retry payment"), "", "", 2000);
    currentAccountCode = "";
    currentUserName = "";
    return false;
  }

  if (httpCode != HTTP_CODE_OK) {
    setTemporaryRgbMode(RgbMode::Error, 1800);
    showMessage("Payment failed", extractMessage(responseDoc, "Server error"), "", "", 1800);
    currentAccountCode = "";
    currentUserName = "";
    return false;
  }

  bool success = responseDoc["success"].as<bool>();
  String message = extractMessage(responseDoc, success ? "Approved" : "Rejected");
  float balance = responseDoc["balance"].as<float>();

  if (success) {
    setTemporaryRgbMode(RgbMode::Success, 2600);
    buzz(1, 180, 40);
    showMessage("Amount paid", String("TZS ") + String(amount, 2), message, String("Bal ") + String(balance, 2), 2600);
    sendHeartbeatIfDue(true);
  } else {
    setTemporaryRgbMode(RgbMode::Error, 2200);
    buzz(1, 300, 40);
    showMessage("Payment rejected", message, String("Bal ") + String(balance, 2), "", 2200);
  }

  currentAccountCode = "";
  currentUserName = "";
  return success;
}
