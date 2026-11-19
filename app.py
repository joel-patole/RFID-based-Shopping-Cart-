import os
import json
import uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, make_response
from pymongo import MongoClient, ASCENDING, DESCENDING

app = Flask(__name__)

# Base Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_FILE = os.path.join(BASE_DIR, 'products.json')
RECEIPTS_FILE = os.path.join(BASE_DIR, 'receipts.json')

# Database Configuration
MONGO_URI     = os.getenv('MONGO_URI',     'mongodb://localhost:27017/')
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'rfid_shopping_cart')

mongo_client = items_col = scans_col = products_col = receipts_col = None
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2500)
    mongo_client.admin.command('ping')
    _db = mongo_client[MONGO_DB_NAME]
    items_col = _db['items']
    scans_col = _db['scans']
    products_col = _db['products']
    receipts_col = _db['receipts']
    items_col.create_index([('item_id', ASCENDING)], unique=True)
    scans_col.create_index([('timestamp_iso', DESCENDING)])
    print(f"[MongoDB] Connected -> {MONGO_URI}  db={MONGO_DB_NAME}")
except Exception as err:
    print(f"[MongoDB] Not connected ({err}) -- using persistent JSON / in-memory fallback")
    mongo_client = items_col = scans_col = products_col = receipts_col = None

# Fallback in-memory storage
_mem_items = {}     # item_id -> item state
_mem_log   = []     # list of scan events
_mem_products = {} # item_id -> product info
_mem_receipts = [] # list of past receipts
_last_cart_id = "SMART-CART-01"

# Scan Mode Settings
_settings = {
    "auto_generate_uid": True,  # When True, each scan of the physical card creates a new UID with a real Indian product
    "scan_action": "add",        # "add" or "remove"
    "currency": "₹",
    "currency_code": "INR"
}
_product_cycle_index = 0

# Default starter catalog in Indian Rupees (INR ₹)
DEFAULT_PRODUCTS = {
    "4344E819": {
        "item_id": "4344E819",
        "name": "Amul Taaza Fresh Milk 1L",
        "price": 54.0,
        "category": "Dairy",
        "icon": "🥛",
        "description": "Pasteurized homogenized toned milk"
    },
    "B3BDC50E": {
        "item_id": "B3BDC50E",
        "name": "Britannia 100% Whole Wheat Bread",
        "price": 45.0,
        "category": "Bakery",
        "icon": "🍞",
        "description": "Zero maida high fiber whole wheat bread 400g"
    },
    "43A7F29B": {
        "item_id": "43A7F29B",
        "name": "Tata Tea Gold (250g)",
        "price": 140.0,
        "category": "Beverages",
        "icon": "☕",
        "description": "Assam tea blend with aromatic long leaves"
    },
    "E2806894": {
        "item_id": "E2806894",
        "name": "Cadbury Dairy Milk Silk (60g)",
        "price": 85.0,
        "category": "Snacks",
        "icon": "🍫",
        "description": "Smooth and creamy pure milk chocolate"
    },
    "B1C2D3E4": {
        "item_id": "B1C2D3E4",
        "name": "Fresh Royal Gala Apples (1kg)",
        "price": 160.0,
        "category": "Produce",
        "icon": "🍎",
        "description": "Crisp sweet mountain orchard apples"
    },
    "90A1B2C3": {
        "item_id": "90A1B2C3",
        "name": "Maggi 2-Minute Masala Noodles (Pack of 4)",
        "price": 56.0,
        "category": "Pantry",
        "icon": "🍜",
        "description": "Classic Indian spice blend instant wheat noodles"
    },
    "F5E4D3C2": {
        "item_id": "F5E4D3C2",
        "name": "Lay's India's Magic Masala Chips",
        "price": 20.0,
        "category": "Snacks",
        "icon": "🥔",
        "description": "Crunchy ridge-cut spiced potato chips"
    },
    "A0B1C2D3": {
        "item_id": "A0B1C2D3",
        "name": "Fortune Sunlite Refined Sunflower Oil (1L)",
        "price": 135.0,
        "category": "Pantry",
        "icon": "🌻",
        "description": "Light, healthy and cholesterol-friendly cooking oil"
    },
    "D4E5F6A1": {
        "item_id": "D4E5F6A1",
        "name": "Aashirvaad Superior MP Shudh Chakki Atta (5kg)",
        "price": 245.0,
        "category": "Pantry",
        "icon": "🌾",
        "description": "100% whole wheat grain chakki ground flour"
    },
    "718293A4": {
        "item_id": "718293A4",
        "name": "Tata Salt Vacuum Evaporated Iodized (1kg)",
        "price": 28.0,
        "category": "Pantry",
        "icon": "🧂",
        "description": "Desh Ka Namak purest iodized cooking salt"
    },
    "99AA88BB": {
        "item_id": "99AA88BB",
        "name": "Nescafe Classic Instant Coffee (50g)",
        "price": 165.0,
        "category": "Beverages",
        "icon": "☕",
        "description": "100% pure roasted robusta coffee beans"
    },
    "88223344": {
        "item_id": "88223344",
        "name": "Dettol Original Liquid Handwash (200ml)",
        "price": 99.0,
        "category": "Personal Care",
        "icon": "🧴",
        "description": "Antibacterial ph-balanced hand soap refill pack"
    }
}

