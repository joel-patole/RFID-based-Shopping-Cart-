#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <MFRC522v2.h>
#include <MFRC522DriverSPI.h>
#include <MFRC522DriverPinSimple.h>
#include <MFRC522Debug.h>

const char* ssid      = "ESPTEST";
const char* password  = "12345678";
const char* serverUrl = "http://10.136.140.78:5001/scan"; // Your Mac IP : port 5001

MFRC522DriverPinSimple ss_pin(15);
MFRC522DriverSPI driver{ss_pin};
MFRC522 mfrc522{driver};

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(1000);
  WiFi.begin(ssid, password);

  Serial.println("=================================");
  Serial.println("Connecting to WiFi...");
  Serial.print("SSID: ");
  Serial.println(ssid);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi Connected!");
    Serial.print("ESP8266 IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("MAC: ");
    Serial.println(WiFi.macAddress());
    Serial.println("=================================");
  } else {
    Serial.println("WiFi Failed! Restarting...");
    delay(3000);
    ESP.restart();
  }
}

void sendPostRequest(String uid, String mac) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected");
    return;
  }

  WiFiClient client;
  HTTPClient http;

  http.begin(client, serverUrl);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);

  String jsonPayload = "{\"item_id\":\"" + uid + "\",\"cart_id\":\"" + mac + "\"}";

  Serial.println("Sending POST...");
  Serial.println(jsonPayload);

  int httpResponseCode = http.POST(jsonPayload);

  if (httpResponseCode > 0) {
    Serial.print("SUCCESS! Code: ");
    Serial.println(httpResponseCode);
    Serial.println(http.getString());
  } else {
    Serial.print("FAILED! Error: ");
    Serial.println(httpResponseCode);
    Serial.println(HTTPClient::errorToString(httpResponseCode));
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("ESP8266 Starting...");
  connectWiFi();
  mfrc522.PCD_Init();
  Serial.println("RFID Ready - Scan Card");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi Lost! Reconnecting...");
    connectWiFi();
  }

  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  String uidStr = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(mfrc522.uid.uidByte[i], HEX);
  }
  uidStr.toUpperCase();

  String macAddr = WiFi.macAddress();

  Serial.println();
  Serial.println("Card Detected!");
  Serial.print("UID: ");
  Serial.println(uidStr);

  sendPostRequest(uidStr, macAddr);
  delay(2000);
}