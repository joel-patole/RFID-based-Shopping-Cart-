#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <MFRC522v2.h>
#include <MFRC522DriverSPI.h>
#include <MFRC522DriverPinSimple.h>
#include <MFRC522Debug.h>

// ─── CHANGE THESE ────────────────────────────────────────────────────────────
const char* ssid      = "ESPTEST";
const char* password  = "12345678";
const char* serverUrl = "http://10.136.140.78:5001/scan"; // Your Mac IP : port 5001
// ─────────────────────────────────────────────────────────────────────────────

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
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi Connected!");
    Serial.print("ESP8266 IP : ");
    Serial.println(WiFi.localIP());
    Serial.print("Gateway IP : ");
    Serial.println(WiFi.gatewayIP());
    Serial.print("MAC Address: ");
    Serial.println(WiFi.macAddress());
    Serial.println("=================================");
  } else {
    Serial.println("WiFi FAILED — check SSID/password or signal.");
    Serial.println("Restarting in 5 seconds...");
    delay(5000);
    ESP.restart();
  }
}

void sendPostRequest(String uid, String mac) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected — skipping POST");
    return;
  }

  WiFiClient client;
  HTTPClient http;

  http.begin(client, serverUrl);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);

  String payload = "{\"item_id\":\"" + uid + "\",\"cart_id\":\"" + mac + "\"}";

  Serial.println("Sending POST to: " + String(serverUrl));
  Serial.println("Payload: " + payload);

  int code = http.POST(payload);

  if (code > 0) {
    Serial.print("SUCCESS  HTTP ");
    Serial.println(code);
    Serial.println("Response: " + http.getString());
  } else {
    Serial.print("FAILED   Error: ");
    Serial.println(code);
    Serial.println("Reason : " + HTTPClient::errorToString(code));
    Serial.println("Check: PC IP correct? Flask running? Same network?");
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println();
  Serial.println("ESP8266 RFID Scanner Starting...");
  connectWiFi();
  mfrc522.PCD_Init();
  Serial.println();
  Serial.println("RFID Ready — Scan a card!");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost — reconnecting...");
    connectWiFi();
  }

  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial())   return;

  String uid = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(mfrc522.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  String mac = WiFi.macAddress();

  Serial.println();
  Serial.println("Card Detected!");
  Serial.println("UID: " + uid);

  sendPostRequest(uid, mac);
  delay(2000);
}