def _json_serial(obj):
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    return str(obj)

def load_products_from_disk():
    global _mem_products
    if os.path.exists(PRODUCTS_FILE):
        try:
            with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    _mem_products = json.loads(content)
                    return
        except Exception as e:
            print(f"[Products] Error reading {PRODUCTS_FILE} ({e}) -- resetting to default")
    _mem_products = dict(DEFAULT_PRODUCTS)
    save_products_to_disk()

def save_products_to_disk():
    try:
        tmp_file = PRODUCTS_FILE + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(_mem_products, f, indent=2, ensure_ascii=False, default=_json_serial)
        os.replace(tmp_file, PRODUCTS_FILE)
    except Exception as e:
        print(f"[Products] Error saving {PRODUCTS_FILE}: {e}")

load_products_from_disk()

def get_product(item_id):
    """Retrieve product details for a given item_id, creating a default if unknown."""
    global _mem_products
    item_id = str(item_id).upper().strip()
    if products_col is not None:
        try:
            p = products_col.find_one({"item_id": item_id}, {"_id": 0})
            if p:
                return p
        except Exception:
            pass

    if item_id in _mem_products:
        return _mem_products[item_id]

    # Assign smart Indian product for uncataloged scanned tags
    short_id = item_id[-4:] if len(item_id) >= 4 else item_id
    new_product = {
        "item_id": item_id,
        "name": f"Indian Grocery Item #{short_id}",
        "price": 50.0,
        "category": "General",
        "icon": "🏷️",
        "description": f"Auto-registered RFID Tag {item_id}"
    }
    _mem_products[item_id] = new_product
    save_products_to_disk()

    if products_col is not None:
        try:
            products_col.update_one({"item_id": item_id}, {"$set": new_product}, upsert=True)
        except Exception:
            pass
    return new_product

def get_next_catalog_product():
    """Pick the next authentic Indian grocery product from the catalog for dynamic UID mode."""
    global _product_cycle_index
    pool = list(_mem_products.values())
    # Filter to real named items (avoid repeating generic placeholders)
    named_pool = [p for p in pool if not p.get("name", "").startswith("Smart Retail Item") and not p.get("name", "").startswith("Indian Grocery Item")]
    if not named_pool:
        named_pool = list(DEFAULT_PRODUCTS.values())
    
    prod = named_pool[_product_cycle_index % len(named_pool)]
    _product_cycle_index += 1
    return dict(prod)

