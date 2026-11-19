# 🛒 Smart RFID Shopping Cart & Checkout System

A full-stack autonomous RFID shopping cart and retail checkout system. When an item with an RFID tag is placed in the cart, it is scanned and **Registered (Added to Cart)**. When removed from the cart and scanned again, it is **Unregistered (Removed from Cart)** with live price deduction, tax calculation, and digital thermal receipts.

---

## ✨ Features

- **Autonomous Cart Item Tracking**:
  - **First Scan**: Product is **Registered** (Added to Cart) with sound chime, price added to subtotal.
  - **Second Scan**: Product is **Unregistered** (Removed from Cart) with removal alert, price deducted.
  - **Subsequent Scans**: Seamlessly toggles back and forth.
- **Rich Modern UI**:
  - Dark glassmorphic aesthetic with animated glowing emerald (`#10b981`) and coral (`#f43f5e`) alert states.
  - Supermarket scanner audio beeps generated directly with Web Audio API (no external sound files required).
  - Live metric counters for Cart Total ($), Active Cart Items, Unregistered items, and Total Scans.
- **Product Catalog Management**:
  - Pre-seeded with realistic grocery & retail items (Milk, Bread, Apples, Coffee, Chocolate, etc.).
  - Auto-assigns any uncataloged RFID tag UID to a new product profile with customizable name, price, and category.
  - In-browser modal to add, edit, or remove products mapped to RFID UIDs.
- **Smart Checkout & Digital Receipts**:
  - Complete checkout flow with payment options (Card, Apple Pay, UPI, Cash).
  - Thermal paper receipt view with barcode, itemized breakdown, tax calculation, and printable invoice.
- **Built-in RFID Tag Simulator**:
  - Test the entire add/remove shopping cart cycle directly in your browser with 1-click test chips, even without the ESP8266 plugged in.
- **Zero Arduino Code Changes Required**:
  - 100% compatible with existing ESP8266 sketch sending `{"item_id": "<UID>", "cart_id": "<MAC>"}` to `/scan`.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Server
```bash
python3 app.py
```

### 3. Open the Dashboard
Navigate to:
```
http://localhost:5001
```

---

## 🛠️ ESP8266 Arduino Setup

Your Arduino code in [rfid_scanner.ino](file:///Users/joel/Downloads/RFID-based-attendance-server-main/rfid_scanner.ino) is 100% compatible. Simply update your WiFi credentials and your computer's local IP address:

```cpp
// ─── CHANGE THESE IN rfid_scanner.ino ──────────────────────────────
const char* ssid      = "YOUR_ROUTER_WIFI";            // Same WiFi network your computer uses
const char* password  = "YOUR_WIFI_PASSWORD";
const char* serverUrl = "http://YOUR_COMPUTER_IP:5001/scan"; // Port 5001
// ───────────────────────────────────────────────────────────────────
```

### Finding your computer's local IP:
- **macOS / Linux**: Run `ifconfig` or `ip a` (look for `en0` or `wlan0` `inet 192.168.x.x`).
- **Windows**: Run `ipconfig` in Command Prompt (look for `IPv4 Address`).

> [!NOTE]
> Ensure your computer and the ESP8266 are connected to the same Wi-Fi router or mobile hotspot.

---

## 📦 Database & Storage

- **MongoDB (Recommended)**: Automatically connects to `mongodb://localhost:27017/` (or via `MONGO_URI` environment variable).
- **Persistent JSON Fallback**: If MongoDB is not running, the server automatically persists product mappings to `products.json` and receipts to `receipts.json` with in-memory caching.
