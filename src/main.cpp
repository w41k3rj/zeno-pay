#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_Fingerprint.h>
#include <Keypad.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

//==============================---------------LCD Setup-----------------=====================================

LiquidCrystal_I2C lcd(0x27, 20, 4);//=================kwa lcd ya 20 x 4======================================

//==============================------Fingerprint Sensor Setup==========HardwareSerial========================

#define FINGERPRINT_RX 16         //=======================ESP32 RX pin (connects to sensor TX)===============

#define FINGERPRINT_TX 17         //=======================ESP32 TX pin (connects to sensor RX)===============

HardwareSerial fingerSerial(1); //--------------------------Using UART1--------------------------------------

Adafruit_Fingerprint finger = Adafruit_Fingerprint(&fingerSerial);

//================================================Keypad Setup (4x4)===============================================

const byte ROWS = 4; // Four rows
const byte COLS = 4; // Four columns
char keys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};

//================================// Adjust these pin numbers according to your ESP32-S3 wiring=====================
byte rowPins[ROWS] = {1, 2, 3, 4}; // Connect to the row pinouts of the keypad
byte colPins[COLS] = {5, 6, 7, 8}; // Connect to the column pinouts of the keypad

Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

//==============================================WiFi Credentials iot net  connection ========================

const char* ssid = "w41k3rj";
const char* password = "12345678";

//=============================================Server Details runing port====================================

const char* serverUrl = "https://your-server.com/api";

//============================================= Variables logic on shop com=================================

float currentAmount = 0.0;
String currentUserID = "";
bool waitingForFingerprint = false;
bool waitingForPIN = false;
String enteredPIN = "";

//=============================================Function protocal kwenye user acct checking=================

void displayMainScreen();
void enterAmountMode();
void checkFingerprint();
bool getUserDetails(uint16_t userID);
void verifyPIN();

void setup() {
  Serial.begin(115200);
  
  //======================================= LCD seting za kioo and initializing ===========================

  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Payment System");
  lcd.setCursor(0, 1);
  lcd.print("Initializing...");
  
  //========================================Initialize Fingerprint Sensor=================================

  fingerSerial.begin(57600, SERIAL_8N1, FINGERPRINT_RX, FINGERPRINT_TX);
  finger.begin(57600);
  
  if (finger.verifyPassword()) {
    lcd.setCursor(0, 2);
    lcd.print("Fingerprint OK");
  } else {
    lcd.setCursor(0, 2);
    lcd.print("Fingerprint ERR");
    while (1) { delay(1); }
  }
  
  //========================================= Connect to WiFi check pin and connect ====================

  WiFi.begin(ssid, password);
  lcd.setCursor(0, 3);
  lcd.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    lcd.print(".");
  }
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("WiFi Connected");
  lcd.setCursor(0, 1);
  lcd.print("IP: ");
  lcd.print(WiFi.localIP());
  delay(2000);
  
  lcd.clear();
  displayMainScreen();
}

void loop() {
  char key = keypad.getKey();
  
  //============================Seller enters amount mode dukani muuzaji ataanza comvasation kwa kuweka ammount======

  if (key == '#') {
    enterAmountMode();
  }
  
  //=====================================Fingerprint verification====================================================

  if (waitingForFingerprint) {
    checkFingerprint();
  }
  
  //==================================== PIN entry  checking pin  if mech continue==================================

  if (waitingForPIN && key) {
    if (key == '*') {
      //================================ Cancel PIN entry if not true  cancel=======================================

      waitingForPIN = false;
      displayMainScreen();
    } else if (key == '#') {
      //================================ Submit PIN=================================================================

      verifyPIN();
    } else if (key >= '0' && key <= '9') {
      //============================== Add digit to PIN (ignore A, B, C, D keys but #ok *delete)===================================

      if (enteredPIN.length() < 4) {
        enteredPIN += key;
        lcd.setCursor(10 + enteredPIN.length(), 2);
        lcd.print("*");
      }
    }
  }
}

void displayMainScreen() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Payment System");
  lcd.setCursor(0, 1);
  lcd.print("Press # to start");
  lcd.setCursor(0, 2);
  lcd.print("Amount: ");
  lcd.print(currentAmount, 2);
}