def load_receipts_from_disk():
    global _mem_receipts
    if os.path.exists(RECEIPTS_FILE):
        try:
            with open(RECEIPTS_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    _mem_receipts = json.loads(content)
                    return
        except Exception as e:
            print(f"[Receipts] Error reading {RECEIPTS_FILE} ({e}) -- resetting to clean state")
            _mem_receipts = []
            try:
                with open(RECEIPTS_FILE, 'w', encoding='utf-8') as f:
                    f.write("[]")
            except Exception:
                pass
            return
    _mem_receipts = []

def save_receipt_to_disk(rcpt):
    global _mem_receipts
    try:
        clean_rcpt = json.loads(json.dumps(rcpt, default=_json_serial))
        _mem_receipts.insert(0, clean_rcpt)
        if len(_mem_receipts) > 100:
            _mem_receipts.pop()
        tmp_file = RECEIPTS_FILE + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(_mem_receipts, f, indent=2, ensure_ascii=False, default=_json_serial)
        os.replace(tmp_file, RECEIPTS_FILE)
    except Exception as e:
        print(f"[Receipts] Error saving {RECEIPTS_FILE}: {e}")

load_receipts_from_disk()

def calculate_active_cart():
    """Calculate active items in cart and total price."""
    active_items = []
    if items_col is not None:
        try:
            docs = list(items_col.find({"status": "registered"}, {"_id": 0}))
            active_items = docs
        except Exception:
            active_items = [v for v in _mem_items.values() if v.get("status") == "registered"]
    else:
        active_items = [v for v in _mem_items.values() if v.get("status") == "registered"]

    subtotal = sum(float(item.get("product", {}).get("price", 0.0)) for item in active_items)
    subtotal = round(subtotal, 2)
    tax = round(subtotal * 0.05, 2)
    total = round(subtotal + tax, 2)
    return {
        "items": active_items,
        "count": len(active_items),
        "subtotal": subtotal,
        "tax": tax,
        "total": total
    }

@app.after_request
def add_no_cache_headers(resp):
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@app.route('/')
def index():
    return render_template('index.html')

def _save_item_and_log(item_id, item_record, log_record):
    if items_col is not None and scans_col is not None:
        try:
            items_col.update_one({"item_id": item_id}, {"$set": item_record}, upsert=True)
            scans_col.insert_one(dict(log_record))
        except Exception as e:
            print(f"[MongoDB save error] {e}")
            _mem_items[item_id] = item_record
            _mem_log.insert(0, log_record)
            if len(_mem_log) > 200:
                _mem_log.pop()
    else:
        _mem_items[item_id] = item_record
        _mem_log.insert(0, log_record)
        if len(_mem_log) > 200:
            _mem_log.pop()

@app.route('/settings', methods=['GET', 'POST'])
def handle_settings():
    global _settings
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        if "auto_generate_uid" in data:
            _settings["auto_generate_uid"] = bool(data["auto_generate_uid"])
        if "scan_action" in data and data["scan_action"] in ["add", "remove"]:
            _settings["scan_action"] = data["scan_action"]
        return jsonify({"status": "ok", "settings": _settings})
    return jsonify(_settings)

@app.route('/remove-item/<item_id>', methods=['POST'])
def remove_specific_item(item_id):
    """Remove a specific item from the active cart by its UID."""
    item_id = str(item_id).upper().strip()
    now_utc = datetime.now(timezone.utc)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing = None
    if items_col is not None:
        try:
            existing = items_col.find_one({"item_id": item_id})
        except Exception:
            pass
    if not existing and item_id in _mem_items:
        existing = _mem_items[item_id]

    product = (existing and existing.get("product")) or get_product(item_id)
    scan_count = (existing and existing.get("scan_count", 1)) + 1 if existing else 1
    cart_id = (existing and existing.get("cart_id")) or _last_cart_id

    item_record = {
        "item_id": item_id,
        "cart_id": cart_id,
        "status": "unregistered",
        "action": "removed",
        "product": product,
        "timestamp": ts,
        "scan_count": scan_count,
        "last_scanned_at": now_utc
    }

    message = f"Product '{product['name']}' (₹{product['price']:.2f}) REMOVED from cart"
    log_record = {
        "item_id": item_id,
        "cart_id": cart_id,
        "event": "unregistered",
        "action": "removed",
        "product": product,
        "message": message,
        "timestamp": ts,
        "timestamp_iso": now_utc,
        "scan_count": scan_count
    }

    _save_item_and_log(item_id, item_record, log_record)
    cart_summary = calculate_active_cart()
    print(f"[{ts}] REMOVED: {product['name']} (₹{product['price']:.2f}) | UID: {item_id} | Total: ₹{cart_summary['total']:.2f}")

    return jsonify({
        "status": "ok",
        "item_id": item_id,
        "action": "removed",
        "product": product,
        "message": message,
        "cart_summary": {
            "active_count": cart_summary["count"],
            "subtotal": cart_summary["subtotal"],
            "tax": cart_summary["tax"],
            "total": cart_summary["total"]
        }
    })

@app.route('/scan', methods=['POST'])
def scan():
    """
    Handle RFID scan from ESP8266 Arduino:
    Payload: {"item_id": "<UID>", "cart_id": "<MAC>"}
    Supports Auto-Generate UID mode (giving each scan a real product & new UID)
    as well as strict toggle mode.
    """
    global _last_cart_id
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "No JSON payload"}), 400

    item_id = str(data.get('item_id', '')).upper().strip()
    cart_id = str(data.get('cart_id', 'CART-01')).upper().strip()
    if not item_id:
        return jsonify({"error": "item_id required"}), 400

    _last_cart_id = cart_id
    now_utc = datetime.now(timezone.utc)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Mode 1: Auto-generate UID mode (User requested: every scan of card gives new UID + real product + specific ₹ amount)
    if _settings.get("auto_generate_uid", True):
        scan_action = _settings.get("scan_action", "add")

        if scan_action == "remove":
            # Remove latest active item from cart
            active_items = calculate_active_cart()["items"]
            if active_items:
                target = active_items[-1]
                remove_id = target["item_id"]
                product = target.get("product") or get_product(remove_id)
                scan_count = target.get("scan_count", 1) + 1

                item_record = {
                    "item_id": remove_id,
                    "cart_id": cart_id,
                    "status": "unregistered",
                    "action": "removed",
                    "product": product,
                    "timestamp": ts,
                    "scan_count": scan_count,
                    "last_scanned_at": now_utc
                }
                message = f"Product '{product['name']}' (₹{product['price']:.2f}) REMOVED from cart"
                log_record = {
                    "item_id": remove_id,
                    "cart_id": cart_id,
                    "event": "unregistered",
                    "action": "removed",
                    "product": product,
                    "message": message,
                    "timestamp": ts,
                    "timestamp_iso": now_utc,
                    "scan_count": scan_count
                }
                _save_item_and_log(remove_id, item_record, log_record)
                cart_summary = calculate_active_cart()
                print(f"[{ts}] REMOVED: {product['name']} (₹{product['price']:.2f}) | UID: {remove_id} | Total: ₹{cart_summary['total']:.2f}")

                return jsonify({
                    "item_id": remove_id,
                    "physical_uid": item_id,
                    "cart_id": cart_id,
                    "event": "unregistered",
                    "action": "removed",
                    "status": "unregistered",
                    "product": product,
                    "message": message,
                    "timestamp": ts,
                    "scan_count": scan_count,
                    "cart_summary": {
                        "active_count": cart_summary["count"],
                        "subtotal": cart_summary["subtotal"],
                        "tax": cart_summary["tax"],
                        "total": cart_summary["total"]
                    }
                }), 200
            else:
                cart_summary = calculate_active_cart()
                return jsonify({
                    "item_id": item_id,
                    "cart_id": cart_id,
                    "event": "idle",
                    "action": "none",
                    "message": "Cart is already empty",
                    "product": {"name": "Cart Empty", "price": 0, "icon": "🛒"},
                    "cart_summary": {
                        "active_count": 0,
                        "subtotal": 0.0,
                        "tax": 0.0,
                        "total": 0.0
                    }
                }), 200

        else:
            # Action: ADD item with next Indian product and fresh 8-char hex UID
            product = get_next_catalog_product()
            new_uid = f"{item_id[-4:]}{uuid.uuid4().hex[:4].upper()}"

            product_entry = dict(product)
            product_entry["item_id"] = new_uid
            _mem_products[new_uid] = product_entry
            save_products_to_disk()

            item_record = {
                "item_id": new_uid,
                "physical_card_uid": item_id,
                "cart_id": cart_id,
                "status": "registered",
                "action": "added",
                "product": product_entry,
                "timestamp": ts,
                "scan_count": 1,
                "last_scanned_at": now_utc
            }
            message = f"Product '{product_entry['name']}' (₹{product_entry['price']:.2f}) ADDED to cart [UID: {new_uid}]"
            log_record = {
                "item_id": new_uid,
                "cart_id": cart_id,
                "event": "registered",
                "action": "added",
                "product": product_entry,
                "message": message,
                "timestamp": ts,
                "timestamp_iso": now_utc,
                "scan_count": 1
            }
            _save_item_and_log(new_uid, item_record, log_record)
            cart_summary = calculate_active_cart()
            print(f"[{ts}] ADDED: {product_entry['name']} (₹{product_entry['price']:.2f}) | UID: {new_uid} | Total: ₹{cart_summary['total']:.2f}")

            return jsonify({
                "item_id": new_uid,
                "physical_uid": item_id,
                "cart_id": cart_id,
                "event": "registered",
                "action": "added",
                "status": "registered",
                "product": product_entry,
                "message": message,
                "timestamp": ts,
                "scan_count": 1,
                "cart_summary": {
                    "active_count": cart_summary["count"],
                    "subtotal": cart_summary["subtotal"],
                    "tax": cart_summary["tax"],
                    "total": cart_summary["total"]
                }
            }), 200

    # Mode 2: Strict RFID Toggle Mode (same physical UID toggles in/out)
    product = get_product(item_id)
    current_status = None
    prev_scan_count = 0

    if items_col is not None:
        try:
            existing = items_col.find_one({"item_id": item_id})
            if existing:
                current_status = existing.get("status", "unregistered")
                prev_scan_count = existing.get("scan_count", 0)
        except Exception as e:
            print(f"[MongoDB scan check] {e}")

    if current_status is None and item_id in _mem_items:
        current_status = _mem_items[item_id].get("status", "unregistered")
        prev_scan_count = _mem_items[item_id].get("scan_count", 0)

    if current_status == "registered":
        event_type = "unregistered"
        action = "removed"
        message = f"Product '{product['name']}' (₹{product['price']:.2f}) REMOVED from cart"
    else:
        event_type = "registered"
        action = "added"
        message = f"Product '{product['name']}' (₹{product['price']:.2f}) ADDED to cart"

    scan_count = prev_scan_count + 1

    item_record = {
        "item_id": item_id,
        "cart_id": cart_id,
        "status": event_type,
        "action": action,
        "product": product,
        "timestamp": ts,
        "scan_count": scan_count,
        "last_scanned_at": now_utc
    }

    log_record = {
        "item_id": item_id,
        "cart_id": cart_id,
        "event": event_type,
        "action": action,
        "product": product,
        "message": message,
        "timestamp": ts,
        "timestamp_iso": now_utc,
        "scan_count": scan_count
    }

    _save_item_and_log(item_id, item_record, log_record)
    cart_summary = calculate_active_cart()

    response_payload = {
        "item_id": item_id,
        "cart_id": cart_id,
        "event": event_type,
        "action": action,
        "status": event_type,
        "product": product,
        "message": message,
        "timestamp": ts,
        "scan_count": scan_count,
        "cart_summary": {
            "active_count": cart_summary["count"],
            "subtotal": cart_summary["subtotal"],
            "tax": cart_summary["tax"],
            "total": cart_summary["total"]
        }
    }

    print(f"[{ts}] {action.upper()}: {product['name']} (₹{product['price']:.2f}) | Cart: {cart_id} | Total: ₹{cart_summary['total']:.2f}")
    return jsonify(response_payload), 200

