# -*- coding: utf-8 -*-
import sqlite3
import requests
import telebot
import time
import os
import re
import urllib.parse
from threading import Thread
from flask import Flask, request, jsonify, render_template_string
from telebot import types

# ----------------- আপনার বোটের মূল সেটিংস -----------------
_p1 = "8305538092"
_p2 = "AAFSTufp-WJgux99zrQjcrdfzt1IDT87tEQ"
BOT_TOKEN = os.environ.get("BOT_TOKEN", f"{_p1}:{_p2}")
SMMSUN_API_URL = os.environ.get("SMMSUN_API_URL", "https://socialpanel.pro/api/v2")
SMMSUN_API_KEY = os.environ.get("SMMSUN_API_KEY", "14f3163c337f51c7c90c6232d9428bc2")
MAIN_ADMIN_ID = int(os.environ.get("MAIN_ADMIN_ID", 7561864109))
# --------------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ডাটাবেজ পাথ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.exists("/var/data"):
    DB_DIR = "/var/data"
elif os.path.exists("/data"):
    DB_DIR = "/data"
elif os.environ.get("DATA_DIR") and os.path.exists(os.environ.get("DATA_DIR")):
    DB_DIR = os.environ.get("DATA_DIR")
else:
    DB_DIR = BASE_DIR

DB_FILE = os.path.join(DB_DIR, "users.db")
USER_STATES = {}
FAILED_ATTEMPTS = {}

def create_2col_markup(button_list):
    markup = types.InlineKeyboardMarkup()
    for i in range(0, len(button_list), 2):
        if i + 1 < len(button_list):
            markup.row(button_list[i], button_list[i+1])
        else:
            markup.row(button_list[i])
    return markup