void enterAmountMode() {
  currentAmount = 0.0;
  String amountStr = "";
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Enter Amount:");
  lcd.setCursor(0, 1);
  lcd.print("(Press # to confirm)");
  lcd.setCursor(0, 2);
  lcd.print("                "); //EEneo wazi jaza kiasi Clear amount display area
  
  while (true) {
    char key = keypad.getKey();
    if (key) {
      if (key == '#') {
        if (amountStr.length() > 0) {
          currentAmount = amountStr.toFloat();
          lcd.clear();
          lcd.setCursor(0, 0);
          lcd.print("Amount: ");
          lcd.print(currentAmount, 2);
          lcd.setCursor(0, 1);
          lcd.print("Scan fingerprint");
          waitingForFingerprint = true;
          return;
        }
      } else if (key >= '0' && key <= '9') {
        amountStr += key;
        lcd.setCursor(0, 2);
        lcd.print(amountStr);
      } else if (key == '*') {
        //==============================================Cancelkutoka kwa user amount============================
        displayMainScreen();
        return;
      }
    }
  }
}

void checkFingerprint() {
  uint8_t p = finger.getImage();
  if (p != FINGERPRINT_OK) return;
  
  p = finger.image2Tz();
  if (p != FINGERPRINT_OK) return;
  
  p = finger.fingerFastSearch();
  if (p == FINGERPRINT_OK) {
    uint16_t fid = finger.fingerID;
    float confidence = finger.confidence;
    
    if (confidence > 50) { //-------------------------------------- Confidence threshold------------------------------
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("User ID: ");
      lcd.print(fid);
      lcd.setCursor(0, 1);
      lcd.print("Enter PIN:");
      lcd.setCursor(10, 2);
      lcd.print("____"); // Placeholder for PIN
      
      //================================================= Get user details from server===============================
      
      if (getUserDetails(fid)) {
        waitingForFingerprint = false;
        waitingForPIN = true;
        enteredPIN = "";
      } else {
        lcd.setCursor(0, 3);
        lcd.print("User not found");
        delay(2000);
        displayMainScreen();
      }
    } else {
      lcd.setCursor(0, 3);
      lcd.print("Low confidence");
      delay(1000);
      lcd.setCursor(0, 1);
      lcd.print("Scan fingerprint");
    }
  } else {
    lcd.setCursor(0, 3);
    lcd.print("Not recognized");
    delay(1000);
    lcd.setCursor(0, 1);
    lcd.print("Scan fingerprint");
  }
}

bool getUserDetails(uint16_t userID) {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(1000);
    if (WiFi.status() != WL_CONNECTED) return false;
  }
  
  HTTPClient http;
  String url = String(serverUrl) + "/user?id=" + String(userID);
  
  http.begin(url);
  int httpCode = http.GET();
  
  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    JsonDocument doc;
    deserializeJson(doc, payload);
    
    currentUserID = doc["id"].as<String>();
    http.end();
    return true;
  }
  
  http.end();
  return false;
}

void verifyPIN() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(1000);
    if (WiFi.status() != WL_CONNECTED) {
      lcd.setCursor(0, 3);
      lcd.print("Network error");
      delay(2000);
      displayMainScreen();
      return;
    }
  }
  
  HTTPClient http;
  String url = String(serverUrl) + "/verify";
  
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  
  JsonDocument doc;
  doc["user_id"] = currentUserID;
  doc["pin"] = enteredPIN;
  doc["amount"] = currentAmount;
  
  String requestBody;
  serializeJson(doc, requestBody);
  
  int httpCode = http.POST(requestBody);
  
  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    JsonDocument responseDoc;
    deserializeJson(responseDoc, payload);
    
    bool success = responseDoc["success"];
    String message = responseDoc["message"].as<String>();
    float newBalance = responseDoc["balance"];
    
    lcd.clear();
    lcd.setCursor(0, 0);
    if (success) {
      lcd.print("Payment Success!");
      lcd.setCursor(0, 1);
      lcd.print("New Balance: ");
      lcd.print(newBalance, 2);
    } else {
      lcd.print("Payment Failed");
      lcd.setCursor(0, 1);
      lcd.print(message);
    }
    
    delay(3000);
  } else {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Server Error");
    lcd.setCursor(0, 1);
    lcd.print("Try again later");
    delay(2000);
  }
  
  http.end();
  waitingForPIN = false;
  displayMainScreen();
}