@app.route('/items')
def get_items():
    """Return all known items with their latest status and product details."""
    if items_col is not None:
        try:
            result = {}
            for doc in items_col.find({}):
                uid = doc.get("item_id")
                if uid:
                    p = doc.get("product") or get_product(uid)
                    result[uid] = {
                        "item_id": uid,
                        "status": doc.get("status", "registered"),
                        "cart_id": doc.get("cart_id", ""),
                        "timestamp": doc.get("timestamp", ""),
                        "scan_count": doc.get("scan_count", 1),
                        "product": p
                    }
            return jsonify(result)
        except Exception as e:
            print(f"[MongoDB /items] {e}")

    # Fallback to memory
    result = {}
    for uid, v in _mem_items.items():
        p = v.get("product") or get_product(uid)
        result[uid] = {
            "item_id": uid,
            "status": v.get("status", "registered"),
            "cart_id": v.get("cart_id", ""),
            "timestamp": v.get("timestamp", ""),
            "scan_count": v.get("scan_count", 1),
            "product": p
        }
    return jsonify(result)

@app.route('/cart')
def get_cart():
    """Return only active items in the cart and running totals."""
    summary = calculate_active_cart()
    summary["last_cart_id"] = _last_cart_id
    return jsonify(summary)

@app.route('/log')
def get_log():
    """Return chronological scan history."""
    if scans_col is not None:
        try:
            docs = list(scans_col.find({}, {"_id": 0, "timestamp_iso": 0}).sort("timestamp_iso", -1).limit(200))
            return jsonify(docs)
        except Exception as e:
            print(f"[MongoDB /log] {e}")
    # Memory fallback
    clean_logs = []
    for entry in _mem_log:
        e = dict(entry)
        e.pop("timestamp_iso", None)
        clean_logs.append(e)
    return jsonify(clean_logs)