def init_db():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, joined_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)")
        cursor.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, chat_id INTEGER, service_name TEXT, quantity INTEGER, cost REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, method TEXT, amount REAL, txid TEXT, status TEXT DEFAULT 'Pending', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS auto_transactions (txid TEXT PRIMARY KEY, amount REAL, method TEXT, status TEXT DEFAULT 'Unclaimed')")
        cursor.execute("CREATE TABLE IF NOT EXISTS main_categories (name TEXT PRIMARY KEY, sort_order INTEGER DEFAULT 0)")
        cursor.execute("CREATE TABLE IF NOT EXISTS sub_categories (main_name TEXT, sub_name TEXT, sort_order INTEGER DEFAULT 0, PRIMARY KEY (main_name, sub_name))")
        cursor.execute("CREATE TABLE IF NOT EXISTS services (main_cat TEXT, sub_cat TEXT, id_bot TEXT, api_id TEXT, name TEXT, price_per_1k REAL DEFAULT 0.0, min_qty INTEGER DEFAULT 10, description TEXT DEFAULT '', PRIMARY KEY (main_cat, sub_cat, id_bot))")
        cursor.execute("CREATE TABLE IF NOT EXISTS force_channels (channel_id TEXT PRIMARY KEY, channel_name TEXT, invite_link TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        try: cursor.execute("ALTER TABLE main_categories ADD COLUMN sort_order INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass
        try: cursor.execute("ALTER TABLE sub_categories ADD COLUMN sort_order INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass
        try: cursor.execute("ALTER TABLE services ADD COLUMN description TEXT DEFAULT ''")
        except sqlite3.OperationalError: pass
        try: cursor.execute("ALTER TABLE users ADD COLUMN joined_at DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError: pass
        conn.commit()

def get_setting(key):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

def set_setting(key, value):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def clear_user_steps(chat_id):
    try:
        if hasattr(bot, 'next_step_handlers') and chat_id in bot.next_step_handlers:
            del bot.next_step_handlers[chat_id]
    except Exception:
        pass

def get_user_display(chat_id):
    try:
        chat = bot.get_chat(chat_id)
        if chat.username: return f"@{chat.username}"
        elif chat.first_name: return f"{chat.first_name}"
    except Exception: pass
    return f"User_{chat_id}"

def clean_transaction_id(txid):
    if not txid: return ""
    cleaned = re.sub(r'^(?:TrxID|TxnID|TxID|Trx|Txn|OrderID|Order\s*ID|Payment\s*ID)\s*[:=\-\s]*', '', str(txid), flags=re.IGNORECASE)
    return re.sub(r'[^A-Z0-9]', '', cleaned.strip().upper())

def get_bkash_number(): return get_setting("bkash_number") or "01925263571"
def get_nagad_number(): return get_setting("nagad_number") or "01925263571"
def get_binance_pay_id(): return get_setting("binance_pay_id") or "1132992475"
def get_usdt_rate(): return float(get_setting("usdt_rate") or 126.0)
def get_binance_status(): return get_setting("binance_status") or "ON"
def get_support_username(): return get_setting("support_username") or "@Mr_Sojol_Ceo"
def get_support_phone(): return get_setting("support_phone") or "+8801925263571"
def get_channel_link(): return get_setting("channel_link") or "https://t.me/your_channel"
def get_log_channel_id(): return get_setting("log_channel_id")
def get_coin_rate(): return float(get_setting("coin_rate_per_1000") or 12.0)
def get_bot_domain(): return get_setting("bot_domain") or "https://sojol.onrender.com"
def get_price_list_text(): return get_setting("price_list_text") or "💰 <b>বর্তমানে কোনো প্রাইজ লিস্ট সেট করা নেই।</b>"
def get_order_success_note(): return get_setting("order_success_note") or ""
def get_smm_api_url(): return get_setting("smm_api_url") or SMMSUN_API_URL
def get_smm_api_key(): return get_setting("smm_api_key") or SMMSUN_API_KEY

def is_admin(chat_id):
    if chat_id == MAIN_ADMIN_ID: return True
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (chat_id,))
        return cursor.fetchone() is not None

def add_co_admin(admin_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins VALUES (?)", (admin_id,))
        conn.commit()

def remove_co_admin(admin_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
        conn.commit()

def add_user(chat_id):
    is_new = False
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM users WHERE chat_id = ?", (chat_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (chat_id, balance) VALUES (?, 0.0)", (chat_id,))
            conn.commit()
            is_new = True
    return is_new

def get_balance(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        return row[0] if row else 0.0

def update_balance(chat_id, new_balance):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (chat_id, balance) VALUES (?, 0.0)", (chat_id,))
        cursor.execute("UPDATE users SET balance = ? WHERE chat_id = ?", (new_balance, chat_id))
        conn.commit()

def get_all_users():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM users")
        return [r[0] for r in cursor.fetchall()]

def get_user_stats(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders WHERE chat_id = ?", (chat_id,))
        total_orders = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM payments WHERE chat_id = ? AND status = 'Approved'", (chat_id,))
        total_payments = cursor.fetchone()[0]
        return total_orders, total_payments

def add_force_channel(channel_id, channel_name, invite_link):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO force_channels VALUES (?, ?, ?)", (channel_id, channel_name, invite_link))
        conn.commit()

def get_force_channels():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_name, invite_link FROM force_channels")
        return cursor.fetchall()

def delete_force_channel(channel_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM force_channels WHERE channel_id = ?", (channel_id,))
        conn.commit()

def check_user_joined_all(chat_id):
    channels = get_force_channels()
    unjoined = []
    for ch in channels:
        try:
            ch_id = ch[0].strip()
            if not ch_id.startswith('@') and not ch_id.startswith('-100'):
                ch_id = '@' + ch_id
            member = bot.get_chat_member(ch_id, chat_id)
            if member.status not in ['member', 'administrator', 'creator']:
                unjoined.append(ch)
        except Exception:
            unjoined.append(ch)
    return unjoined

def add_main_category(name, sort_order=0):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO main_categories (name, sort_order) VALUES (?, ?)", (name, sort_order))
        conn.commit()

def get_main_categories():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM main_categories ORDER BY sort_order ASC, name ASC")
        return [r[0] for r in cursor.fetchall()]

def delete_main_category(name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM main_categories WHERE name = ?", (name,))
        cursor.execute("DELETE FROM sub_categories WHERE main_name = ?", (name,))
        cursor.execute("DELETE FROM services WHERE main_cat = ?", (name,))
        conn.commit()

def add_sub_category(main_name, sub_name, sort_order=0):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO sub_categories (main_name, sub_name, sort_order) VALUES (?, ?, ?)", (main_name, sub_name, sort_order))
        conn.commit()

def get_sub_categories(main_cat):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sub_name FROM sub_categories WHERE main_name = ? ORDER BY sort_order ASC, sub_name ASC", (main_cat,))
        return [r[0] for r in cursor.fetchall()]

def delete_sub_category(main_name, sub_name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sub_categories WHERE main_name = ? AND sub_name = ?", (main_name, sub_name))
        cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ?", (main_name, sub_name))
        conn.commit()

def get_services_by_sub_cat(main_cat, sub_cat):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id_bot, api_id, name, price_per_1k, min_qty, description FROM services WHERE main_cat = ? AND sub_cat = ?", (main_cat, sub_cat))
        rows = cursor.fetchall()
        return [{"id": r[0], "api_id": r[1], "name": r[2], "price_per_1k": float(r[3]) if r[3] is not None else 0.0, "min_qty": r[4] if r[4] else 10, "description": r[5] if r[5] else "", "main_cat": main_cat, "sub_cat": sub_cat} for r in rows]

def delete_single_service(main_cat, sub_cat, id_bot="1"):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ?", (main_cat, sub_cat))
        conn.commit()

def add_order_to_db(order_id, chat_id, service_name, quantity, cost):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (order_id, chat_id, service_name, quantity, cost) VALUES (?, ?, ?, ?, ?)",
                       (order_id, chat_id, service_name, quantity, cost))
        conn.commit()

def get_user_orders(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT order_id, service_name, quantity, cost FROM orders WHERE chat_id = ? ORDER BY id DESC LIMIT 5", (chat_id,))
        return cursor.fetchall()

def add_payment_to_db(chat_id, method, amount, txid, status='Approved'):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (chat_id, method, amount, txid, status) VALUES (?, ?, ?, ?, ?)",
                       (chat_id, method, amount, txid, status))
        conn.commit()

def save_auto_sms_trx(txid, amount, method):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        clean_tx = clean_transaction_id(txid)
        if clean_tx:
            cursor.execute("INSERT OR REPLACE INTO auto_transactions (txid, amount, method, status) VALUES (?, ?, ?, 'Unclaimed')",
                           (clean_tx, float(amount), str(method)))
            conn.commit()

def claim_auto_trx(txid):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        clean_tx = clean_transaction_id(txid)
        if not clean_tx: return None, None
        cursor.execute("SELECT amount, method, status FROM auto_transactions WHERE UPPER(txid) = UPPER(?)", (clean_tx,))
        row = cursor.fetchone()
        if row and str(row[2]).strip().lower() == 'unclaimed':
            cursor.execute("UPDATE auto_transactions SET status = 'Claimed' WHERE UPPER(txid) = UPPER(?)", (clean_tx,))
            conn.commit()
            return float(row[0]), str(row[1])
        return None, None

init_db()

@app.route('/')
def home():
    domain = request.url_root.strip('/')
    if domain.startswith("http://"): domain = domain.replace("http://", "https://")
    set_setting("bot_domain", domain)
    return "SMM Bot Server is Alive and 24/7 Running!", 200

@app.route('/payment-page')
def payment_page():
    bdt = request.args.get('bdt', '60')
    bkash_num = request.args.get('bkash', '01925263571')
    nagad_num = request.args.get('nagad', '01925263571')
    binance_id = get_binance_pay_id()
    usdt_rate = get_usdt_rate()
    binance_status = get_binance_status()
    try:
        usdt_amount = round(float(bdt) / usdt_rate, 2)
    except Exception:
        usdt_amount = 0.48
    
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>MR PAY GATEWAY</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * { box-sizing: border-box; }
            body { font-family: 'Arial', sans-serif; background: linear-gradient(135deg, #F3F8FF 0%, #E3EFFF 100%); margin: 0; padding: 10px; color: #333; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .container { background-color: #fff; border-radius: 20px; padding: 15px; box-shadow: 0 10px 30px rgba(30,136,229,0.1); text-align: center; width: 100%; max-width: 400px; }
            .banner-img { width: 100%; border-radius: 12px; margin-bottom: 12px; max-height: 140px; object-fit: cover; }
            .instructions-banner { padding: 10px; border-radius: 10px; font-size: 13px; margin-bottom: 15px; font-weight: bold; text-align: center; }
            .method-btn { background: linear-gradient(135deg, #1E88E5 0%, #1565C0 100%); color: white; padding: 12px; border-radius: 10px; font-size: 15px; font-weight: bold; border: none; width: 100%; cursor: pointer; margin-bottom: 15px; }
            .payment-box { display: none; text-align: left; padding: 15px; border-radius: 15px; color: white; box-shadow: 0 8px 20px rgba(0,0,0,0.15); }
            .bkash-theme { background: linear-gradient(135deg, #E2125D 0%, #9F063A 100%); }
            .nagad-theme { background: linear-gradient(135deg, #E11C24 0%, #A30A0E 100%); }
            .binance-theme { background: linear-gradient(135deg, #181A20 0%, #0B0E11 100%); color: #F0B90B; border: 1px solid #F0B90B; }
            .input-trx { width: 100%; padding: 12px; border-radius: 8px; border: 2px solid rgba(255,255,255,0.4); margin: 10px 0; font-size: 15px; background: rgba(255,255,255,0.15); color: white; outline: none; }
            .input-trx::placeholder { color: rgba(255,255,255,0.7); }
            .copy-row { display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.18); padding: 10px; border-radius: 8px; font-size: 15px; margin: 8px 0; border: 1px dashed rgba(255,255,255,0.5); }
            .binance-theme .copy-row { background: rgba(240, 185, 11, 0.15); border: 1px dashed #F0B90B; color: #fff; }
            .copy-btn { background: white; color: #333; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold; }
            .verify-btn { background: #fff; color: #333; width: 100%; padding: 14px; border-radius: 10px; border: none; font-size: 15px; font-weight: bold; cursor: pointer; margin-top: 15px; }
            .binance-theme .verify-btn { background: #F0B90B; color: #000; }
            .footer-nav { margin-top: 20px; display: flex; gap: 12px; justify-content: center; }
            .icon-btn { background: #fff; border: 1px solid #e0e0e0; border-radius: 50%; width: 45px; height: 45px; display: flex; align-items: center; justify-content: center; font-size: 20px; cursor: pointer; text-decoration: none; }
            .gateway-options { display: flex; justify-content: space-between; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
            .gate-select-btn { border: 1px solid #e2e8f0; background: white; padding: 6px; border-radius: 12px; width: 31%; cursor: pointer; display: flex; align-items: center; justify-content: center; height: 75px; }
            .gate-select-btn img { max-height: 100%; max-width: 100%; object-fit: contain; }
            .active-view { display: block !important; }
        </style>
    </head>
    <body>
        <div class="container">
            <img src="https://files.catbox.moe/4c11cv.jpg" class="banner-img" alt="Payment Banner">
            <div id="method-selection-view" class="active-view">
                <button class="method-btn">Select Payment Method</button>
                <div class="gateway-options">
                    <div class="gate-select-btn" onclick="switchView('bkash')"><img src="https://files.catbox.moe/54mbuq.jpg" alt="bKash"></div>
                    <div class="gate-select-btn" onclick="switchView('nagad')"><img src="https://files.catbox.moe/m4iobq.jpg" alt="Nagad"></div>
                    {% if binance_status == 'ON' %}
                    <div class="gate-select-btn" onclick="switchView('binance')"><img src="https://files.catbox.moe/uwbw0v.jpg" alt="Binance Pay"></div>
                    {% endif %}
                </div>
                <div class="footer-nav">
                    <a href="https://t.me/Mr_Sojol_Ceo" class="icon-btn">🎧</a>
                    <a href="https://wa.me/8801925263571" class="icon-btn">💬</a>
                    <a href="tel:01925263571" class="icon-btn">📞</a>
                </div>
                <button class="method-btn" style="margin-top:20px; background:#EBF5FB; color:#1E88E5;" disabled>Amount: {{ bdt }} BDT {% if binance_status == 'ON' %}(~{{ usdt_amount }} USDT){% endif %}</button>
            </div>

            <div id="bkash-payment-view" class="payment-box bkash-theme">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
                    <span style="font-weight:bold; font-size:18px;">bKash Personal</span>
                    <span style="font-weight:bold; font-size:18px;">{{ bdt }} BDT</span>
                </div>
                <div class="instructions-banner" style="background:rgba(0,0,0,0.25);">টাকা পাঠানোর ৫-১০ সেকেন্ড পর ভেরিফাই করুন।</div>
                <label style="font-size:13px; font-weight:bold;">ট্রানজেকশন আইডি দিন</label>
                <input type="text" id="bkash-trx" class="input-trx" placeholder="TrxID দিন">
                <div style="font-size:13px; line-height:1.6;">
                    <p>• <b>Send Money</b> করুন নিচের নাম্বারে:</p>
                    <div class="copy-row">
                        <span id="bkash-num-val" style="font-weight:bold; font-size:16px;">{{ bkash_num }}</span>
                        <button class="copy-btn" onclick="copyNumber('{{ bkash_num }}')">Copy</button>
                    </div>
                    <p>• পরিমাণ: <b>{{ bdt }} BDT</b> সেন্ড করে TrxID দিয়ে ভেরিফাই করুন।</p>
                </div>
                <button class="verify-btn" onclick="verifyTrx('bkash')">VERIFY TRANSACTION</button>
                <button class="verify-btn" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.4); margin-top:8px;" onclick="goHome()">BACK</button>
            </div>

            <div id="nagad-payment-view" class="payment-box nagad-theme">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
                    <span style="font-weight:bold; font-size:18px;">Nagad Personal</span>
                    <span style="font-weight:bold; font-size:18px;">{{ bdt }} BDT</span>
                </div>
                <div class="instructions-banner" style="background:rgba(0,0,0,0.25);">টাকা পাঠানোর ৫-১০ সেকেন্ড পর ভেরিফাই করুন।</div>
                <label style="font-size:13px; font-weight:bold;">ট্রানজেকশন আইডি দিন</label>
                <input type="text" id="nagad-trx" class="input-trx" placeholder="TxnID দিন">
                <div style="font-size:13px; line-height:1.6;">
                    <p>• <b>Send Money</b> করুন নিচের নাম্বারে:</p>
                    <div class="copy-row">
                        <span id="nagad-num-val" style="font-weight:bold; font-size:16px;">{{ nagad_num }}</span>
                        <button class="copy-btn" onclick="copyNumber('{{ nagad_num }}')">Copy</button>
                    </div>
                    <p>• পরিমাণ: <b>{{ bdt }} BDT</b> সেন্ড করে TxnID দিয়ে ভেরিফাই করুন।</p>
                </div>
                <button class="verify-btn" onclick="verifyTrx('nagad')">VERIFY TRANSACTION</button>
                <button class="verify-btn" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.4); margin-top:8px;" onclick="goHome()">BACK</button>
            </div>

            <div id="binance-payment-view" class="payment-box binance-theme">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
                    <span style="font-weight:bold; font-size:18px; color:#F0B90B;">Binance Pay</span>
                    <span style="font-weight:bold; font-size:18px; color:#F0B90B;">{{ usdt_amount }} USDT</span>
                </div>
                <div class="instructions-banner" style="background:rgba(240,185,11,0.15); color:#F0B90B;">রেট: ১ USDT = {{ usdt_rate }} BDT (~{{ bdt }} ৳)</div>
                <label style="font-size:13px; font-weight:bold; color:#fff;">Order ID / TrxID দিন</label>
                <input type="text" id="binance-trx" class="input-trx" placeholder="বাইনান্স Order ID দিন">
                <div style="font-size:13px; line-height:1.6; color:#fff;">
                    <p>• <b>Binance Pay ID</b>-তে সেন্ড করুন:</p>
                    <div class="copy-row">
                        <span id="binance-id-val" style="font-weight:bold; font-size:16px; color:#F0B90B;">{{ binance_id }}</span>
                        <button class="copy-btn" style="background:#F0B90B; color:#000;" onclick="copyNumber('{{ binance_id }}')">Copy</button>
                    </div>
                    <p>• পরিমাণ: <b>{{ usdt_amount }} USDT</b> সেন্ড করে Order ID দিন।</p>
                </div>
                <button class="verify-btn" onclick="verifyTrx('binance')">VERIFY TRANSACTION</button>
                <button class="verify-btn" style="background:transparent; color:#fff; border:1px solid rgba(255,255,255,0.4); margin-top:8px;" onclick="goHome()">BACK</button>
            </div>
        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.ready(); tg.expand();
            function switchView(method) {
                document.getElementById('method-selection-view').classList.remove('active-view');
                document.getElementById('bkash-payment-view').classList.remove('active-view');
                document.getElementById('nagad-payment-view').classList.remove('active-view');
                const binView = document.getElementById('binance-payment-view');
                if (binView) binView.classList.remove('active-view');
                if (method === 'bkash') document.getElementById('bkash-payment-view').classList.add('active-view');
                else if (method === 'nagad') document.getElementById('nagad-payment-view').classList.add('active-view');
                else if (method === 'binance' && binView) binView.classList.add('active-view');
                window.scrollTo(0, 0);
            }
            function goHome() {
                document.getElementById('bkash-payment-view').classList.remove('active-view');
                document.getElementById('nagad-payment-view').classList.remove('active-view');
                const binView = document.getElementById('binance-payment-view');
                if (binView) binView.classList.remove('active-view');
                document.getElementById('method-selection-view').classList.add('active-view');
                window.scrollTo(0, 0);
            }
            function copyNumber(num) {
                navigator.clipboard.writeText(num).then(() => alert('সফলভাবে কপি করা হয়েছে!'));
            }
            function verifyTrx(method) {
                let trx = '';
                if (method === 'bkash') trx = document.getElementById('bkash-trx').value;
                else if (method === 'nagad') trx = document.getElementById('nagad-trx').value;
                else if (method === 'binance') trx = document.getElementById('binance-trx').value;
                trx = trx.trim();
                if (!trx) { alert('সঠিক ID/TrxID টাইপ করুন।'); return; }
                tg.sendData(trx);
                tg.close();
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_content, bdt=bdt, bkash_num=bkash_num, nagad_num=nagad_num, binance_id=binance_id, usdt_rate=usdt_rate, usdt_amount=usdt_amount, binance_status=binance_status)

def verify_and_credit_payment(chat_id, raw_txid):
    user_txid = clean_transaction_id(raw_txid)
    if not user_txid or len(user_txid) < 6: return False
    amount, method = claim_auto_trx(user_txid)

    if amount and method:
        if chat_id in FAILED_ATTEMPTS: FAILED_ATTEMPTS.pop(chat_id)
        received_bdt = amount
        current_bal = get_balance(chat_id)
        new_balance = current_bal + received_bdt
        update_balance(chat_id, new_balance)
        add_payment_to_db(chat_id, method, received_bdt, user_txid, status='Approved')

        bot.send_message(
            chat_id,
            f"✅ <b>পেমেন্ট সফলভাবে ভেরিফাই হয়েছে!</b>\n\n"
            f"💳 <b>মেথড:</b> {method}\n"
            f"৳ <b>প্রাপ্ত ব্যালেন্স:</b> <b>৳ {received_bdt:.2f} BDT</b>\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>৳ {new_balance:.2f} BDT</b> 🎉",
            reply_markup=get_main_menu_markup(chat_id),
            parse_mode="HTML"
        )

        try:
            user_disp = get_user_display(chat_id)
            admin_msg = (
                f"🎉 <b>AUTO DEPOSIT SUCCESSFUL!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>ইউজারনেম:</b> <b>{user_disp}</b>\n"
                f"💵 <b>টাকা পরিমাণ:</b> <b>{amount:.2f} BDT</b>\n"
                f"💳 <b>মেথড:</b> <b>{method}</b>\n"
                f"🆔 <b>TrxID:</b> <code>{user_txid}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            bot.send_message(MAIN_ADMIN_ID, admin_msg, parse_mode="HTML")
        except Exception:
            pass
        return True
    return False

@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    chat_id = message.chat.id
    clear_user_steps(chat_id)
    raw_txid = message.web_app_data.data.strip() if (message.web_app_data and message.web_app_data.data) else ""
    if not verify_and_credit_payment(chat_id, raw_txid):
        bot.send_message(
            chat_id,
            "❌ <b>অনুরোধ প্রত্যাখ্যান! সঠিক TrxID/Order ID পাওয়া যায়নি অথবা টাকা পাঠানোর ৫-১০ সেকেন্ড হয়নি।</b>\n\nঅনুগ্রহ করে '💳 CLICK TO PAY' বাটনে ক্লিক করে সঠিক TrxID দিয়ে পুনরায় চেষ্টা করুন।",
            reply_markup=get_main_menu_markup(chat_id),
            parse_mode="HTML"
        )

@app.route('/sms-webhook', methods=['POST', 'GET'], strict_slashes=False)
@app.route('/sms-webhook/<token>', methods=['POST', 'GET'], strict_slashes=False)
def sms_webhook(token=None):
    try:
        raw_parts = []
        if request.is_json:
            try:
                js = request.get_json(force=True, silent=True)
                if js: raw_parts.extend([str(k) + " " + str(v) for k, v in js.items()])
            except Exception: pass
        if request.args: raw_parts.extend([str(v) for v in request.args.values()])
        if request.form: raw_parts.extend([str(v) for v in request.form.values()])
        try:
            raw_data = request.get_data(as_text=True)
            if raw_data: raw_parts.append(raw_data)
        except Exception: pass
                
        full_text = urllib.parse.unquote(" ".join(raw_parts)).replace('+', ' ')

        # বাইনান্স পে নোটিফিকেশন ডিটেকশন
        if "binance" in full_text.lower() or "usdt" in full_text.lower() or "order id" in full_text.lower():
            method = "Binance Pay"
            trx_match = re.search(r'(?:Order\s*ID|OrderID|Order|ID)\s*[:=\-\s]*([A-Za-z0-9]{8,24})', full_text, re.IGNORECASE)
            amt_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:USDT|USD|\$)', full_text, re.IGNORECASE)
            if not trx_match: trx_match = re.search(r'\b[0-9]{14,22}\b', full_text)
            txid = trx_match.group(1).strip().upper() if (trx_match and hasattr(trx_match, 'group')) else (trx_match.group(0) if trx_match else None)
            
            if txid:
                usdt_received = float(amt_match.group(1)) if amt_match else 0.48
                rate = get_usdt_rate()
                amount_bdt = round(usdt_received * rate, 2)
                clean_tx = clean_transaction_id(txid)
                save_auto_sms_trx(clean_tx, amount_bdt, method)
                try: bot.send_message(MAIN_ADMIN_ID, f"🟡 <b>Binance Pay Received!</b>\n\n💵 USDT: <b>{usdt_received} USDT</b>\n৳ BDT: <b>{amount_bdt:.2f} BDT</b>\n🆔 Order ID: <code>{clean_tx}</code>", parse_mode="HTML")
                except Exception: pass
                return jsonify({"status": "success"}), 200

        # বিকাশ ও নগদ ডিটেকশন
        trx_match = re.search(r'(?:TrxID|TxnID|TxID|Trx\s*ID|Txn\s*ID|Transaction\s*ID|Trans\s*ID)\s*[:=\-\s]*([A-Za-z0-9]{6,16})', full_text, re.IGNORECASE)
        amt_match = re.search(r'(?:Tk|Tk\.|Amount|BDT|received|deposit of|Cash In)\.?\s*[:=\-\s]*(?:Tk\.?\s*)?([0-9]+(?:\.[0-9]+)?)', full_text, re.IGNORECASE)

        if not trx_match:
            possible_codes = re.findall(r'\b[A-Za-z0-9]{6,16}\b', full_text)
            for code in possible_codes:
                if any(c.isdigit() for c in code) and any(c.isalpha() for c in code):
                    txid = code.strip().upper()
                    break
            else: txid = None
        else:
            txid = trx_match.group(1).strip().upper()

        if txid:
            amount = float(amt_match.group(1)) if amt_match else 10.0
            method = "Nagad" if ("Nagad" in full_text or "TxnID" in full_text or "TXNID" in full_text) else "bKash"
            clean_tx = clean_transaction_id(txid)
            save_auto_sms_trx(clean_tx, amount, method)
            try: bot.send_message(MAIN_ADMIN_ID, f"📩 <b>{method} Auto SMS Received!</b>\n\n💵 Amount: <b>{amount:.2f} BDT</b>\n🆔 TrxID: <code>{clean_tx}</code>", parse_mode="HTML")
            except Exception: pass

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "success", "error": str(e)}), 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

def get_multiple_orders_status(order_ids):
    if not order_ids: return {}
    try:
        payload = {"key": get_smm_api_key(), "action": "status", "orders": ",".join(map(str, order_ids))}
        response = requests.post(get_smm_api_url(), data=payload, timeout=3)
        res = response.json()
        return res if isinstance(res, dict) else {}
    except Exception: return {}

# ================== 👑 এডমিন প্যানেল (/admin) ==================

@bot.message_handler(commands=["admin"])
def admin_panel_command(message):
    if not is_admin(message.chat.id): return
    try:
        clear_user_steps(message.chat.id)
        btns = [
            types.InlineKeyboardButton("➕ মেইন প্ল্যাটফর্ম যোগ", callback_data="admin_add_main_cat"),
            types.InlineKeyboardButton("📂 সাব-ক্যাটাগরি যোগ", callback_data="admin_add_sub_cat"),
            types.InlineKeyboardButton("🛒 সার্ভিস যোগ", callback_data="admin_add_service_start"),
            types.InlineKeyboardButton("🔍 ইউজার ইনফো ও ব্যালেন্স", callback_data="admin_user_info_start"),
            types.InlineKeyboardButton("🖼️ স্টার্ট পিকচার সেট", callback_data="admin_set_start_photo"),
            types.InlineKeyboardButton("📝 স্টার্ট মেসেজ সেট", callback_data="admin_set_welcome_text"),
            types.InlineKeyboardButton("📢 জয়েন চ্যানেল সেটআপ", callback_data="admin_force_channel_menu"),
            types.InlineKeyboardButton("🔌 SMM API এডিট", callback_data="admin_set_smm_api"),
            types.InlineKeyboardButton("👑 এডমিন যোগ/রিমুভ", callback_data="admin_manage_co_admins"),
            types.InlineKeyboardButton("🗑️ সার্ভিস ডিলিট", callback_data="admin_delete_single_service_start"),
            types.InlineKeyboardButton("🗑️ প্ল্যাটফর্ম ডিলিট", callback_data="admin_del_main_platform_start"),
            types.InlineKeyboardButton("🗑️ সাব-ক্যাট ডিলিট", callback_data="admin_del_subcategory_start"),
            types.InlineKeyboardButton("🪙 কয়েন রেট আপডেট", callback_data="admin_set_coin_rate"),
            types.InlineKeyboardButton("📢 ব্রডকাস্ট মেসেজ", callback_data="admin_broadcast_start"),
            types.InlineKeyboardButton("📊 লাইভ সেলস ও লাভ", callback_data="admin_live_stats"),
            types.InlineKeyboardButton("📞 বিকাশ নাম্বার সেট", callback_data="admin_set_bkash"),
            types.InlineKeyboardButton("📱 নগদ নাম্বার সেট", callback_data="admin_set_nagad"),
            types.InlineKeyboardButton("🟡 বাইনান্স পে কন্ট্রোল", callback_data="admin_set_binance_menu"),
            types.InlineKeyboardButton("👤 সাপোর্ট ইউজার সেট", callback_data="admin_set_sup_user"),
            types.InlineKeyboardButton("📱 সাপোর্ট ফোন সেট", callback_data="admin_set_sup_phone"),
            types.InlineKeyboardButton("📦 অর্ডার লগ চ্যানেল সেট", callback_data="admin_set_log_chan"),
            types.InlineKeyboardButton("💰 প্রাইজ লিস্ট টেক্সট সেট", callback_data="admin_set_price_text"),
            types.InlineKeyboardButton("📝 অর্ডার সাকসেস নোট সেট", callback_data="admin_set_success_note"),
            types.InlineKeyboardButton("💥 সকল সার্ভিস ডিলিট", callback_data="admin_clear_services_confirm")
        ]
        bot.send_message(message.chat.id, "👑 <b>এডমিন কন্ট্রোল প্যানেল</b>\n━━━━━━━━━━━━━━━━━━━━━━\nনিচের বাটন চেপে কাজ নির্বাচন করুন:", reply_markup=create_2col_markup(btns), parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_binance_menu")
def admin_set_binance_menu(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    status = get_binance_status()
    pay_id = get_binance_pay_id()
    rate = get_usdt_rate()
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton(f"স্ট্যাটাস: {'🟢 চালু (ON)' if status == 'ON' else '🔴 বন্ধ (OFF)'}", callback_data="admin_toggle_binance"))
    markup.add(types.InlineKeyboardButton("✏️ Pay ID পরিবর্তন", callback_data="admin_set_binance_id"), types.InlineKeyboardButton("💵 ডলার রেট পরিবর্তন", callback_data="admin_set_binance_rate"))
    text = f"🟡 <b>Binance Pay কন্ট্রোল প্যানেল</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🔘 <b>বর্তমান অবস্থা:</b> <b>{status}</b>\n🆔 <b>Pay ID:</b> <code>{pay_id}</code>\n💵 <b>ডলার রেট:</b> <b>১ USDT = {rate:.2f} BDT</b>"
    bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_toggle_binance")
def admin_toggle_binance(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    new_status = "OFF" if get_binance_status() == "ON" else "ON"
    set_setting("binance_status", new_status)
    bot.send_message(call.message.chat.id, f"✅ <b>Binance Pay স্ট্যাটাস: {new_status} করা হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_binance_id")
def admin_set_binance_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "🆔 <b>নতুন Binance Pay ID লিখে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("binance_pay_id", m.text.strip()), bot.send_message(m.chat.id, f"✅ <b>Binance Pay ID সেট হয়েছে:</b> <code>{m.text.strip()}</code>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_binance_rate")
def admin_set_binance_rate(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "💵 <b>১ USDT এর মূল্য কত টাকা করবেন? (যেমন: 126):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_binance_rate)

def save_binance_rate(m):
    try:
        rate = float(m.text.strip())
        set_setting("usdt_rate", rate)
        bot.send_message(m.chat.id, f"✅ <b>ডলার রেট আপডেট হয়েছে:</b> ১ USDT = <b>{rate:.2f} BDT</b>", parse_mode="HTML")
    except Exception:
        bot.send_message(m.chat.id, "❌ ভুল ইনপুট! শুধুমাত্র সংখ্যা লিখুন।")

@bot.callback_query_handler(func=lambda call: call.data == "admin_live_stats")
def admin_live_stats_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*), SUM(cost) FROM orders")
            r_all_o = cursor.fetchone()
            total_orders_count = r_all_o[0] if r_all_o[0] else 0
            total_orders_cost = r_all_o[1] if r_all_o[1] else 0.0
            cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'Approved'")
            r_all_d = cursor.fetchone()
            total_all_deposit = r_all_d[0] if r_all_d[0] else 0.0
            cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'Approved' AND date(timestamp, 'localtime') = date('now', 'localtime')")
            r_t_d = cursor.fetchone()
            today_deposit = r_t_d[0] if r_t_d[0] else 0.0
            cursor.execute("SELECT COUNT(*), SUM(cost) FROM orders WHERE date(timestamp, 'localtime') = date('now', 'localtime')")
            r_t_o = cursor.fetchone()
            today_orders_count = r_t_o[0] if r_t_o[0] else 0
            today_orders_cost = r_t_o[1] if r_t_o[1] else 0.0
            
        stats_text = (
            f"📊 <b>লাইভ সেলস ও লাভ রিপোর্ট</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>সর্বমোট ইউজার:</b> <b>{total_users} জন</b>\n"
            f"🛒 <b>সর্বমোট অর্ডার:</b> <b>{total_orders_count} টি</b>\n"
            f"💰 <b>সর্বমোট সেলস:</b> <b>৳ {total_orders_cost:.2f} BDT</b>\n"
            f"💳 <b>সর্বমোট ডিপোজিট:</b> <b>৳ {total_all_deposit:.2f} BDT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>আজকের মোট ডিপোজিট:</b> <b>৳ {today_deposit:.2f} BDT</b>\n"
            f"🛒 <b>আজকের মোট অর্ডার:</b> <b>{today_orders_count} টি</b>\n"
            f"💵 <b>আজকের মোট সেলস:</b> <b>৳ {today_orders_cost:.2f} BDT</b>"
        )
        bot.send_message(call.message.chat.id, stats_text, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_main_cat")
def admin_add_main_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "✍️ <b>নতুন মেইন প্ল্যাটফর্মের নাম লিখুন:</b> (মুছতে `0` পাঠান)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_get_main_cat_serial)

def admin_get_main_cat_serial(message):
    mcat_name = message.text.strip()
    if mcat_name == "0": bot.send_message(message.chat.id, "❌ বাতিল করা হয়েছে।"); return
    msg = bot.send_message(message.chat.id, f"🔢 <b>[{mcat_name}] প্ল্যাটফর্মের সিরিয়াল নম্বর দিন (যেমন: 1, 2):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_confirm_main_cat, mcat_name)

def admin_confirm_main_cat(message, mcat_name):
    try: sort_order = int(message.text.strip())
    except ValueError: sort_order = 0
    USER_STATES[message.chat.id] = {"temp_mcat": mcat_name, "temp_sort": sort_order}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ নিশ্চিত করুন (Confirm)", callback_data="confirm_add_mcat_save"), types.InlineKeyboardButton("❌ বাতিল (Cancel)", callback_data="cancel_admin_action"))
    bot.send_message(message.chat.id, f"📌 <b>মেইন প্ল্যাটফর্ম:</b> <code>{mcat_name}</code>\n🔢 <b>সিরিয়াল:</b> <b>{sort_order}</b>\n\nসংরক্ষণ করতে কনফার্ম করুন:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_add_mcat_save")
def confirm_add_mcat_save(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    data = USER_STATES.pop(call.message.chat.id, {})
    if data.get("temp_mcat"):
        add_main_category(data["temp_mcat"], data.get("temp_sort", 0))
        bot.send_message(call.message.chat.id, f"✅ <b>[{data['temp_mcat']}] প্ল্যাটফর্ম যুক্ত হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_sub_cat")
def admin_add_sub_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    main_cats = get_main_categories()
    if not main_cats: bot.send_message(call.message.chat.id, "❌ আগে মেইন প্ল্যাটফর্ম তৈরি করুন!"); return
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admsubsel_{mc}") for mc in main_cats]
    bot.send_message(call.message.chat.id, "📁 <b>কোন প্ল্যাটফর্মের ভেতরে সাব-ক্যাটাগরি যোগ করবেন?</b>", reply_markup=create_2col_markup(btns), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admsubsel_"))
def admin_sub_cat_get_name(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    mcat_name = call.data.replace("admsubsel_", "")
    msg = bot.send_message(call.message.chat.id, f"✍️ <b>[{mcat_name}] এর নতুন সাব-ক্যাটাগরি নাম লিখুন:</b> (মুছতে `0` পাঠান)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_get_sub_cat_serial, mcat_name)

def admin_get_sub_cat_serial(message, mcat_name):
    sub_name = message.text.strip()
    if sub_name == "0": bot.send_message(message.chat.id, "❌ বাতিল করা হয়েছে।"); return
    msg = bot.send_message(message.chat.id, f"🔢 <b>[{sub_name}] এর সিরিয়াল নম্বর দিন (যেমন: 1, 2):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_confirm_sub_cat, mcat_name, sub_name)

def admin_confirm_sub_cat(message, mcat_name, sub_name):
    try: sort_order = int(message.text.strip())
    except ValueError: sort_order = 0
    USER_STATES[message.chat.id] = {"temp_mcat": mcat_name, "temp_sub": sub_name, "temp_sort": sort_order}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ নিশ্চিত করুন (Confirm)", callback_data="confirm_add_sub_save"), types.InlineKeyboardButton("❌ বাতিল (Cancel)", callback_data="cancel_admin_action"))
    bot.send_message(message.chat.id, f"📌 <b>সাব-ক্যাটাগরি:</b> <code>{sub_name}</code>\n🔢 <b>সিরিয়াল:</b> <b>{sort_order}</b>\n\nসংরক্ষণ করতে চাপ দিন:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_add_sub_save")
def confirm_add_sub_save(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    data = USER_STATES.pop(call.message.chat.id, {})
    if data.get("temp_mcat") and data.get("temp_sub"):
        add_sub_category(data["temp_mcat"], data["temp_sub"], data.get("temp_sort", 0))
        bot.send_message(call.message.chat.id, f"✅ <b>[{data['temp_mcat']}] -> [{data['temp_sub']}] তৈরি হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_service_start")
def admin_add_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    main_cats = get_main_categories()
    if not main_cats: bot.send_message(call.message.chat.id, "❌ কোনো প্ল্যাটফর্ম নেই!"); return
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admcatm_{mc}") for mc in main_cats]
    bot.send_message(call.message.chat.id, "📁 <b>মেইন প্ল্যাটফর্ম সিলেক্ট করুন:</b>", reply_markup=create_2col_markup(btns), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcatm_"))
def admin_step_select_sub_for_service(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    mcat_name = call.data.replace("admcatm_", "")
    sub_cats = get_sub_categories(mcat_name)
    if not sub_cats: bot.send_message(call.message.chat.id, f"❌ [{mcat_name}] এ কোনো সাব-ক্যাটাগরি নেই!"); return
    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"admcats_{mcat_name}___{sc}") for sc in sub_cats]
    bot.send_message(call.message.chat.id, f"📂 <b>[{mcat_name}] এর সাব-ক্যাটাগরি সিলেক্ট করুন:</b>", reply_markup=create_2col_markup(btns), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcats_"))
def admin_step_get_api_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    mcat_name, scat_name = call.data.replace("admcats_", "").split("___")
    msg = bot.send_message(call.message.chat.id, f"🔌 <b>[{scat_name}] এর আসল API ID কত? (যেমন: 19138):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_direct_coin, mcat_name, scat_name)

def admin_step_get_direct_coin(message, mcat_name, scat_name):
    api_id = message.text.strip()
    if api_id == "0": bot.send_message(message.chat.id, "❌ বাতিল করা হয়েছে।"); return
    msg = bot.send_message(message.chat.id, f"🪙 <b>প্রতি ১০০০টির জন্য কত টাকা কাটবেন? (যেমন: 10 বা 15):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_min_qty, mcat_name, scat_name, api_id)

def admin_step_get_min_qty(message, mcat_name, scat_name, api_id):
    try: coin_price = float(message.text.strip())
    except ValueError: bot.send_message(message.chat.id, "❌ ভুল ইনপুট!"); return
    msg = bot.send_message(message.chat.id, f"🔢 <b>সর্বনিম্ন কোয়ান্টিটি (Min Qty) কত? (যেমন: 100):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_description, mcat_name, scat_name, api_id, coin_price)

def admin_step_get_description(message, mcat_name, scat_name, api_id, coin_price):
    try: min_qty = int(message.text.strip())
    except ValueError: min_qty = 10
    msg = bot.send_message(message.chat.id, "📝 <b>সার্ভিসের বিবরণ (Description) লিখুন: (না দিতে `0` পাঠান)</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_prompt_service_confirm, mcat_name, scat_name, api_id, coin_price, min_qty)

def admin_step_prompt_service_confirm(message, mcat_name, scat_name, api_id, coin_price, min_qty):
    desc = "" if message.text.strip() == "0" else message.text.strip()
    USER_STATES[message.chat.id] = {"mcat": mcat_name, "scat": scat_name, "api_id": api_id, "price": coin_price, "min_qty": min_qty, "desc": desc}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ সংরক্ষণ করুন (Confirm)", callback_data="confirm_save_service_action"), types.InlineKeyboardButton("❌ বাতিল (Cancel)", callback_data="cancel_admin_action"))
    bot.send_message(message.chat.id, f"🛒 <b>সার্ভিস:</b> <code>{scat_name}</code>\n🔌 <b>API ID:</b> <b>{api_id}</b>\n💰 <b>১০০০টির মূল্য:</b> <b>{coin_price:.2f} BDT</b>\n🔢 <b>সর্বনিম্ন:</b> <b>{min_qty} টি</b>\n\nসংরক্ষণ করতে কনফার্ম করুন:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_save_service_action")
def confirm_save_service_action(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    data = USER_STATES.pop(call.message.chat.id, {})
    if data:
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO services (main_cat, sub_cat, id_bot, api_id, name, price_per_1k, min_qty, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (data['mcat'], data['scat'], "1", data['api_id'], data['scat'], data['price'], data['min_qty'], data['desc']))
            conn.commit()
        bot.send_message(call.message.chat.id, f"✅ <b>[{data['scat']}] সার্ভিসটি সফলভাবে সংরক্ষিত হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_admin_action")
def cancel_admin_action(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    USER_STATES.pop(call.message.chat.id, None)
    clear_user_steps(call.message.chat.id)
    bot.send_message(call.message.chat.id, "❌ <b>কাজটি বাতিল করা হয়েছে।</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_bkash")
def admin_set_bkash(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📞 <b>নতুন বিকাশ নাম্বার টাইপ করে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("bkash_number", m.text.strip()), bot.send_message(m.chat.id, f"✅ <b>বিকাশ নাম্বার সেট হয়েছে:</b> <code>{m.text.strip()}</code>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_nagad")
def admin_set_nagad(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📱 <b>নতুন নগদ নাম্বার টাইপ করে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("nagad_number", m.text.strip()), bot.send_message(m.chat.id, f"✅ <b>নগদ নাম্বার সেট হয়েছে:</b> <code>{m.text.strip()}</code>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_sup_user")
def admin_set_sup_user(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "👤 <b>সাপোর্ট ইউজারনেম দিন (@ সহ):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("support_username", m.text.strip()), bot.send_message(m.chat.id, f"✅ <b>সাপোর্ট ইউজারনেম সেট হয়েছে:</b> <code>{m.text.strip()}</code>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_sup_phone")
def admin_set_sup_phone(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📱 <b>সাপোর্ট ফোন নাম্বার দিন:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("support_phone", m.text.strip()), bot.send_message(m.chat.id, f"✅ <b>সাপোর্ট ফোন সেট হয়েছে:</b> <code>{m.text.strip()}</code>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_log_chan")
def admin_set_log_chan(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📦 <b>অর্ডার ফরওয়ার্ড চ্যানেল ID দিন:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("log_channel_id", m.text.strip()), bot.send_message(m.chat.id, f"✅ <b>লগ চ্যানেল আইডি সেট হয়েছে:</b> <code>{m.text.strip()}</code>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_price_text")
def admin_set_price_text(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "💰 <b>প্রাইজ লিস্ট কাস্টম টেক্সট পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("price_list_text", m.text.strip()), bot.send_message(m.chat.id, "✅ <b>প্রাইজ লিস্ট টেক্সট আপডেট হয়েছে!</b>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_success_note")
def admin_set_success_note(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📝 <b>অর্ডার সাকসেস অতিরিক্ত নোট দিন: (মুছতে `0` পাঠান)</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("order_success_note", "" if m.text.strip()=="0" else m.text.strip()), bot.send_message(m.chat.id, "✅ <b>সাকসেস নোট আপডেট হয়েছে!</b>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_coin_rate")
def admin_set_coin_rate(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "🪙 <b>১০০০ কয়েনের মূল্য কত টাকা করবেন? (যেমন: 12):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("coin_rate_per_1000", float(m.text.strip())), bot.send_message(m.chat.id, f"✅ <b>কয়েন রেট: {float(m.text.strip())} BDT</b>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast_start")
def admin_broadcast_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📢 <b>সকল ইউজারের জন্য নোটিশ মেসেজটি লিখুন:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    users = get_all_users()
    if not users: bot.send_message(message.chat.id, "❌ কোনো ইউজার নেই!"); return
    msg_loading = bot.send_message(message.chat.id, "⏳ ব্রডকাস্টিং চালু হচ্ছে...")
    s, f = 0, 0
    for uid in users:
        try:
            bot.send_message(uid, message.text, parse_mode="HTML")
            s += 1; time.sleep(0.05)
        except Exception: f += 1
    bot.edit_message_text(f"📢 <b>ব্রডকাস্ট রিপোর্ট:</b>\n✅ সফল: {s} জন | ❌ ব্যর্থ: {f} জন", chat_id=message.chat.id, message_id=msg_loading.message_id, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_smm_api")
def admin_set_smm_api(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "🔌 <b>নতুন SMM API URL দিন:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("smm_api_url", m.text.strip()), bot.register_next_step_handler(bot.send_message(m.chat.id, "🔑 <b>নতুন SMM API Key দিন:</b>", parse_mode="HTML"), lambda k: [set_setting("smm_api_key", k.text.strip()), bot.send_message(k.chat.id, "✅ <b>SMM API আপডেট হয়েছে!</b>", parse_mode="HTML")])])

@bot.callback_query_handler(func=lambda call: call.data == "admin_del_main_platform_start")
def admin_del_main_platform_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    main_cats = get_main_categories()
    if not main_cats: bot.send_message(call.message.chat.id, "❌ কোনো প্ল্যাটফর্ম নেই।"); return
    btns = [types.InlineKeyboardButton(f"❌ {mc}", callback_data=f"delmainplatform_{mc}") for mc in main_cats]
    bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মটি সম্পূর্ণ ডিলিট করবেন?</b>", reply_markup=create_2col_markup(btns), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmainplatform_"))
def admin_del_main_platform_confirm(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delmainplatform_", "")
    delete_main_category(mcat_name)
    bot.send_message(call.message.chat.id, f"✅ <b>[{mcat_name}] প্ল্যাটফর্মটি মুছে ফেলা হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_del_subcategory_start")
def admin_del_subcategory_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    main_cats = get_main_categories()
    if not main_cats: bot.send_message(call.message.chat.id, "❌ কোনো প্ল্যাটফর্ম নেই।"); return
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"delsubcatselectmc_{mc}") for mc in main_cats]
    bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মের সাব-ক্যাটাগরি ডিলিট করবেন?</b>", reply_markup=create_2col_markup(btns), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsubcatselectmc_"))
def admin_del_subcategory_select_sub(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delsubcatselectmc_", "")
    sub_cats = get_sub_categories(mcat_name)
    if not sub_cats: bot.send_message(call.message.chat.id, f"❌ [{mcat_name}] এ কোনো সাব-ক্যাটাগরি নেই।"); return
    btns = [types.InlineKeyboardButton(f"❌ {sc}", callback_data=f"delsubcatconfirm_{mcat_name}___{sc}") for sc in sub_cats]
    bot.send_message(call.message.chat.id, f"🗑️ <b>[{mcat_name}] এর কোন সাব-ক্যাটাগরি ডিলিট করবেন?</b>", reply_markup=create_2col_markup(btns), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsubcatconfirm_"))
def admin_del_subcategory_confirm(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name, scat_name = call.data.replace("delsubcatconfirm_", "").split("___")
    delete_sub_category(mcat_name, scat_name)
    bot.send_message(call.message.chat.id, f"✅ <b>[{mcat_name}] -> [{scat_name}] ডিলিট হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_single_service_start")
def admin_delete_single_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    main_cats = get_main_categories()
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"delmcat_{mc}") for mc in main_cats]
    bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মের সার্ভিস ডিলিট করবেন?</b>", reply_markup=create_2col_markup(btns), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmcat_"))
def admin_del_select_sub(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delmcat_", "")
    sub_cats = get_sub_categories(mcat_name)
    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"delscat_{mcat_name}___{sc}") for sc in sub_cats]
    bot.send_message(call.message.chat.id, f"🗑️ <b>[{mcat_name}] এর সাব-ক্যাটাগরি সার্ভিস সিলেক্ট করুন:</b>", reply_markup=create_2col_markup(btns), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delscat_"))
def admin_del_select_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name, scat_name = call.data.replace("delscat_", "").split("___")
    delete_single_service(mcat_name, scat_name, "1")
    bot.send_message(call.message.chat.id, f"✅ <b>[{scat_name}] সার্ভিসটি ডিলিট হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_co_admins")
def admin_manage_co_admins(call):
    if call.message.chat.id != MAIN_ADMIN_ID: bot.answer_callback_query(call.id, "❌ শুধু মেইন Admin এটি পারবে!"); return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("➕ এডমিন যোগ", callback_data="coadmin_add"), types.InlineKeyboardButton("❌ এডমিন রিমুভ", callback_data="coadmin_remove"))
    bot.send_message(MAIN_ADMIN_ID, "👑 <b>এডমিন ম্যানেজমেন্ট</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("coadmin_"))
def coadmin_action(call):
    if call.message.chat.id != MAIN_ADMIN_ID: return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    action = call.data.replace("coadmin_", "")
    if action == "add":
        msg = bot.send_message(MAIN_ADMIN_ID, "👤 <b>ইউজার ID দিন:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, lambda m: [add_co_admin(int(m.text.strip())), bot.send_message(MAIN_ADMIN_ID, "✅ এডমিন যোগ হয়েছে!")])
    elif action == "remove":
        msg = bot.send_message(MAIN_ADMIN_ID, "👤 <b>ইউজার ID দিন:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, lambda m: [remove_co_admin(int(m.text.strip())), bot.send_message(MAIN_ADMIN_ID, "✅ এডমিন সরানো হয়েছে!")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_start_photo")
def admin_set_start_photo(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "🖼️ <b>বোট স্টার্টের ফটো Direct URL দিন: (মুছতে `0` পাঠান)</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("start_photo", "" if m.text.strip()=="0" else m.text.strip()), bot.send_message(m.chat.id, "✅ স্টার্ট পিকচার আপডেট হয়েছে!")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_welcome_text")
def admin_set_welcome_text(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📝 <b>বোটের প্রোফাইল ডেসক্রিপশন টেক্সট দিন: (মুছতে `0` পাঠান)</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: [set_setting("welcome_text", "" if m.text.strip()=="0" else m.text.strip()), bot.send_message(m.chat.id, "✅ ডেসক্রিপশন আপডেট হয়েছে!")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_force_channel_menu")
def admin_force_channel_menu(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    channels = get_force_channels()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels: markup.add(types.InlineKeyboardButton(f"❌ {ch[1]} ডিলিট করুন", callback_data=f"delchan_{ch[0]}"))
    if len(channels) < 4: markup.add(types.InlineKeyboardButton("➕ নতুন চ্যানেল যোগ", callback_data="addchan_start"))
    bot.send_message(call.message.chat.id, f"📢 <b>ফোর্সমস্ট চ্যানেল তালিকা ({len(channels)}/4):</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "addchan_start")
def addchan_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 <b>চ্যানেলের ইউজারনেম দিন (@ সহ):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: bot.register_next_step_handler(bot.send_message(m.chat.id, "🔗 <b>ইনভাইট লিংক দিন:</b>"), lambda l: bot.register_next_step_handler(bot.send_message(l.chat.id, "📌 <b>বাটনের নাম লিখুন:</b>"), lambda n: [add_force_channel(m.text.strip(), n.text.strip(), l.text.strip()), bot.send_message(n.chat.id, "✅ চ্যানেল যুক্ত হয়েছে!")])))

@bot.callback_query_handler(func=lambda call: call.data.startswith("delchan_"))
def delchan_process(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    delete_force_channel(call.data.replace("delchan_", ""))
    bot.send_message(call.message.chat.id, "✅ চ্যানেলটি রিমুভ করা হয়েছে!", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_user_info_start")
def admin_user_info_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔍 <b>ইউজারের তথ্য দেখতে ইউজার ID দিন:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_process_user_lookup)

def admin_process_user_lookup(message):
    try: target_user = int(message.text.strip())
    except ValueError: bot.send_message(message.chat.id, "❌ ভুল ইউজার ID!"); return
    balance = get_balance(target_user)
    total_orders, total_payments = get_user_stats(target_user)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ ব্যালেন্স যোগ", callback_data=f"admbal_ADD_{target_user}"), types.InlineKeyboardButton("✏️ ব্যালেন্স সেট", callback_data=f"admbal_SET_{target_user}"))
    info_text = f"👤 <b>ইউজার অ্যাকাউন্ট</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🆔 <b>ID:</b> <code>{target_user}</code>\n💰 <b>ব্যালেন্স:</b> <b>৳ {balance:.2f} BDT</b>\n🛒 <b>অর্ডার:</b> <b>{total_orders} টি</b>\n💳 <b>ডিপোজিট:</b> <b>{total_payments} টি</b>"
    bot.send_message(message.chat.id, info_text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admbal_"))
def admin_process_balance_action(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    action, target_user = call.data.replace("admbal_", "").split("_")
    target_user = int(target_user)
    if action == "ADD":
        msg = bot.send_message(call.message.chat.id, f"💵 ইউজার <code>{target_user}</code> এর সাথে <b>কত টাকা যোগ করবেন?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, lambda m: [update_balance(target_user, get_balance(target_user) + float(m.text.strip())), bot.send_message(m.chat.id, f"✅ নতুন ব্যালেন্স: <b>৳ {get_balance(target_user):.2f} BDT</b>", parse_mode="HTML")])
    elif action == "SET":
        msg = bot.send_message(call.message.chat.id, f"✏️ ইউজার <code>{target_user}</code> এর <b>নতুন ব্যালেন্স কত সেট করবেন?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, lambda m: [update_balance(target_user, float(m.text.strip())), bot.send_message(m.chat.id, f"✅ ব্যালেন্স সেট হয়েছে: <b>৳ {float(m.text.strip()):.2f} BDT</b>", parse_mode="HTML")])

@bot.callback_query_handler(func=lambda call: call.data == "admin_clear_services_confirm")
def admin_clear_services_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔐 <b>সকল সার্ভিস ডিলিট করতে ৫ ডিজিটের PIN দিন:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_clear_services_pin)

def process_clear_services_pin(message):
    if message.text.strip() == "12345":
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM services")
            cursor.execute("DELETE FROM main_categories")
            cursor.execute("DELETE FROM sub_categories")
            conn.commit()
        bot.send_message(message.chat.id, "🗑️ <b>সকল সার্ভিস সফলভাবে ডিলিট হয়েছে!</b>", parse_mode="HTML")
    else: bot.send_message(message.chat.id, "❌ ভুল পিন কোড!")

# ===================================================

def get_main_menu_markup(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🛒 ORDER SERVICE"),
        types.KeyboardButton("💳 DEPOSIT"),
        types.KeyboardButton("💰 ORDER PRICE"),
        types.KeyboardButton("📜 ORDER HISTORY"),
        types.KeyboardButton("👤 MY PROFILE"),
        types.KeyboardButton("📞 SUPPORT")
    )
    return markup

def get_platforms_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_cats = get_main_categories()
    for i in range(0, len(main_cats), 2):
        if i + 1 < len(main_cats):
            markup.row(types.KeyboardButton(main_cats[i]), types.KeyboardButton(main_cats[i+1]))
        else:
            markup.row(types.KeyboardButton(main_cats[i]))
    markup.row(types.KeyboardButton("⬅️ MAIN MENU"))
    return markup

def get_subcategories_keyboard(main_cat):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    sub_cats = get_sub_categories(main_cat)
    for i in range(0, len(sub_cats), 2):
        if i + 1 < len(sub_cats):
            markup.row(types.KeyboardButton(sub_cats[i]), types.KeyboardButton(sub_cats[i+1]))
        else:
            markup.row(types.KeyboardButton(sub_cats[i]))
    markup.row(types.KeyboardButton("⬅️ BACK"))
    return markup

def enforce_force_join(chat_id):
    unjoined = check_user_joined_all(chat_id)
    if unjoined:
        markup = types.InlineKeyboardMarkup()
        for ch in unjoined: markup.add(types.InlineKeyboardButton(f"📢 Join {ch[1]}", url=ch[2]))
        markup.add(types.InlineKeyboardButton("✅ জয়েন সম্পন্ন করেছি (Verify)", callback_data="verify_channel_joins"))
        bot.send_message(chat_id, "⚠️ <b>বট ব্যবহার করতে নিচের চ্যানেলগুলোতে জয়েন হওয়া বাধ্যতামূলক!</b>", reply_markup=markup, parse_mode="HTML")
        return False
    return True

@bot.callback_query_handler(func=lambda call: call.data == "verify_channel_joins")
def verify_channel_joins_callback(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    if not check_user_joined_all(chat_id):
        bot.send_message(chat_id, "🎉 <b>জয়েনিং ভেরিফাই হয়েছে!</b>", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
    else:
        bot.send_message(chat_id, "❌ <b>আপনি এখনো সবগুলো চ্যানেলে জয়েন করেননি!</b>", parse_mode="HTML")

@bot.message_handler(commands=["start"])
def start_command(message):
    chat_id = message.chat.id
    is_new = add_user(chat_id)
    if is_new:
        try:
            user_disp = get_user_display(chat_id)
            bot.send_message(MAIN_ADMIN_ID, f"👤 <b>নতুন ইউজার যুক্ত হয়েছে!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n🏷️ <b>ইউজারনেম:</b> <b>{user_disp}</b>\n🆔 <b>ইউজার আইডি:</b> <code>{chat_id}</code>", parse_mode="HTML")
        except Exception: pass
    if enforce_force_join(chat_id):
        send_main_menu(chat_id, message.from_user.first_name)

def send_main_menu(chat_id, first_name):
    safe_name = "ইউজার" if not first_name else first_name.replace("<", "&lt;").replace(">", "&gt;")
    custom_welcome = get_setting("welcome_text")
    welcome_text = custom_welcome.replace("{name}", safe_name) if custom_welcome else f"⚡✅ <b>আমাদের প্রিমিয়াম SMM বোটে স্বাগতম!</b> 🥰\n━━━━━━━━━━━━━━━━━━━━━━\nহ্যালো <b>{safe_name}</b>, এখানে আপনি সেরা সোশ্যাল মিডিয়া সার্ভিস পাবেন। 🚀\n\n🛒 <b>অর্ডার করতে বাটন চাপুন:</b> 👇"
    start_photo = get_setting("start_photo")
    if start_photo:
        try: bot.send_photo(chat_id, start_photo, caption=welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
        except Exception: bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
    else: bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

@bot.message_handler(func=lambda message: True)
def handle_menu_buttons(message):
    chat_id = message.chat.id
    if not enforce_force_join(chat_id): return
    text = message.text.strip()

    if text in ["⬅️ MAIN MENU", "❌ CANCEL", "⬅️ প্রধান মেনু", "❌ বাতিল করুন"]:
        clear_user_steps(chat_id)
        USER_STATES.pop(chat_id, None)
        send_main_menu(chat_id, message.from_user.first_name)
        return

    if text == "👤 MY PROFILE":
        balance = get_balance(chat_id)
        bot.send_message(chat_id, f"┏━━━━━━━━━━━━━━━━━━━━┓\n   👤 আমার অ্যাকাউন্ট ড্যাশবোর্ড 👤\n┗━━━━━━━━━━━━━━━━━━━━┛\n\n🆔 আপনার ইউজার আইডি : {chat_id}\n💰 বর্তমান ব্যালেন্স : {balance:.2f} BDT\n━━━━━━━━━━━━━━━━━━━━", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

    elif text in ["🛒 ORDER SERVICE", "⬅️ BACK"]:
        main_cats = get_main_categories()
        if not main_cats: bot.send_message(chat_id, "❌ বর্তমানে কোনো সার্ভিস উপলব্ধ নেই।", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML"); return
        USER_STATES[chat_id] = {"step": "PLATFORMS"}
        bot.send_message(chat_id, "💸 <b>আমাদের সার্ভিস প্ল্যাটফর্ম নির্বাচন করুন:</b>", reply_markup=get_platforms_keyboard(), parse_mode="HTML")

    elif text in get_main_categories():
        USER_STATES[chat_id] = {"step": "SUBCATS", "main_cat": text}
        bot.send_message(chat_id, f"📂 <b>[{text}] সার্ভিস বেছে নিন:</b>", reply_markup=get_subcategories_keyboard(text), parse_mode="HTML")

    elif chat_id in USER_STATES and USER_STATES[chat_id].get("step") == "SUBCATS" and text in get_sub_categories(USER_STATES[chat_id].get("main_cat")):
        main_cat = USER_STATES[chat_id]["main_cat"]
        sub_cat = text
        services_list = get_services_by_sub_cat(main_cat, sub_cat)
        if not services_list: bot.send_message(chat_id, "❌ সার্ভিসের তথ্য পাওয়া যায়নি।", reply_markup=get_subcategories_keyboard(main_cat), parse_mode="HTML"); return
        selected_service = services_list[0]
        USER_STATES[chat_id] = {"step": "ENTER_QUANTITY", "main_cat": main_cat, "sub_cat": sub_cat, "service": selected_service}
        desc_text = f"\n{selected_service['description']}\n" if selected_service['description'] else ""
        msg = bot.send_message(chat_id, f"👑 <b>SERVICE: {sub_cat}</b>\n💰 <b>রেট:</b> {selected_service['price_per_1k']:.2f} BDT (প্রতি ১০০০ টি)\n🔢 <b>সর্বনিম্ন কোয়ান্টিটি:</b> {selected_service['min_qty']} টি\n{desc_text}\n👉 <b>কত কোয়ান্টিটি (Quantity) নিতে চান? সংখ্যাটি লিখে পাঠান:</b>", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_step_quantity, selected_service)

    elif text == "💳 DEPOSIT":
        clear_user_steps(chat_id)
        msg = bot.send_message(chat_id, "💵 <b>কত টাকা (BDT) রিচার্জ করতে চান? পরিমাণ লিখে পাঠান:</b>\n\n<i>(সর্বনিম্ন রিচার্জ পরিমাণ ১০ টাকা)</i>", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ MAIN MENU"), parse_mode="HTML")
        bot.register_next_step_handler(msg, get_intended_deposit_amount)

    elif text == "💰 ORDER PRICE":
        bot.send_message(chat_id, get_price_list_text(), reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

    elif text == "📜 ORDER HISTORY":
        msg_loading = bot.send_message(chat_id, "⏳ <b>অর্ডার হিস্ট্রি লোড হচ্ছে...</b>", parse_mode="HTML")
        orders = get_user_orders(chat_id)
        if not orders: bot.edit_message_text("📭 <b>আপনি এখনো কোনো অর্ডার করেননি।</b>", chat_id=chat_id, message_id=msg_loading.message_id, parse_mode="HTML"); return
        statuses = get_multiple_orders_status([o[0] for o in orders])
        response = "📋 <b>আপনার সর্বশেষ ৫টি অর্ডার এবং লাইভ স্ট্যাটাস:</b>\n\n"
        for idx, o in enumerate(orders, 1):
            st = statuses.get(str(o[0]), {}).get("status", "Processing") if isinstance(statuses, dict) else "Processing"
            response += f"<b>{idx}. {o[1]}</b>\n🆔 <b>ID:</b> <code>{o[0]}</code>\n🔢 <b>Qty:</b> <b>{o[2]}</b> | 💵 <b>খরচ:</b> <b>৳ {o[3]:.2f} BDT</b>\n🚦 <b>স্ট্যাটাস:</b> <b>{st}</b>\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        bot.edit_message_text(response, chat_id=chat_id, message_id=msg_loading.message_id, parse_mode="HTML")

    elif text == "📞 SUPPORT":
        bot.send_message(chat_id, f"┏━━━━━━━━━━━━━━━━━━┓\n       📞   <b>গ্রাহক সাপোর্ট</b>   📞\n┗━━━━━━━━━━━━━━━━━━┛\n\n💬 <b>টেলিগ্রাম এডমিন:</b> {get_support_username()}\n📱 <b>হোয়াটসঅ্যাপ/ফোন:</b> {get_support_phone()}\n\nযেকোনো সমস্যার জন্য যোগাযোগ করুন।", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

def process_order_step_quantity(message, selected_service):
    chat_id = message.chat.id
    quantity_input = message.text.strip()
    main_cat = selected_service.get('main_cat')
    if quantity_input in ["❌ CANCEL", "⬅️ MAIN MENU", "❌ বাতিল করুন"]:
        if main_cat:
            USER_STATES[chat_id] = {"step": "SUBCATS", "main_cat": main_cat}
            bot.send_message(chat_id, f"📂 <b>[{main_cat}] সার্ভিস বেছে নিন:</b>", reply_markup=get_subcategories_keyboard(main_cat), parse_mode="HTML")
        else: send_main_menu(chat_id, message.from_user.first_name)
        return
    if not quantity_input.isdigit():
        msg = bot.send_message(chat_id, "🛑 <b>ভুল সংখ্যা! শুধুমাত্র সংখ্যা টাইপ করুন।</b>", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_step_quantity, selected_service)
        return

    quantity = int(quantity_input)
    min_qty = selected_service.get('min_qty', 10)
    if quantity < min_qty:
        msg = bot.send_message(chat_id, f"❌ <b>সর্বনিম্ন {min_qty} টি অর্ডার করতে হবে!</b> আবার লিখুন:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_step_quantity, selected_service)
        return

    msg = bot.send_message(chat_id, "🔗 <b>অর্ডারের লিংকটি পেস্ট করে পাঠান:</b>", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
    bot.register_next_step_handler(msg, process_order_step_link, selected_service, quantity)

def process_order_step_link(message, selected_service, quantity):
    chat_id = message.chat.id
    link = message.text.strip()
    main_cat = selected_service.get('main_cat')
    if link in ["❌ CANCEL", "⬅️ MAIN MENU", "❌ বাতিল করুন"]:
        if main_cat:
            USER_STATES[chat_id] = {"step": "SUBCATS", "main_cat": main_cat}
            bot.send_message(chat_id, f"📂 <b>[{main_cat}] সার্ভিস বেছে নিন:</b>", reply_markup=get_subcategories_keyboard(main_cat), parse_mode="HTML")
        else: send_main_menu(chat_id, message.from_user.first_name)
        return
    if not link.startswith("http"):
        msg = bot.send_message(chat_id, "🛑 <b>ভুল লিংক! সঠিক লিংক দিন।</b>", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_step_link, selected_service, quantity)
        return

    rate = selected_service.get("price_per_1k", 0.0) or 10.0
    estimated_cost = max((quantity / 1000) * rate, 1.0)
    user_balance = get_balance(chat_id)
    if user_balance < estimated_cost:
        markup = get_subcategories_keyboard(main_cat) if main_cat else get_main_menu_markup(chat_id)
        bot.send_message(chat_id, f"❌ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\nমূল্য: <b>৳ {estimated_cost:.2f} BDT</b> | ব্যালেন্স: <b>৳ {user_balance:.2f} BDT</b>", reply_markup=markup, parse_mode="HTML")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("✅ CONFIRM", "❌ CANCEL")
    msg = bot.send_message(chat_id, f"💵 <b>অর্ডার মূল্য: ৳ {estimated_cost:.2f} BDT</b>\n\nসাবমিট করতে <b>'✅ CONFIRM'</b> চাপুন:", reply_markup=markup, parse_mode="HTML")
    bot.register_next_step_handler(msg, confirm_order_final, selected_service, link, quantity, estimated_cost)

def confirm_order_final(message, selected_service, link, quantity, estimated_cost):
    chat_id = message.chat.id
    user_choice = message.text.strip()
    main_cat = selected_service.get('main_cat')
    if main_cat:
        USER_STATES[chat_id] = {"step": "SUBCATS", "main_cat": main_cat}
        stay_markup = get_subcategories_keyboard(main_cat)
    else: stay_markup = get_main_menu_markup(chat_id)

    if user_choice in ["✅ CONFIRM", "✅ কনফার্ম করুন"]:
        user_balance = get_balance(chat_id)
        if user_balance < estimated_cost:
            bot.send_message(chat_id, "❌ <b>পর্যাপ্ত ব্যালেন্স নেই।</b>", reply_markup=stay_markup, parse_mode="HTML")
            return
        payload = {"key": get_smm_api_key(), "action": "add", "service": selected_service["api_id"], "link": link, "quantity": quantity}
        try:
            response = requests.post(get_smm_api_url(), data=payload)
            api_res = response.json()
            if isinstance(api_res, dict) and "order" in api_res:
                new_balance = user_balance - estimated_cost
                update_balance(chat_id, new_balance)
                add_order_to_db(api_res["order"], chat_id, selected_service["name"], quantity, estimated_cost)
                success_text = f"✅ <b>অর্ডার সফল হয়েছে!</b>\n\n📌 <b>সার্ভিস:</b> {selected_service['name']}\n🔢 <b>কোয়ান্টিটি:</b> {quantity}\n💳 <b>খরচ:</b> <b>৳ {estimated_cost:.2f} BDT</b>\n💰 <b>অবশিষ্ট ব্যালেন্স:</b> <b>৳ {new_balance:.2f} BDT</b>\n🆔 <b>অর্ডার আইডি:</b> <code>{api_res['order']}</code> ✅"
                note = get_order_success_note()
                if note: success_text += f"\n\n📝 <b>নোট:</b>\n{note}"
                bot.send_message(chat_id, success_text, reply_markup=stay_markup, parse_mode="HTML")
                
                log_chan = get_log_channel_id()
                if log_chan:
                    try:
                        user_disp = get_user_display(chat_id)
                        bot.send_message(log_chan, f"📦 <b>NEW ORDER!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n👤 <b>ইউজারনেম:</b> <b>{user_disp}</b>\n🆔 <b>অর্ডার ID:</b> <code>{api_res['order']}</code>\n📌 <b>সার্ভিস:</b> <b>{selected_service['name']}</b>\n🔢 <b>Qty:</b> <b>{quantity} টি</b>\n💵 <b>মূল্য:</b> <b>৳ {estimated_cost:.2f} BDT</b>\n🔗 <b>লিংক:</b> Private", parse_mode="HTML")
                    except Exception: pass
            else:
                err = api_res.get("error", "Server error") if isinstance(api_res, dict) else "Invalid response"
                bot.send_message(chat_id, f"❌ <b>অর্ডার ব্যর্থ:</b> {err}", reply_markup=stay_markup, parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, "❌ <b>সার্ভার সংযোগে ত্রুটি!</b>", reply_markup=stay_markup, parse_mode="HTML")
    else:
        bot.send_message(chat_id, "❌ <b>অর্ডার বাতিল করা হয়েছে।</b>", reply_markup=stay_markup, parse_mode="HTML")

def get_intended_deposit_amount(message):
    chat_id = message.chat.id
    amount_str = message.text.strip()
    if amount_str in ["⬅️ MAIN MENU", "⬅️ প্রধান মেনু"]:
        clear_user_steps(chat_id)
        send_main_menu(chat_id, message.from_user.first_name)
        return
    try:
        intended_amount = float(amount_str)
        if intended_amount < 10.0:
            msg = bot.send_message(chat_id, "❌ <b>সর্বনিম্ন ১০ টাকা রিচার্জ করতে হবে!</b> আবার লিখুন:", parse_mode="HTML")
            bot.register_next_step_handler(msg, get_intended_deposit_amount)
            return
        
        web_app_url = f"{get_bot_domain()}/payment-page?bdt={intended_amount}&bkash={get_bkash_number()}&nagad={get_nagad_number()}"
        msg_text = (
            "┏━━━━━━━━━━━━━━━━━━━━┓\n"
            "   🪙 <b>অটো রিচার্জ প্যানেল</b> 🪙\n"
            "┗━━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"💵 <b>রিচার্জ পরিমাণ:</b> <b>{intended_amount:.2f} BDT</b>\n"
            "⚠️ <b>সর্বনিম্ন রিচার্জ পরিমাণ:</b> <b>১০ টাকা</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💳 <b>পেমেন্ট মাধ্যম:</b> বিকাশ / নগদ / বাইনান্স পে\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ <b>নির্দেশনা:</b>\n"
            "পেমেন্ট সম্পন্ন করতে নিচে থাকা <b>'💳 CLICK TO PAY'</b> বাটনে ক্লিক করুন। সেখানে বিকাশ, নগদ ও বাইনান্স পে-এর নাম্বার পেয়ে যাবেন। টাকা পাঠিয়ে TrxID/Order ID দিয়ে ভেরিফাই করলেই অ্যাকাউন্টে ব্যালেন্স স্বয়ংক্রিয়ভাবে যোগ হবে।\n\n"
            "👇 <b>রিচার্জ করতে নিচের বাটনে ক্লিক করুন:</b>"
        )
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        try: markup.add(types.KeyboardButton("💳 CLICK TO PAY", web_app=types.WebAppInfo(url=web_app_url)))
        except Exception: markup.add(types.KeyboardButton("💳 CLICK TO PAY"))
        markup.add("⬅️ MAIN MENU")
        bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.send_message(chat_id, f"❌ <b>ভুল ইনপুট! শুধু সংখ্যা লিখুন:</b>", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

def start_bot_polling():
    while True:
        try: bot.polling(none_stop=True, skip_pending=True, timeout=60)
        except Exception: time.sleep(5)

if __name__ == "__main__":
    print("🤖 SMM BOT IS RUNNING...")
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    time.sleep(2)
    start_bot_polling()
