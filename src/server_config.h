#pragma once

#include <IPAddress.h>

static const char *kWifiSsid = "simon";
static const char *kWifiPassword = "SIMON1234";
static const char *kTerminalId = "terminal-arusha-01";
static const char *kMachineName = "ATC W41K3RJ BIOMETRIX";
static const char *kMachineLocationName = "ATC POINT";
static const char *kMachineLocationLink =
    "https://maps.google.com/?q=ATC+Arusha+Technical+College+Irrigation+Point";
static const char *kOwnerAccountCode = "W41K3RJ000000";
static const char *kFirmwareVersion = "2026.06.09";

static constexpr bool kUseStaticIp = true;
static const IPAddress kDeviceIp(192, 168, 43, 80);
static const IPAddress kGateway(192, 168, 43, 15);
static const IPAddress kSubnet(255, 255, 255, 0);
static const IPAddress kDns1(8, 8, 8, 8);
static const IPAddress kDns2(1, 1, 1, 1);
static constexpr bool kValidateServerCertificate = true;
static constexpr bool kAllowInsecureTlsFallback = true;
static constexpr unsigned long kTlsClockSyncTimeoutMs = 4000;
static constexpr unsigned long kTlsMinimumUnixTime = 1704067200UL;  // 2024-01-01 UTC
static const char *kNtpServer1 = "pool.ntp.org";
static const char *kNtpServer2 = "time.google.com";
static const char *kNtpServer3 = "time.cloudflare.com";

static constexpr uint16_t kPaymentMinimum = 500;
static constexpr uint8_t kLocalFingerprintCapacity = 127;
static constexpr uint8_t kFingerprintConfidenceThreshold = 50;
static constexpr unsigned long kHeartbeatIntervalMs = 20000;

static constexpr uint32_t kLocalFingerprintBaud = 57600;
static constexpr uint8_t kLocalFingerprintRxPin = 16;
static constexpr uint8_t kLocalFingerprintTxPin = 17;

// LCD I2C pins.
static constexpr int kLcdSdaPin = 41;
static constexpr int kLcdSclPin = 42;
static constexpr uint8_t kLcdI2cAddress = 0x27;
static constexpr uint8_t kLcdColumns = 20;
static constexpr uint8_t kLcdRows = 4;

// Matrix keypad mapping for the 8-pin connector shown in the user's diagram:
// connector pins 8,7,6,5 are rows 1,2,3,4 and pins 4,3,2,1 are cols 1,2,3,4.
// These values assume ESP32 GPIO 1..8 were wired to keypad connector pins 1..8.
static constexpr uint8_t kKeypadRow1Pin = 8;
static constexpr uint8_t kKeypadRow2Pin = 7;
static constexpr uint8_t kKeypadRow3Pin = 6;
static constexpr uint8_t kKeypadRow4Pin = 5;
static constexpr uint8_t kKeypadCol1Pin = 4;
static constexpr uint8_t kKeypadCol2Pin = 3;
static constexpr uint8_t kKeypadCol3Pin = 2;
static constexpr uint8_t kKeypadCol4Pin = 1;
static constexpr bool kLogKeypadToSerial = true;

static constexpr bool kEnableRgbStatusLed = true;
static constexpr uint8_t kRgbStatusBrightness = 48;
static constexpr unsigned long kRgbStatusStepMs = 35;

static constexpr uint8_t kLedPowerPin = 9;
static constexpr uint8_t kLedAs608Pin = 10;
static constexpr uint8_t kLedZkPin = 11;
static constexpr uint8_t kLedWifiPin = 12;
static constexpr uint8_t kBuzzerPin = 13;

static constexpr uint8_t kZkRs485RxPin = 14;
static constexpr uint8_t kZkRs485TxPin = 15;
static const char *kZkReaderModel = "ZKTeco F12 RS485 Slave Reader";
static const char *kZkReaderPartCode = "CGIN212460898";
static const char *kZkReaderPowerNote = "12VDC external supply required";
static const char *kZkReaderTransport = "RS485";
static const char *kZkReaderWiringNote =
    "F12 485+ -> RS485 A+, 485- -> RS485 B-, GND -> converter GND, "
    "converter TXD/RXD -> ESP32 RX/TX, reader uses external 12V DC";
static constexpr bool kZkReaderPowerPresent = true;
static constexpr bool kZkReaderTransportConfigured = true;
static constexpr bool kZkReaderDirectEnrollmentSupported = false;
static constexpr bool kZkReaderServerSideMatchingSupported = false;