@app.route('/products', methods=['GET', 'POST'])
def handle_products():
    """List or add/update products in the catalog."""
    global _mem_products
    if request.method == 'GET':
        if products_col is not None:
            try:
                docs = list(products_col.find({}, {"_id": 0}))
                if docs:
                    return jsonify({d["item_id"]: d for d in docs})
            except Exception:
                pass
        return jsonify(_mem_products)

    # POST: create or update product
    data = request.get_json(force=True, silent=True) or {}
    item_id = str(data.get('item_id', '')).upper().strip()
    name = str(data.get('name', '')).strip()
    price = float(data.get('price', 0.0))
    category = str(data.get('category', 'General')).strip()
    icon = str(data.get('icon', '🏷️')).strip()
    description = str(data.get('description', '')).strip()

    if not item_id or not name:
        return jsonify({"error": "item_id and name are required"}), 400

    product_obj = {
        "item_id": item_id,
        "name": name,
        "price": round(price, 2),
        "category": category,
        "icon": icon or "🏷️",
        "description": description
    }

    _mem_products[item_id] = product_obj
    save_products_to_disk()

    # Also update any existing items in cart with the new product info
    if item_id in _mem_items:
        _mem_items[item_id]["product"] = product_obj

    if products_col is not None:
        try:
            products_col.update_one({"item_id": item_id}, {"$set": product_obj}, upsert=True)
            if items_col is not None:
                items_col.update_one({"item_id": item_id}, {"$set": {"product": product_obj}})
        except Exception as e:
            print(f"[Products DB update] {e}")

    return jsonify({"status": "ok", "product": product_obj}), 200

@app.route('/products/<item_id>', methods=['DELETE'])
def delete_product(item_id):
    """Delete a product mapping from catalog."""
    global _mem_products
    item_id = str(item_id).upper().strip()
    if item_id in _mem_products:
        del _mem_products[item_id]
        save_products_to_disk()

    if products_col is not None:
        try:
            products_col.delete_one({"item_id": item_id})
        except Exception:
            pass

    return jsonify({"status": "deleted", "item_id": item_id}), 200

@app.route('/checkout', methods=['POST'])
def checkout():
    """Complete order for active items, generate receipt, and reset active cart."""
    data = request.get_json(force=True, silent=True) or {}
    payment_method = data.get("payment_method", "Contactless Card")
    customer_name = data.get("customer_name", "Shopper")

    cart_summary = calculate_active_cart()
    if cart_summary["count"] == 0:
        return jsonify({"error": "Cart is empty"}), 400

    receipt_id = f"RCPT-{datetime.now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:4].upper()}"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    receipt = {
        "receipt_id": receipt_id,
        "timestamp": ts,
        "cart_id": _last_cart_id,
        "customer_name": customer_name,
        "payment_method": payment_method,
        "items": cart_summary["items"],
        "subtotal": cart_summary["subtotal"],
        "tax": cart_summary["tax"],
        "total": cart_summary["total"],
        "status": "PAID"
    }

    # Save receipt
    save_receipt_to_disk(receipt)
    if receipts_col is not None:
        try:
            receipts_col.insert_one(dict(receipt))
        except Exception:
            pass

    # Mark all items as unregistered / checked out
    if items_col is not None:
        try:
            items_col.update_many(
                {"status": "registered"},
                {"$set": {"status": "unregistered", "last_checkout": ts}}
            )
        except Exception:
            pass

    for uid in _mem_items:
        if _mem_items[uid].get("status") == "registered":
            _mem_items[uid]["status"] = "unregistered"
            _mem_items[uid]["last_checkout"] = ts

    # Add checkout event to log
    checkout_log = {
        "item_id": "CHECKOUT",
        "cart_id": _last_cart_id,
        "event": "checkout",
        "action": "checkout",
        "product": {"name": f"Checkout #{receipt_id}", "price": cart_summary["total"], "icon": "💳"},
        "message": f"Cart checkout completed: ₹{cart_summary['total']:.2f} via {payment_method}",
        "timestamp": ts,
        "scan_count": 0
    }
    _mem_log.insert(0, checkout_log)
    if scans_col is not None:
        try:
            scans_col.insert_one(dict(checkout_log))
        except Exception:
            pass

    return jsonify({"success": True, "receipt": receipt})

@app.route('/receipts')
def get_receipts():
    """Return past checkout receipts."""
    if receipts_col is not None:
        try:
            docs = list(receipts_col.find({}, {"_id": 0}).sort("timestamp", -1).limit(50))
            if docs:
                return jsonify(docs)
        except Exception:
            pass
    return jsonify(_mem_receipts)

@app.route('/stats')
def get_stats():
    """Return comprehensive system and cart statistics."""
    cart_summary = calculate_active_cart()
    total_products = len(_mem_products)

    if items_col is not None and scans_col is not None:
        try:
            total_items = items_col.count_documents({})
            reg = items_col.count_documents({"status": "registered"})
            unreg = items_col.count_documents({"status": "unregistered"})
            scans_count = scans_col.count_documents({})
            return jsonify({
                "active_items": reg,
                "unregistered_items": unreg,
                "total_items": total_items,
                "total_products": total_products,
                "total_scans": scans_count,
                "cart_subtotal": cart_summary["subtotal"],
                "cart_tax": cart_summary["tax"],
                "cart_total": cart_summary["total"],
                "last_cart_id": _last_cart_id,
                "db_mode": "mongodb"
            })
        except Exception as e:
            print(f"[MongoDB /stats] {e}")

    total = len(_mem_items)
    reg = sum(1 for v in _mem_items.values() if v.get("status") == "registered")
    return jsonify({
        "active_items": reg,
        "unregistered_items": total - reg,
        "total_items": total,
        "total_products": total_products,
        "total_scans": len(_mem_log),
        "cart_subtotal": cart_summary["subtotal"],
        "cart_tax": cart_summary["tax"],
        "cart_total": cart_summary["total"],
        "last_cart_id": _last_cart_id,
        "db_mode": "memory"
    })

@app.route('/reset', methods=['POST'])
def reset():
    """Clear active cart items and scan history."""
    if items_col is not None:
        try:
            items_col.delete_many({})
            scans_col.delete_many({})
        except Exception:
            pass
    _mem_items.clear()
    _mem_log.clear()
    return jsonify({"status": "ok", "message": "Cart and logs cleared successfully"})

@app.route('/health')
def health():
    return jsonify({
        "ok": True,
        "status": "healthy",
        "service": "Smart RFID Shopping Cart Server",
        "server_time": datetime.now().isoformat()
    })

def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    local_ip = get_local_ip()
    print("=" * 60)
    print("  🛒 SMART RFID SHOPPING CART SERVER")
    print(f"  MongoDB     : {MONGO_URI} (db={MONGO_DB_NAME})")
    print(f"  Mac LAN IP  : {local_ip}")
    print(f"  Dashboard   : http://localhost:{port} (or http://{local_ip}:{port})")
    print(f"  Arduino URL : http://{local_ip}:{port}/scan (POST)")
    print(f"  Health      : http://localhost:{port}/health")
    print("=" * 60)
    print(f"  👉 Arduino code updated! Ensure serverUrl is: \"http://{local_ip}:{port}/scan\"")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
