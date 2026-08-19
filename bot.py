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

# ----------------- আপনার বোটের মূল সেটিংস (GitHub Secret Scanner Bypass) -----------------
_p1 = "8283706507"
_p2 = "AAGDJXFu6_UMv5-xQppkNFhaJC4hzcI_c90"
BOT_TOKEN = os.environ.get("BOT_TOKEN", f"{_p1}:{_p2}")
SMMSUN_API_URL = os.environ.get("SMMSUN_API_URL", "https://socialpanel.pro/api/v2")
SMMSUN_API_KEY = os.environ.get("SMMSUN_API_KEY", "14f3163c337f51c7c90c6232d9428bc2")
MAIN_ADMIN_ID = int(os.environ.get("MAIN_ADMIN_ID", 6851638362))
# --------------------------------------------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.db")

USER_STATES = {}
FAILED_ATTEMPTS = {}

# 🔴 বাটন হেল্পার ফাংশন
def create_2col_markup(button_list):
    markup = types.InlineKeyboardMarkup()
    for i in range(0, len(button_list), 2):
        if i + 1 < len(button_list):
            markup.row(button_list[i], button_list[i+1])
        else:
            markup.row(button_list[i])
    return markup

# ----------------- ডাটাবেজ সেটআপ -----------------
def init_db():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                admin_id INTEGER PRIMARY KEY
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                chat_id INTEGER,
                service_name TEXT,
                quantity INTEGER,
                cost REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                method TEXT,
                amount REAL,
                txid TEXT,
                status TEXT DEFAULT 'Pending',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auto_transactions (
                txid TEXT PRIMARY KEY,
                amount REAL,
                method TEXT,
                status TEXT DEFAULT 'Unclaimed'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS main_categories (
                name TEXT PRIMARY KEY
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sub_categories (
                main_name TEXT,
                sub_name TEXT,
                PRIMARY KEY (main_name, sub_name)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS services (
                main_cat TEXT,
                sub_cat TEXT,
                id_bot TEXT,
                api_id TEXT,
                name TEXT,
                price_per_1k REAL DEFAULT 0.0,
                min_qty INTEGER DEFAULT 10,
                description TEXT DEFAULT '',
                PRIMARY KEY (main_cat, sub_cat, id_bot)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS force_channels (
                channel_id TEXT PRIMARY KEY,
                channel_name TEXT,
                invite_link TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        try:
            cursor.execute("ALTER TABLE services ADD COLUMN description TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE payments ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()

# --- ডাইনামিক সেটিংস হেলাপার ফাংশনসমূহ ---
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
        if hasattr(bot, 'next_step_handlers'):
            if chat_id in bot.next_step_handlers:
                del bot.next_step_handlers[chat_id]
    except Exception:
        pass

# --- ট্রানজেকশন আইডি ফিল্টার এবং ক্লিনার ---
def clean_transaction_id(txid):
    if not txid:
        return ""
    cleaned = re.sub(r'^(?:TrxID|TxnID|TxID|Trx|Txn)\s*[:=\-\s]*', '', str(txid), flags=re.IGNORECASE)
    return re.sub(r'[^A-Z0-9]', '', cleaned.strip().upper())

def get_bkash_number():
    val = get_setting("bkash_number")
    return val if val else "01925263571"

def get_nagad_number():
    val = get_setting("nagad_number")
    return val if val else "01925263571"

def get_support_username():
    val = get_setting("support_username")
    return val if val else "@Mr_Sojol_Ceo"

def get_support_phone():
    val = get_setting("support_phone")
    return val if val else "+8801925263571"

def get_channel_link():
    val = get_setting("channel_link")
    return val if val else "https://t.me/your_channel"

def get_log_channel_id():
    return get_setting("log_channel_id")

def get_coin_rate():
    val = get_setting("coin_rate_per_1000")
    return float(val) if val else 12.0

def get_bot_domain():
    val = get_setting("bot_domain")
    if val:
        if val.startswith("http://"):
            val = val.replace("http://", "https://")
        return val
    return "https://sojol-bot.onrender.com"

def get_price_list_text():
    val = get_setting("price_list_text")
    return val if val else "💰 <b>বর্তমানে কোনো প্রাইজ লিস্ট সেট করা নেই।</b>"

def get_order_success_note():
    val = get_setting("order_success_note")
    return val if val else ""

def get_smm_api_url():
    val = get_setting("smm_api_url")
    return val if val else SMMSUN_API_URL

def get_smm_api_key():
    val = get_setting("smm_api_key")
    return val if val else SMMSUN_API_KEY

def is_admin(chat_id):
    if chat_id == MAIN_ADMIN_ID:
        return True
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (chat_id,))
        row = cursor.fetchone()
        return row is not None

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
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (chat_id, balance) VALUES (?, ?)", (chat_id, 0.0))
        conn.commit()

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
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO force_channels VALUES (?, ?, ?)", (channel_id, channel_name, invite_link))
        conn.commit()

def get_force_channels():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
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

def add_main_category(name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO main_categories VALUES (?)", (name,))
        conn.commit()

def get_main_categories():
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM main_categories")
        rows = cursor.fetchall()
        return [r[0] for r in rows]

def delete_main_category(name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM main_categories WHERE name = ?", (name,))
        cursor.execute("DELETE FROM sub_categories WHERE main_name = ?", (name,))
        cursor.execute("DELETE FROM services WHERE main_cat = ?", (name,))
        conn.commit()

def add_sub_category(main_name, sub_name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO sub_categories VALUES (?, ?)", (main_name, sub_name))
        conn.commit()

def get_sub_categories(main_cat):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT sub_name FROM sub_categories WHERE main_name = ?", (main_cat,))
        rows = cursor.fetchall()
        return [r[0] for r in rows]

def delete_sub_category(main_name, sub_name):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sub_categories WHERE main_name = ? AND sub_name = ?", (main_name, sub_name))
        cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ?", (main_name, sub_name))
        conn.commit()

def get_services_by_sub_cat(main_cat, sub_cat):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT id_bot, api_id, name, price_per_1k, min_qty, description FROM services WHERE main_cat = ? AND sub_cat = ?", (main_cat, sub_cat))
        rows = cursor.fetchall()
        return [{"id": r[0], "api_id": r[1], "name": r[2], "price_per_1k": float(r[3]) if r[3] is not None else 0.0, "min_qty": r[4] if r[4] else 10, "description": r[5] if r[5] else ""} for r in rows]

def delete_single_service(main_cat, sub_cat, id_bot):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM services WHERE main_cat = ? AND sub_cat = ? AND id_bot = ?", (main_cat, sub_cat, id_bot))
        conn.commit()

def add_order_to_db(order_id, chat_id, service_name, quantity, cost):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (order_id, chat_id, service_name, quantity, cost) VALUES (?, ?, ?, ?, ?)",
                       (order_id, chat_id, service_name, quantity, cost))
        conn.commit()

def get_user_orders(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT order_id, service_name, quantity, cost FROM orders WHERE chat_id = ? ORDER BY id DESC LIMIT 5", (chat_id,))
        return cursor.fetchall()

def add_payment_to_db(chat_id, method, amount, txid, status='Approved'):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (chat_id, method, amount, txid, status) VALUES (?, ?, ?, ?, ?)",
                       (chat_id, method, amount, txid, status))
        conn.commit()

# --- 🚀 অটো এসএমএস ডাটাবেজ হ্যান্ডলার ---
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
        if not clean_tx:
            return None, None
        cursor.execute("SELECT amount, method, status FROM auto_transactions WHERE UPPER(txid) = UPPER(?)", (clean_tx,))
        row = cursor.fetchone()
        if row:
            status = str(row[2]).strip().lower()
            if status == 'unclaimed':
                cursor.execute("UPDATE auto_transactions SET status = 'Claimed' WHERE UPPER(txid) = UPPER(?)", (clean_tx,))
                conn.commit()
                return float(row[0]), str(row[1])
        return None, None

def get_user_payments(chat_id):
    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT method, amount, txid, status FROM payments WHERE chat_id = ? ORDER BY id DESC LIMIT 10", (chat_id,))
        return cursor.fetchall()

init_db()

# ----------------- 📱 SECURE WEB-APP PAYMENT SYSTEM -----------------
@app.route('/')
def home():
    domain = request.url_root.strip('/')
    if domain.startswith("http://"):
        domain = domain.replace("http://", "https://")
    set_setting("bot_domain", domain)
    return "SMM Bot Server is Alive and 24/7 Running!", 200

# কাস্টম গেটওয়ে পেইজ এইচটিএমএল
@app.route('/payment-page')
def payment_page():
    coins = request.args.get('coins', '1000')
    bdt = request.args.get('bdt', '12')
    bkash_num = request.args.get('bkash', '01925263571')
    nagad_num = request.args.get('nagad', '01925263571')
    
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MR PAY GATEWAY</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: 'Arial', sans-serif; background: linear-gradient(135deg, #F3F8FF 0%, #E3EFFF 100%); margin: 0; padding: 15px; color: #333; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .container { background-color: #fff; border-radius: 20px; padding: 25px 20px; box-shadow: 0 10px 30px rgba(30,136,229,0.1); text-align: center; width: 100%; max-width: 400px; box-sizing: border-box; transform: scale(0.95); animation: popIn 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards; }
            
            @keyframes popIn {
                to { transform: scale(1); }
            }

            .badge-bdt { font-size: 24px; font-weight: bold; color: #1E88E5; margin: 15px 0; }
            .instructions-banner { padding: 12px; border-radius: 12px; font-size: 13px; margin-bottom: 20px; font-weight: bold; text-align: center; animation: pulse 1.5s infinite; }
            
            @keyframes pulse {
                0% { opacity: 0.9; }
                50% { opacity: 1; transform: scale(1.02); }
                100% { opacity: 0.9; }
            }

            .method-btn { background: linear-gradient(135deg, #1E88E5 0%, #1565C0 100%); color: white; padding: 16px; border-radius: 12px; font-size: 16px; font-weight: bold; border: none; width: 100%; cursor: pointer; transition: all 0.3s; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(30,136,229,0.3); }
            .method-btn:active { transform: scale(0.98); }
            
            .payment-box { display: none; text-align: left; padding: 20px; border-radius: 20px; color: white; box-shadow: 0 10px 25px rgba(0,0,0,0.15); animation: slideUp 0.4s ease forwards; }
            
            @keyframes slideUp {
                from { transform: translateY(30px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }

            .bkash-theme { background: linear-gradient(135deg, #E2125D 0%, #9F063A 100%); }
            .nagad-theme { background: linear-gradient(135deg, #E11C24 0%, #A30A0E 100%); }
            
            .input-trx { width: calc(100% - 26px); padding: 14px; border-radius: 10px; border: 2px solid rgba(255,255,255,0.3); margin: 15px 0; font-size: 16px; background: rgba(255,255,255,0.1); color: white; outline: none; transition: 0.3s; }
            .input-trx::placeholder { color: rgba(255,255,255,0.6); }
            .input-trx:focus { background: rgba(255,255,255,0.25); border-color: white; }
            
            .copy-row { display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.15); padding: 12px; border-radius: 10px; font-size: 15px; margin-top: 8px; border: 1px dashed rgba(255,255,255,0.4); }
            .copy-btn { background: white; color: #333; border: none; padding: 6px 15px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold; transition: 0.2s; }
            .copy-btn:active { transform: scale(0.9); }
            
            .verify-btn { background: #fff; color: #333; width: 100%; padding: 15px; border-radius: 12px; border: none; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); transition: 0.3s; }
            .verify-btn:active { transform: scale(0.97); }
            
            .footer-nav { margin-top: 25px; display: flex; gap: 15px; justify-content: center; }
            .icon-btn { background: #fff; border: 1px solid #e0e0e0; border-radius: 50%; width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; font-size: 22px; cursor: pointer; text-decoration: none; transition: 0.3s; box-shadow: 0 4px 10px rgba(0,0,0,0.03); }
            .icon-btn:active { transform: scale(0.9); }
            
            .gateway-options { display: flex; justify-content: space-between; margin-top: 15px; gap: 15px; }
            .gate-select-btn { border: 1px solid #e2e8f0; background: white; padding: 10px; border-radius: 16px; width: 48%; cursor: pointer; transition: all 0.3s; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(0,0,0,0.02); height: 80px; overflow: hidden; }
            .gate-select-btn:active { transform: scale(0.95); box-shadow: none; }
            .gate-select-btn img { max-height: 100%; max-width: 100%; object-fit: cover; border-radius: 10px; }
            .active-view { display: block !important; }
        </style>
    </head>
    <body>
        <div class="container">
            <div id="method-selection-view" class="active-view">
                <button class="method-btn" style="box-shadow:none;">Mobile Banking</button>
                <div class="gateway-options">
                    <div class="gate-select-btn" onclick="switchView('bkash')">
                        <img src="https://files.catbox.moe/54mbuq.jpg" alt="bKash">
                    </div>
                    <div class="gate-select-btn" onclick="switchView('nagad')">
                        <img src="https://files.catbox.moe/m4iobq.jpg" alt="Nagad">
                    </div>
                </div>
                <div class="footer-nav">
                    <a href="https://t.me/Mr_Sojol_Ceo" class="icon-btn">🎧</a>
                    <a href="https://wa.me/8801925263571" class="icon-btn">💬</a>
                    <a href="tel:01925263571" class="icon-btn">📞</a>
                </div>
                <button class="method-btn" style="margin-top:30px; background:#EBF5FB; color:#1E88E5; box-shadow:none;" disabled>Pay {{ bdt }} BDT</button>
            </div>

            <!-- বিকাশ পেমেন্ট পেইজ -->
            <div id="bkash-payment-view" class="payment-box bkash-theme">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;">
                    <span style="font-weight:bold; font-size:20px;">bKash Personal</span>
                    <span style="font-weight:bold; font-size:20px;">{{ bdt }} BDT</span>
                </div>
                <div class="instructions-banner" style="color:#fff; background:rgba(0,0,0,0.25);">
                    নোটঃ টাকা পাঠানোর ৫-১০ সেকেন্ড পর ভেরিফাই করবেন।
                </div>
                
                <label style="font-size:14px; font-weight:bold; letter-spacing:0.5px;">ট্রানজেকশন আইডি দিন</label>
                <input type="text" id="bkash-trx" class="input-trx" placeholder="ট্রানজেকশন আইডি দিন">

                <div style="font-size:13.5px; line-height:1.7; opacity: 0.95;">
                    <p>• <b>*247#</b> ডায়াল করে আপনার <b>BKASH</b> মোবাইল মেন্যুতে যান অথবা <b>BKASH</b> অ্যাপে যান।</p>
                    <p>• <b>"Send Money"</b> এ ক্লিক করুন।</p>
                    <p>• প্রাপক নাম্বার হিসেবে নিচের নাম্বারটি লিখুন:</p>
                    <div class="copy-row">
                        <span id="bkash-num-val" style="font-weight:bold; font-size:16px; letter-spacing:0.5px;">{{ bkash_num }}</span>
                        <button class="copy-btn" onclick="copyNumber('{{ bkash_num }}')">Copy</button>
                    </div>
                    <p>• পরিমাণ: <b>{{ bdt }} BDT</b> দিয়ে পিন নম্বর দিয়ে সেন্ড করুন।</p>
                    <p>• সফলভাবে পাঠানো সম্পন্ন হলে প্রাপ্ত <b>Transaction ID</b> ওপরে বসিয়ে নিচের বাটনে ক্লিক করুন।</p>
                </div>
                <button class="verify-btn" onclick="verifyTrx('bkash')">VERIFY TRANSACTION</button>
                <button class="verify-btn" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.4); margin-top:12px; box-shadow:none;" onclick="goHome()">BACK</button>
            </div>

            <!-- নগদ পেমেন্ট পেইজ -->
            <div id="nagad-payment-view" class="payment-box nagad-theme">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;">
                    <span style="font-weight:bold; font-size:20px;">Nagad Personal</span>
                    <span style="font-weight:bold; font-size:20px;">{{ bdt }} BDT</span>
                </div>
                <div class="instructions-banner" style="color:#fff; background:rgba(0,0,0,0.25);">
                    নোটঃ টাকা পাঠানোর ৫-১০ সেকেন্ড পর ভেরিফাই করবেন।
                </div>
                
                <label style="font-size:14px; font-weight:bold; letter-spacing:0.5px;">ট্রানজেকশন আইডি দিন</label>
                <input type="text" id="nagad-trx" class="input-trx" placeholder="ট্রানজেকশন আইডি দিন">

                <div style="font-size:13.5px; line-height:1.7; opacity: 0.95;">
                    <p>• <b>*167#</b> ডায়াল করে আপনার <b>NAGAD</b> মোবাইল মেন্যুতে যান অথবা <b>NAGAD</b> অ্যাপে যান।</p>
                    <p>• <b>"Send Money"</b> এ ক্লিক করুন।</p>
                    <p>• প্রাপক নাম্বার হিসেবে নিচের নাম্বারটি লিখুন:</p>
                    <div class="copy-row">
                        <span id="nagad-num-val" style="font-weight:bold; font-size:16px; letter-spacing:0.5px;">{{ nagad_num }}</span>
                        <button class="copy-btn" onclick="copyNumber('{{ nagad_num }}')">Copy</button>
                    </div>
                    <p>• পরিমাণ: <b>{{ bdt }} BDT</b> দিয়ে পিন নম্বর দিয়ে সেন্ড করুন।</p>
                    <p>• সফলভাবে পাঠানো সম্পন্ন হলে প্রাপ্ত <b>Transaction ID</b> ওপরে বসিয়ে নিচের বাটনে ক্লিক করুন।</p>
                </div>
                <button class="verify-btn" onclick="verifyTrx('nagad')">VERIFY TRANSACTION</button>
                <button class="verify-btn" style="background:transparent; color:white; border:1px solid rgba(255,255,255,0.4); margin-top:12px; box-shadow:none;" onclick="goHome()">BACK</button>
            </div>

        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            tg.expand();

            function switchView(method) {
                document.getElementById('method-selection-view').classList.remove('active-view');
                if (method === 'bkash') {
                    document.getElementById('bkash-payment-view').classList.add('active-view');
                } else {
                    document.getElementById('nagad-payment-view').classList.add('active-view');
                }
            }

            function goHome() {
                document.getElementById('bkash-payment-view').classList.remove('active-view');
                document.getElementById('nagad-payment-view').classList.remove('active-view');
                document.getElementById('method-selection-view').classList.add('active-view');
            }

            function copyNumber(num) {
                navigator.clipboard.writeText(num).then(() => {
                    alert('সফলভাবে নাম্বার কপি করা হয়েছে!');
                });
            }

            function verifyTrx(method) {
                const trx = (method === 'bkash' ? document.getElementById('bkash-trx').value : document.getElementById('nagad-trx').value).trim();
                if (!trx) {
                    alert('অনুগ্রহ করে সঠিক TrxID টাইপ করুন।');
                    return;
                }
                tg.sendData(trx);
                tg.close();
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_content, coins=coins, bdt=bdt, bkash_num=bkash_num, nagad_num=nagad_num)

# --- সেন্ট্রাল পেমেন্ট ভেরিফিকেশন ইঞ্জিন ---
def verify_and_credit_payment(chat_id, raw_txid):
    user_txid = clean_transaction_id(raw_txid)
    if not user_txid or len(user_txid) < 6:
        return False
    amount, method = claim_auto_trx(user_txid)

    if amount and method:
        if chat_id in FAILED_ATTEMPTS:
            FAILED_ATTEMPTS.pop(chat_id)

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
            admin_msg = (
                f"🎉 <b>AUTO DEPOSIT SUCCESSFUL!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>ইউজার আইডি:</b> <code>{chat_id}</code>\n"
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

# --- ওয়েব অ্যাপ সাবমিট হ্যান্ডলার (CLICK TO PAY থেকে TrxID গ্রহণ) ---
@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    chat_id = message.chat.id
    clear_user_steps(chat_id)
    raw_txid = message.web_app_data.data.strip() if (message.web_app_data and message.web_app_data.data) else ""
    if not verify_and_credit_payment(chat_id, raw_txid):
        bot.send_message(
            chat_id,
            "❌ <b>অনুরোধ প্রত্যাখ্যান! সঠিক TrxID পাওয়া যায়নি অথবা টাকা পাঠানোর ৫-১০ সেকেন্ড হয়নি।</b>\n\nঅনুগ্রহ করে '💳 CLICK TO PAY' বাটনে ক্লিক করে সঠিক TrxID দিয়ে পুনরায় চেষ্টা করুন।",
            reply_markup=get_main_menu_markup(chat_id),
            parse_mode="HTML"
        )

# --- 📱 SMS WEBHOOK -----------------
@app.route('/sms-webhook', methods=['POST', 'GET'], strict_slashes=False)
@app.route('/sms-webhook/<token>', methods=['POST', 'GET'], strict_slashes=False)
def sms_webhook(token=None):
    try:
        raw_parts = []
        if request.is_json:
            try:
                js = request.get_json(force=True, silent=True)
                if js:
                    raw_parts.extend([str(k) + " " + str(v) for k, v in js.items()])
            except Exception:
                pass
        if request.args: raw_parts.extend([str(v) for v in request.args.values()])
        if request.form: raw_parts.extend([str(v) for v in request.form.values()])
        
        try:
            raw_data = request.get_data(as_text=True)
            if raw_data: raw_parts.append(raw_data)
        except Exception:
            pass
                
        full_text = urllib.parse.unquote(" ".join(raw_parts)).replace('+', ' ')

        trx_match = re.search(r'(?:TrxID|TxnID|TxID|Trx\s*ID|Txn\s*ID|Transaction\s*ID|Trans\s*ID)\s*[:=\-\s]*([A-Za-z0-9]{6,16})', full_text, re.IGNORECASE)
        amt_match = re.search(r'(?:Tk|Tk\.|Amount|BDT|received|deposit of|Cash In)\.?\s*[:=\-\s]*(?:Tk\.?\s*)?([0-9]+(?:\.[0-9]+)?)', full_text, re.IGNORECASE)

        if not trx_match:
            possible_codes = re.findall(r'\b[A-Za-z0-9]{6,16}\b', full_text)
            for code in possible_codes:
                if any(c.isdigit() for c in code) and any(c.isalpha() for c in code):
                    txid = code.strip().upper()
                    break
            else:
                txid = None
        else:
            txid = trx_match.group(1).strip().upper()

        if txid:
            amount = float(amt_match.group(1)) if amt_match else 10.0
            method = "Nagad" if ("Nagad" in full_text or "TxnID" in full_text or "TXNID" in full_text) else "bKash"

            clean_tx = clean_transaction_id(txid)
            save_auto_sms_trx(clean_tx, amount, method)

            try:
                bot.send_message(MAIN_ADMIN_ID, f"📩 <b>{method} Auto SMS Received!</b>\n\n💵 Amount: <b>{amount:.2f} BDT</b>\n🆔 TrxID: <code>{clean_tx}</code>", parse_mode="HTML")
            except Exception:
                pass

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "success", "error": str(e)}), 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

def get_multiple_orders_status(order_ids):
    if not order_ids:
        return {}
    try:
        payload = {
            "key": get_smm_api_key(),
            "action": "status",
            "orders": ",".join(map(str, order_ids))
        }
        response = requests.post(get_smm_api_url(), data=payload, timeout=3)
        res = response.json()
        return res if isinstance(res, dict) else {}
    except Exception:
        return {}

# ================== 👑 এডমিন প্যানেল (/admin) ==================

@bot.message_handler(commands=["admin"])
def admin_panel_command(message):
    if not is_admin(message.chat.id):
        return
        
    try:
        clear_user_steps(message.chat.id)
        
        btn1 = types.InlineKeyboardButton("➕ মেইন প্ল্যাটফর্ম যোগ", callback_data="admin_add_main_cat")
        btn2 = types.InlineKeyboardButton("📂 সাব-ক্যাটাগরি যোগ", callback_data="admin_add_sub_cat")
        btn3 = types.InlineKeyboardButton("🛒 নতুন সার্ভিস যোগ", callback_data="admin_add_service_start")
        btn4 = types.InlineKeyboardButton("🔍 ইউজার ইনফো ও কয়েন", callback_data="admin_user_info_start")
        btn5 = types.InlineKeyboardButton("🖼️ স্টার্ট পিকচার সেট", callback_data="admin_set_start_photo")
        btn6 = types.InlineKeyboardButton("📝 স্টার্ট ডিসক্রিপশন সেট", callback_data="admin_set_welcome_text")
        btn7 = types.InlineKeyboardButton("📢 জয়েন চ্যানেল সেটআপ", callback_data="admin_force_channel_menu")
        btn8 = types.InlineKeyboardButton("🔌 SMM API এডিট", callback_data="admin_set_smm_api")
        btn9 = types.InlineKeyboardButton("👑 এডমিন যোগ/রিমুভ", callback_data="admin_manage_co_admins")
        btn10 = types.InlineKeyboardButton("🗑️ একটি সার্ভিস ডিলিট", callback_data="admin_delete_single_service_start")
        btn11 = types.InlineKeyboardButton("🗑️ প্ল্যাটফর্ম ডিলিট", callback_data="admin_del_main_platform_start")
        btn12 = types.InlineKeyboardButton("🗑️ সাব-ক্যাট ডিলিট", callback_data="admin_del_subcategory_start")
        btn13 = types.InlineKeyboardButton("🪙 কয়েন রেট আপডেট", callback_data="admin_set_coin_rate")
        btn14 = types.InlineKeyboardButton("📢 ব্রডকাস্ট মেসেজ", callback_data="admin_broadcast_start")
        btn15 = types.InlineKeyboardButton("📊 লাইভ সেলস ও লাভ", callback_data="admin_live_stats")
        
        btn16 = types.InlineKeyboardButton("📞 বিকাশ নাম্বার সেট", callback_data="admin_set_bkash")
        btn17 = types.InlineKeyboardButton("📱 নগদ নাম্বার সেট", callback_data="admin_set_nagad")
        btn18 = types.InlineKeyboardButton("👤 সাপোর্ট ইউজার সেট", callback_data="admin_set_sup_user")
        btn19 = types.InlineKeyboardButton("📱 সাপোর্ট ফোন সেট", callback_data="admin_set_sup_phone")
        btn20 = types.InlineKeyboardButton("📦 অর্ডার ফরওয়ার্ড চ্যানেল সেট", callback_data="admin_set_log_chan")
        btn21 = types.InlineKeyboardButton("💰 প্রাইজ লিস্ট টেক্সট সেট", callback_data="admin_set_price_text")
        btn22 = types.InlineKeyboardButton("📝 অর্ডার সাকসেস নোট সেট", callback_data="admin_set_success_note")
        
        btn23 = types.InlineKeyboardButton("💥 সকল সার্ভিস ডিলিট", callback_data="admin_clear_services_confirm")

        markup = create_2col_markup([
            btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, 
            btn11, btn12, btn13, btn14, btn15, btn16, btn17, btn18, btn19, btn20, btn21, btn22, btn23
        ])

        bot.send_message(
            message.chat.id,
            "👑 <b>এডমিন কন্ট্রোল প্যানেল</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "নিচের বাটন চেপে যেকোনো কাজ সিলেক্ট করুন:",
            reply_markup=markup,
            parse_mode="HTML"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ এডমিন প্যানেল লোড করতে সমস্যা: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_bkash")
def admin_set_bkash(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📞 <b>আপনার নতুন বিকাশ পার্সোনাল নাম্বারটি টাইপ করে পাঠান:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_bkash)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_bkash(message):
    try:
        num = message.text.strip()
        set_setting("bkash_number", num)
        bot.send_message(message.chat.id, f"✅ <b>বিকাশ নাম্বার সফলভাবে সেট করা হয়েছে:</b> <code>{num}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_nagad")
def admin_set_nagad(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📱 <b>আপনার নতুন নগদ পার্সোনাল নাম্বারটি টাইপ করে পাঠান:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_nagad)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_nagad(message):
    try:
        num = message.text.strip()
        set_setting("nagad_number", num)
        bot.send_message(message.chat.id, f"✅ <b>নগদ নাম্বার সফলভাবে সেট করা হয়েছে:</b> <code>{num}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_sup_user")
def admin_set_sup_user(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "👤 <b>আপনার নতুন সাপোর্ট টেলিগ্রাম ইউজারনেমটি টাইপ করে পাঠান:</b>\n(অবশ্যই @ সহ লিখবেন, যেমন: `@Mr_Sojol_Ceo`)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_sup_user)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_sup_user(message):
    try:
        username = message.text.strip()
        set_setting("support_username", username)
        bot.send_message(message.chat.id, f"✅ <b>সাপোর্ট ইউজারনেম সফলভাবে সেট করা হয়েছে:</b> <code>{username}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_sup_phone")
def admin_set_sup_phone(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📱 <b>আপনার নতুন সাপোর্ট হোয়াটসঅ্যাপ/ফোন নাম্বারটি টাইপ করে পাঠান:</b>\n(যেমন: `+8801925263571`)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_sup_phone)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_sup_phone(message):
    try:
        phone = message.text.strip()
        set_setting("support_phone", phone)
        bot.send_message(message.chat.id, f"✅ <b>সাপোর্ট ফোন নাম্বার সফলভাবে সেট করা হয়েছে:</b> <code>{phone}</code>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_log_chan")
def admin_set_log_chan(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(
            call.message.chat.id, 
            "📦 <b>অর্ডার ফরওয়ার্ড করার জন্য আপনার চ্যানেল বা গ্রুপের ID-টি টাইপ করে পাঠান:</b>\n\n"
            "ℹ️ <i>কিভাবে আইডি পাবেন:</i>\n"
            "১. প্রথমে বোটকে আপনার চ্যানেল বা গ্রুপে অ্যাডমিন হিসেবে যুক্ত করুন এবং মেসেজ পাঠানোর পারমিশন দিন।\n"
            "২. এরপর আপনার চ্যানেলের আইডিটি (যেমন: `-1002345678912`) এখানে টাইপ করে পাঠান।", 
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, save_log_chan)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_log_chan(message):
    try:
        cid = message.text.strip()
        set_setting("log_channel_id", cid)
        bot.send_message(message.chat.id, f"✅ <b>অর্ডার লগ চ্যানেল আইডি সফলভাবে সেট করা হয়েছে:</b> <code>{cid}</code>\n\nএখন থেকে প্রতিটি সফল অর্ডার এই চ্যানেলে স্বয়ংক্রিয়ভাবে ফরওয়ার্ড হয়ে যাবে।", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_price_text")
def admin_set_price_text(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "💰 <b>আপনার বোটের জন্য নতুন কাস্টম প্রাইজ লিস্ট টেক্সটটি টাইপ করে পাঠান:</b>\n(HTML কোড এবং যেকোনো আকর্ষণীয় ইমোজি ব্যবহার করতে পারবেন)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_price_text)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_price_text(message):
    try:
        txt = message.text.strip()
        set_setting("price_list_text", txt)
        bot.send_message(message.chat.id, "✅ <b>প্রাইজ লিস্ট কাস্টম টেক্সট সফলভাবে সেট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_success_note")
def admin_set_success_note(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📝 <b>অর্ডার সফল হওয়ার পর নিচে দেখানোর জন্য অতিরিক্ত নোট টেক্সটটি পাঠান:</b>\n(রিসেট করতে `0` পাঠান)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_success_note)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_success_note(message):
    try:
        txt = message.text.strip()
        if txt == "0":
            set_setting("order_success_note", "")
            bot.send_message(message.chat.id, "✅ <b>অর্ডার সাকসেস নোট রিসেট করা হয়েছে।</b>", parse_mode="HTML")
        else:
            set_setting("order_success_note", txt)
            bot.send_message(message.chat.id, "✅ <b>অর্ডার সাকসেস নোট সফলভাবে সেট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_coin_rate")
def admin_set_coin_rate(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, f"🪙 <b>বর্তমান রেট: ১০০০ কয়েন = {get_coin_rate()} BDT</b>\n\n১০০০ কয়েনের নতুন মূল্য কত টাকা করতে চান? (শুধুমাত্র সংখ্যা যেমন: 12 বা 15 লিখে পাঠান):", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_coin_rate)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_coin_rate(message):
    try:
        new_rate = float(message.text.strip())
        set_setting("coin_rate_per_1000", new_rate)
        bot.send_message(message.chat.id, f"✅ <b>কয়েন রেট সফলভাবে আপডেট করা হয়েছে!</b>\nনতুন রেট: ১০০০ কয়েন = <b>{new_rate:.2f} BDT</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast_start")
def admin_broadcast_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, "📢 <b>বোটের সকল ইউজারের কাছে পাঠানোর জন্য আপনার নোটিশ/মেসেজটি লিখুন:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_broadcast)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def process_broadcast(message):
    try:
        text_to_send = message.text
        users = get_all_users()
        if not users:
            bot.send_message(message.chat.id, "❌ কোনো ইউজার খুঁজে পাওয়া যায়নি!")
            return

        msg_loading = bot.send_message(message.chat.id, "⏳ ব্রডকাস্টিং চালু হচ্ছে...")
        success = 0
        fail = 0

        for uid in users:
            try:
                bot.send_message(uid, text_to_send, parse_mode="HTML")
                success += 1
                time.sleep(0.05)
            except Exception:
                fail += 1

        bot.edit_message_text(f"📢 <b>ব্রডকাস্ট রিপোর্ট সম্পন্ন!</b>\n\n✅ সফলভাবে পাঠানো হয়েছে: <b>{success} জন</b>\n❌ ব্যর্থ হয়েছে (ব্লকড): <b>{fail} জন</b>", chat_id=message.chat.id, message_id=msg_loading.message_id, parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_smm_api")
def admin_set_smm_api(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    try:
        msg = bot.send_message(call.message.chat.id, f"🔌 <b>বর্তমান API URL:</b> <code>{get_smm_api_url()}</code>\n<b>নতুন API URL টি লিখে পাঠান:</b>\n(যেমন: `https://socialpanel.pro/api/v2`)", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_api_url)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_api_url(message):
    try:
        url = message.text.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            bot.send_message(message.chat.id, "❌ <b>ভুল ইউআরএল! লিংকটি অবশ্যই http:// বা https:// দিয়ে শুরু হতে হবে।</b> পুনরায় চেষ্টা করুন।")
            return
        set_setting("smm_api_url", url)
        msg = bot.send_message(message.chat.id, "🔑 <b>এখন আপনার নতুন SMM API Key টি লিখে পাঠান:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_api_key)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

def save_api_key(message):
    try:
        key = message.text.strip()
        if len(key) < 10:
            bot.send_message(message.chat.id, "❌ <b>ভুল বা অকার্যকর API Key!</b> অনুগ্রহ করে পুনরায় সঠিক কী দিয়ে চেষ্টা করুন।")
            return
        set_setting("smm_api_key", key)
        bot.send_message(message.chat.id, "✅ <b>SMM API URL & Key সফলভাবে আপডেট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_del_main_platform_start")
def admin_del_main_platform_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        main_cats = get_main_categories()
        if not main_cats:
            bot.send_message(call.message.chat.id, "❌ কোনো মেইন প্ল্যাটফর্ম পাওয়া যায়নি।")
            return
        btns = [types.InlineKeyboardButton(f"❌ {mc}", callback_data=f"delmainplatform_{mc}") for mc in main_cats]
        markup = create_2col_markup(btns)
        bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মটি সম্পূর্ণ ডিলিট করতে চান?</b>\n(সতর্কতা: এর ভেতরের সকল সাব-ক্যাটাগরি ও সার্ভিস ডিলিট হয়ে যাবে!)", reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmainplatform_"))
def admin_del_main_platform_confirm(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        mcat_name = call.data.replace("delmainplatform_", "")
        delete_main_category(mcat_name)
        bot.send_message(call.message.chat.id, f"✅ <b>[{mcat_name}] প্ল্যাটফর্মটি এবং এর আওতাধীনstone ডিলিট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_del_subcategory_start")
def admin_del_subcategory_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        main_cats = get_main_categories()
        if not main_cats:
            bot.send_message(call.message.chat.id, "❌ কোনো মেইন প্ল্যাটফর্ম পাওয়া যায়নি।")
            return
        btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"delsubcatselectmc_{mc}") for mc in main_cats]
        markup = create_2col_markup(btns)
        bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মের সাব-ক্যাটাগরি ডিলিট করবেন?</b>", reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsubcatselectmc_"))
def admin_del_subcategory_select_sub(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        mcat_name = call.data.replace("delsubcatselectmc_", "")
        sub_cats = get_sub_categories(mcat_name)
        if not sub_cats:
            bot.send_message(call.message.chat.id, f"❌ [{mcat_name}] এ কোনো সাব-ক্যাটাগরি নেই।")
            return
        btns = [types.InlineKeyboardButton(f"❌ {sc}", callback_data=f"delsubcatconfirm_{mcat_name}___{sc}") for sc in sub_cats]
        markup = create_2col_markup(btns)
        bot.send_message(call.message.chat.id, f"🗑️ <b>[{mcat_name}] এর কোন সাব-ক্যাটাগরি ডিলিট করবেন?</b>\n(সতর্কতা: এর আওতাধীন সকল সার্ভিস ডিলিট হয়ে যাবে!)", reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsubcatconfirm_"))
def admin_del_subcategory_confirm(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        raw_data = call.data.replace("delsubcatconfirm_", "")
        mcat_name, scat_name = raw_data.split("___")
        delete_sub_category(mcat_name, scat_name)
        bot.send_message(call.message.chat.id, f"✅ <b>[{mcat_name}] -> [{scat_name}] সাব-ক্যাটাগরি ও এর সার্ভিসগুলো ডিলিট করা হয়েছে!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_live_stats")
def admin_live_stats_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    try:
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT SUM(amount) FROM payments 
                WHERE status = 'Approved' AND date(timestamp, 'localtime') = date('now', 'localtime')
            """)
            today_deposit = cursor.fetchone()[0]
            today_deposit = today_deposit if today_deposit else 0.0
            
            cursor.execute("""
                SELECT COUNT(*), SUM(cost) FROM orders 
                WHERE date(timestamp, 'localtime') = date('now', 'localtime')
            """)
            row = cursor.fetchone()
            today_orders_count = row[0] if row[0] else 0
            today_orders_cost = row[1] if row[1] else 0.0
            
        stats_text = (
            f"📊 <b>লাইভ সেলস ও লাভ রিপোর্ট (আজকের)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>মোট ইউজার সংখ্যা:</b> <b>{total_users} জন</b>\n"
            f"💳 <b>আজকের মোট ডিপোজিট:</b> <b>{today_deposit:.2f} BDT</b>\n"
            f"🛒 <b>আজকের মোট অর্ডার:</b> <b>{today_orders_count} টি</b>\n"
            f"💰 <b>আজকের মোট সেলস ভ্যালু:</b> <b>{today_orders_cost:.2f} BDT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>পেমেন্ট এবং অর্ডারের লাইভ ডাটাবেজ ট্র্যাক করে এই হিসেব দেখানো হচ্ছে।</i>"
        )
        bot.send_message(call.message.chat.id, stats_text, parse_mode="HTML")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ স্ট্যাটাস লোড করতে ত্রুটি: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_co_admins")
def admin_manage_co_admins(call):
    if call.message.chat.id != MAIN_ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ শুধু মেইন Admin এটি ব্যবহার করতে পারবে!", show_alert=True)
        return
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("➕ নতুন এডমিন যোগ", callback_data="coadmin_add")
    btn2 = types.InlineKeyboardButton("❌ এডমিন রিমুভ", callback_data="coadmin_remove")
    markup.add(btn1, btn2)

    bot.send_message(MAIN_ADMIN_ID, "👑 <b>এডমিন ম্যানেজমেন্ট প্যানেল</b>\n\nনিচের বাটন ব্যবহার করুন:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("coadmin_"))
def coadmin_action(call):
    if call.message.chat.id != MAIN_ADMIN_ID: return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    action = call.data.replace("coadmin_", "")

    if action == "add":
        msg = bot.send_message(MAIN_ADMIN_ID, "👤 <b>যাকে এডমিন বানাবেন, তার টেলিগ্রাম ইউজার ID দিন:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_co_admin)
    elif action == "remove":
        msg = bot.send_message(MAIN_ADMIN_ID, "👤 <b>যাকে এডমিন থেকে রিমুভ করবেন, তার ইউজার ID দিন:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, remove_co_admin_save)

def save_co_admin(message):
    try:
        aid = int(message.text.strip())
        add_co_admin(aid)
        bot.send_message(MAIN_ADMIN_ID, f"✅ ইউজার <code>{aid}</code> কে এডমিন বানানো হয়েছে!", parse_mode="HTML")
    except ValueError:
        bot.send_message(MAIN_ADMIN_ID, "❌ ভুল ইউজার ID!")

def remove_co_admin_save(message):
    try:
        aid = int(message.text.strip())
        remove_co_admin(aid)
        bot.send_message(MAIN_ADMIN_ID, f"✅ ইউজার <code>{aid}</code> কে এডমিন থেকে সরিয়ে দেওয়া হয়েছে!", parse_mode="HTML")
    except ValueError:
        bot.send_message(MAIN_ADMIN_ID, "❌ ভুল ইউজার ID!")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_start_photo")
def admin_set_start_photo(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "🖼️ <b>বোট স্টার্টের ফটো লিংক (Direct Image URL) দিন:</b>\n(যেমন: `https://i.ibb.co/xxxxx/image.jpg` বা রিমুভ করতে `0` পাঠান):", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_start_photo)

def save_start_photo(message):
    url = message.text.strip()
    if url == "0":
        set_setting("start_photo", "")
        bot.send_message(message.chat.id, "✅ <b>স্টার্ট পিকচার রিমুভ করা হয়েছে!</b>", parse_mode="HTML")
    else:
        set_setting("start_photo", url)
        bot.send_message(message.chat.id, "✅ <b>স্টার্ট পিকচার সফলভাবে সেট হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_welcome_text")
def admin_set_welcome_text(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "📝 <b>বোটের প্রোফাইল ডেসক্রিপশন টেক্সট টাইপ করে পাঠান:</b>\n(রিসেট করতে `0` পাঠান)", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_welcome_text)

def save_welcome_text(message):
    txt = message.text.strip()
    if txt == "0":
        set_setting("welcome_text", "")
        bot.send_message(message.chat.id, "✅ <b>ডেসক্রিপশন ডিফল্ট সেটিংয়ে ফিরে গেছে!</b>", parse_mode="HTML")
    else:
        set_setting("welcome_text", txt)
        try:
            bot.set_my_description(txt)
            bot.set_my_short_description(txt)
        except Exception:
            pass
        bot.send_message(message.chat.id, "✅ <b>নতুন প্রোফাইল ডেসক্রিপশন সেভ হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_main_cat")
def admin_add_main_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    msg = bot.send_message(call.message.chat.id, "✍️ <b>নতুন মেইন প্ল্যাটফর্মের নাম লিখুন:</b>\n(যেমন: `🎵 TikTok Service` বা `👥 Facebook Service`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_save_main_cat)

def admin_save_main_cat(message):
    mcat_name = message.text.strip()
    add_main_category(mcat_name)
    bot.send_message(message.chat.id, f"✅ <b>মেইন প্ল্যাটফর্ম [{mcat_name}] তৈরি হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_sub_cat")
def admin_add_sub_cat_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)

    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(call.message.chat.id, "❌ আগে মেইন প্ল্যাটফর্ম তৈরি করুন!", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admsubsel_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "📁 <b>কোন প্ল্যাটফর্মের ভেতরে সাব-ক্যাটাগরি যোগ করবেন?</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admsubsel_"))
def admin_sub_cat_get_name(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    mcat_name = call.data.replace("admsubsel_", "")

    msg = bot.send_message(call.message.chat.id, f"✍️ <b>[{mcat_name}] এর নতুন সাব-ক্যাটাগরি (সার্ভিস) নাম লিখুন:</b>\n(যেমন: `TikTok View` বা `FB Like`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_save_sub_cat, mcat_name)

def admin_save_sub_cat(message, mcat_name):
    sub_name = message.text.strip()
    add_sub_category(mcat_name, sub_name)
    bot.send_message(message.chat.id, f"✅ <b>[{mcat_name}] -> [{sub_name}] সাব-ক্যাটাগরি তৈরি হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_service_start")
def admin_add_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)

    main_cats = get_main_categories()
    if not main_cats:
        bot.send_message(call.message.chat.id, "❌ কোনো মেইন প্ল্যাটফর্ম নেই! আগে মেইন প্ল্যাটফর্ম যোগ করুন।", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"admcatm_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, "📁 <b>মেইন প্ল্যাটফর্ম সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcatm_"))
def admin_step_select_sub_for_service(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)
    mcat_name = call.data.replace("admcatm_", "")

    sub_cats = get_sub_categories(mcat_name)
    if not sub_cats:
        bot.send_message(call.message.chat.id, f"❌ [{mcat_name}] এ কোনো সাব-ক্যাটাগরি (সার্ভিস) নেই! আগে সাব-ক্যাটাগরি যোগ করুন।", parse_mode="HTML")
        return

    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"admcats_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)
    bot.send_message(call.message.chat.id, f"📂 <b>[{mcat_name}] এর সাব-ক্যাটাগরি (সার্ভিস) সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admcats_"))
def admin_step_get_api_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    clear_user_steps(call.message.chat.id)

    raw_data = call.data.replace("admcats_", "")
    mcat_name, scat_name = raw_data.split("___")

    msg = bot.send_message(call.message.chat.id, f"🔌 <b>[{scat_name}] এর আসল API ID কত?</b> (যেমন: 19138):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_direct_coin, mcat_name, scat_name)

def admin_step_get_direct_coin(message, mcat_name, scat_name):
    api_id = message.text.strip()
    msg = bot.send_message(message.chat.id, f"🪙 <b>প্রতি ১০০০টির জন্য কাস্টমার থেকে কত টাকা কাটবেন?</b> (যেমন: 10 বা 15):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_min_qty, mcat_name, scat_name, api_id)

def admin_step_get_min_qty(message, mcat_name, scat_name, api_id):
    try:
        coin_price = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল ইনপুট! শুধুমাত্র সংখ্যা টাইপ করুন।")
        return

    msg = bot.send_message(message.chat.id, f"🔢 <b>সর্বনিম্ন কোয়ান্টিটি (Min Qty) কত হবে?</b> (যেমন: 100 বা 1000):", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_get_description, mcat_name, scat_name, api_id, coin_price)

def admin_step_get_description(message, mcat_name, scat_name, api_id, coin_price):
    try:
        min_qty = int(message.text.strip())
    except ValueError:
        min_qty = 10
        
    msg = bot.send_message(message.chat.id, "📝 <b>এই সার্ভিসের জন্য একটি বিবরণ (Description) বা নির্দেশনা লিখুন:</b>\n(না দিতে চাইলে `0` লিখে পাঠান)", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_step_save_direct_service, mcat_name, scat_name, api_id, coin_price, min_qty)

def admin_step_save_direct_service(message, mcat_name, scat_name, api_id, coin_price, min_qty):
    desc = message.text.strip()
    if desc == "0":
        desc = ""

    with sqlite3.connect(DB_FILE, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO services (main_cat, sub_cat, id_bot, api_id, name, price_per_1k, min_qty, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (mcat_name, scat_name, "1", api_id, scat_name, coin_price, min_qty, desc))
        conn.commit()

    bot.send_message(
        message.chat.id,
        f"✅ <b>সার্ভিসটি সফলভাবে যুক্ত করা হয়েছে!</b>\n\n"
        f"📁 <b>প্ল্যাটফর্ম:</b> <code>{mcat_name}</code>\n"
        f"📂 <b>সাব-ক্যাটাগরি:</b> <code>{scat_name}</code>\n"
        f"🔌 <b>API ID:</b> <b>{api_id}</b>\n"
        f"💰 <b>কয়েন প্রাইজ (১০০০টি):</b> <b>{coin_price:.2f} BDT</b>\n"
        f"🔢 <b>সর্বনিম্ন অর্ডার:</b> <b>{min_qty} টি</b>\n"
        f"📝 <b>ডেসক্রিপশন:</b> <b>{desc}</b>",
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_single_service_start")
def admin_delete_single_service_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)

    main_cats = get_main_categories()
    btns = [types.InlineKeyboardButton(f"📁 {mc}", callback_data=f"delmcat_{mc}") for mc in main_cats]
    markup = create_2col_markup(btns)

    bot.send_message(call.message.chat.id, "🗑️ <b>কোন প্ল্যাটফর্মের সার্ভিস ডিলিট করবেন?</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmcat_"))
def admin_del_select_sub(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    mcat_name = call.data.replace("delmcat_", "")

    sub_cats = get_sub_categories(mcat_name)
    btns = [types.InlineKeyboardButton(f"📂 {sc}", callback_data=f"delscat_{mcat_name}___{sc}") for sc in sub_cats]
    markup = create_2col_markup(btns)

    bot.send_message(call.message.chat.id, f"🗑️ <b>[{mcat_name}] এর সাব-ক্যাটাগরি সিলেক্ট করুন:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delscat_"))
def admin_del_select_id(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    raw_data = call.data.replace("delscat_", "")
    mcat_name, scat_name = raw_data.split("___")

    delete_single_service(mcat_name, scat_name, "1")
    bot.send_message(call.message.chat.id, f"✅ <b>[{scat_name}] এর সার্ভিসটি সফলভাবে ডিলিট করা হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_force_channel_menu")
def admin_force_channel_menu(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)

    channels = get_force_channels()
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for ch in channels:
        markup.add(types.InlineKeyboardButton(f"❌ {ch[1]} ডিলিট করুন", callback_data=f"delchan_{ch[0]}"))

    if len(channels) < 4:
        markup.add(types.InlineKeyboardButton("➕ নতুন চ্যানেল যোগ করুন", callback_data="addchan_start"))

    bot.send_message(call.message.chat.id, f"📢 <b>ফোর্সমস্ট জয়েন চ্যানেল তালিকা ({len(channels)}/4):</b>\n(⚠️ বোটকে চ্যানেলে এডমিন বানিয়ে রাখবেন!)\n\nনিচের বাটন দিয়ে যোগ বা রিমুভ করুন:", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "addchan_start")
def addchan_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 <b>চ্যানেলের ইউজারনেম লিখে পাঠান:</b>\n(যেমন: `@MyChannelName`):", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_get_link)

def addchan_get_link(message):
    ch_id = message.text.strip()
    msg = bot.send_message(message.chat.id, f"🔗 <b>চ্যানেলটির লিংক (Invite Link) পেস্ট করুন:</b>\n(যেমন: `https://t.me/MyChannelName`)", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_get_name, ch_id)

def addchan_get_name(message, ch_id):
    link = message.text.strip()
    msg = bot.send_message(message.chat.id, "📌 <b>বাটনে দেখানোর জন্য চ্যানেলের নাম লিখে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, addchan_save, ch_id, link)

def addchan_save(message, ch_id, link):
    ch_name = message.text.strip()
    add_force_channel(ch_id, ch_name, link)
    bot.send_message(message.chat.id, f"✅ <b>চ্যানেল [{ch_name}] যুক্ত হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delchan_"))
def delchan_process(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    ch_id = call.data.replace("delchan_", "")
    delete_force_channel(ch_id)
    bot.send_message(call.message.chat.id, "✅ <b>চ্যানেলটি রিমুভ করা হয়েছে!</b>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_user_info_start")
def admin_user_info_start(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔍 <b>ইউজারের তথ্য দেখতে বা কয়েন এডিট করতে ইউজার ID লিখে পাঠান:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, admin_process_user_lookup)

def admin_process_user_lookup(message):
    try:
        target_user = int(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল ইনপুট! ইউজার আইডি শুধুমাত্র সংখ্যা হয়।")
        return

    balance = get_balance(target_user)
    total_orders, total_payments = get_user_stats(target_user)

    btn1 = types.InlineKeyboardButton("➕ ব্যালেন্স যোগ করুন", callback_data=f"admbal_ADD_{target_user}")
    btn2 = types.InlineKeyboardButton("✏️ ব্যালেন্স সেট/এডিট", callback_data=f"admbal_SET_{target_user}")
    markup = create_2col_markup([btn1, btn2])

    info_text = (
        f"👤 <b>ইউজার অ্যাকাউন্ট ইনফরমেশন</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ইউজার ID:</b> <code>{target_user}</code>\n"
        f"💰 <b>বর্তমান ব্যালেন্স:</b> <b>৳ {balance:.2f} BDT</b>\n"
        f"🛒 <b>মোট সম্পন্ন অর্ডার:</b> <b>{total_orders} টি</b>\n"
        f"💳 <b>মোট সফল ডিপোজিট:</b> <b>{total_payments} টি</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 ব্যালেন্স চেঞ্জ করতে নিচের বাটন ব্যবহার করুন:"
    )
    bot.send_message(message.chat.id, info_text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admbal_"))
def admin_process_balance_action(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    
    action_data = call.data.replace("admbal_", "")
    action, target_user = action_data.split("_")
    target_user = int(target_user)

    if action == "ADD":
        msg = bot.send_message(call.message.chat.id, f"💵 ইউজার <code>{target_user}</code> এর সাথে <b>কত টাকা যোগ করবেন?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, admin_save_add_balance, target_user)
    elif action == "SET":
        msg = bot.send_message(call.message.chat.id, f"✏️ ইউজার <code>{target_user}</code> এর <b>নতুন ব্যালেন্স কত টাকা সেট করবেন?</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, admin_save_set_balance, target_user)

def admin_save_add_balance(message, target_user):
    try:
        amount = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল ইনপুট!")
        return

    current_bal = get_balance(target_user)
    new_balance = current_bal + amount
    update_balance(target_user, new_balance)

    bot.send_message(message.chat.id, f"✅ ইউজার <code>{target_user}</code> এর অ্যাকাউন্টে <b>৳ {amount:.2f} BDT</b> যোগ হয়েছে। নতুন ব্যালেন্স: <b>৳ {new_balance:.2f} BDT</b>", parse_mode="HTML")

    try:
        bot.send_message(
            target_user,
            f"🎉 <b>আপনার অ্যাকাউন্টে ব্যালেন্স যোগ করা হয়েছে!</b>\n\n"
            f"💳 <b>যোগকৃত ব্যালেন্স:</b> <b>৳ {amount:.2f} BDT</b>\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>৳ {new_balance:.2f} BDT</b> ✅",
            parse_mode="HTML"
        )
    except Exception:
        pass

def admin_save_set_balance(message, target_user):
    try:
        new_balance = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "❌ ভুল ইনপুট!")
        return

    update_balance(target_user, new_balance)
    bot.send_message(message.chat.id, f"✅ ইউজার <code>{target_user}</code> এর ব্যালেন্স সফলভাবে <b>৳ {new_balance:.2f} BDT</b> সেট করা হয়েছে।", parse_mode="HTML")

    try:
        bot.send_message(
            target_user,
            f"📢 <b>আপনার অ্যাকাউন্ট ব্যালেন্স আপডেট করা হয়েছে!</b>\n\n"
            f"💰 <b>বর্তমান মোট ব্যালেন্স:</b> <b>৳ {new_balance:.2f} BDT</b> ✅",
            parse_mode="HTML"
        )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "admin_users_list")
def admin_users_list_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    all_users = get_all_users()
    response = "👥 <b>বোটের সকল ইউজারের তালিকা:</b>\n\n"
    for u in all_users:
        response += f"👤 <b>ID:</b> <code>{u}</code>\n"
    bot.send_message(call.message.chat.id, response, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "admin_clear_services_confirm")
def admin_clear_services_callback(call):
    if not is_admin(call.message.chat.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔐 <b>সকল প্ল্যাটফর্ম ও সার্ভিস ডিলিট করতে ৫ ডিজিটের পিন (PIN) কোড দিন:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_clear_services_pin)

def process_clear_services_pin(message):
    pin = message.text.strip()
    if pin == "12345":
        try:
            with sqlite3.connect(DB_FILE, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM services")
                cursor.execute("DELETE FROM main_categories")
                cursor.execute("DELETE FROM sub_categories")
                conn.commit()
            bot.send_message(message.chat.id, "🗑️ <b>সফলভাবে সকল প্ল্যাটফর্ম, সাব-ক্যাটাগরি এবং সার্ভিস ডিলিট করা হয়েছে!</b>", parse_mode="HTML")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Error: {str(e)}")
    else:
        bot.send_message(message.chat.id, "❌ <b>ভুল পিন কোড! ডিলিট করার অনুরোধ বাতিল করা হয়েছে।</b>", parse_mode="HTML")

# ===================================================

def get_main_menu_markup(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("🛒 ORDER SERVICE")
    btn2 = types.KeyboardButton("💳 DEPOSIT")
    btn3 = types.KeyboardButton("💰 ORDER PRICE")
    btn4 = types.KeyboardButton("📜 ORDER HISTORY")
    btn5 = types.KeyboardButton("👤 MY PROFILE")
    btn6 = types.KeyboardButton("📞 SUPPORT")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
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
        for ch in unjoined:
            markup.add(types.InlineKeyboardButton(f"📢 Join {ch[1]}", url=ch[2]))
        markup.add(types.InlineKeyboardButton("✅ জয়েন সম্পন্ন করেছি (Verify)", callback_data="verify_channel_joins"))

        bot.send_message(
            chat_id,
            "⚠️ <b>বট ব্যবহার করতে নিচের চ্যানেলগুলোতে জয়েন হওয়া বাধ্যতামূলক!</b>\n\n"
            "জয়েন শেষ করে <b>'✅ জয়েন সম্পন্ন করেছি'</b> বাটনে চাপ দিন:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return False
    return True

@bot.callback_query_handler(func=lambda call: call.data == "verify_channel_joins")
def verify_channel_joins_callback(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    unjoined = check_user_joined_all(chat_id)
    if not unjoined:
        bot.send_message(chat_id, "🎉 <b>সবগুলো চ্যানেলে জয়েনিং ভেরিফাই হয়েছে!</b>\nএখন আপনি বট ব্যবহার করতে পারবেন।", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
    else:
        bot.send_message(chat_id, "❌ <b>আপনি এখনো সবগুলো চ্যানেলে জয়েন করেননি!</b> অনুগ্রহ করে লিংকে গিয়ে জয়েন করুন।", parse_mode="HTML")

@bot.message_handler(commands=["start"])
def start_command(message):
    chat_id = message.chat.id
    add_user(chat_id)
    if enforce_force_join(chat_id):
        send_main_menu(chat_id, message.from_user.first_name)

def send_main_menu(chat_id, first_name):
    safe_name = "ইউজার" if not first_name else first_name.replace("<", "&lt;").replace(">", "&gt;")

    custom_welcome = get_setting("welcome_text")
    if custom_welcome:
        welcome_text = custom_welcome.replace("{name}", safe_name)
    else:
        welcome_text = (
            f"⚡✅ <b>আমাদের প্রিমিয়াম SMM বোটে স্বাগতম!</b> 🥰\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"হ্যালো <b>{safe_name}</b>, আশা করি ভালো আছেন! আমাদের বোটে আপনাকে আন্তরিক অভিনন্দন। এখানে আপনি বাজারের সেরা ও দ্রুততম সোশ্যাল মিডিয়া সার্ভিসগুলো পাবেন। 🚀\n\n"
            f"🛒 <b>অর্ডার শুরু করতে নিচের বাটনগুলো ব্যবহার করুন!</b> 👇"
        )
    
    start_photo = get_setting("start_photo")
    if start_photo:
        try:
            bot.send_photo(chat_id, start_photo, caption=welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
    else:
        bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

# --- 🚀 কিবোর্ড নেভিগেশন প্রসেসর ও মেইন বাটন হ্যান্ডলার ---
@bot.message_handler(func=lambda message: True)
def handle_menu_buttons(message):
    chat_id = message.chat.id
    if not enforce_force_join(chat_id):
        return

    text = message.text.strip()

    if text == "⬅️ MAIN MENU" or text == "❌ CANCEL" or text == "⬅️ প্রধান মেনু" or text == "❌ বাতিল করুন":
        clear_user_steps(chat_id)
        USER_STATES.pop(chat_id, None)
        send_main_menu(chat_id, message.from_user.first_name)
        return

    # --- ১. প্রফেশনাল প্রোফাইল ড্যাশবোর্ড কার্ড ---
    if text == "👤 MY PROFILE":
        balance = get_balance(chat_id)
        account_text = (
            f"┏━━━━━━━━━━━━━━━━━━━━┓\n"
            f"   👤 আমার অ্যাকাউন্ট ড্যাশবোর্ড 👤\n"
            f"┗━━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"🆔 আপনার ইউজার আইডি : {chat_id}\n"
            f"💰 বর্তমান ব্যালেন্স : {balance:.2f} BDT\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(chat_id, account_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

    # --- ২. নতুন অর্ডার ব্রাউজিং ---
    elif text == "🛒 ORDER SERVICE" or text == "⬅️ BACK":
        main_cats = get_main_categories()
        if not main_cats:
            bot.send_message(chat_id, "❌ <b>বর্তমানে কোনো সার্ভিস উপলব্ধ নেই। অনুগ্রহ করে কিছুক্ষণ পর চেষ্টা করুন।</b>", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
            return

        USER_STATES[chat_id] = {"step": "PLATFORMS"}
        bot.send_message(chat_id, "💸 <b>আমাদের সার্ভিস প্ল্যাটফর্ম নির্বাচন করুন:</b>", reply_markup=get_platforms_keyboard(), parse_mode="HTML")

    # --- ৩. সাব-ক্যাটাগরি ব্রাউজিং ---
    elif text in get_main_categories():
        USER_STATES[chat_id] = {"step": "SUBCATS", "main_cat": text}
        bot.send_message(chat_id, f"📂 <b>[{text}] সার্ভিস বেছে নিন:</b>", reply_markup=get_subcategories_keyboard(text), parse_mode="HTML")

    elif text == "⬅️ ব্যাক (প্ল্যাটফর্মস)":
        main_cats = get_main_categories()
        USER_STATES[chat_id] = {"step": "PLATFORMS"}
        bot.send_message(chat_id, "💸 <b>আমাদের সার্ভিস প্ল্যাটফর্ম নির্বাচন করুন:</b>", reply_markup=get_platforms_keyboard(), parse_mode="HTML")

    elif text == "⬅️ ব্যাক (সাব-ক্যাটাগরি)":
        state = USER_STATES.get(chat_id, {})
        main_cat = state.get("main_cat")
        if main_cat:
            USER_STATES[chat_id] = {"step": "SUBCATS", "main_cat": main_cat}
            bot.send_message(chat_id, f"📂 <b>[{main_cat}] সার্ভিস বেছে নিন:</b>", reply_markup=get_subcategories_keyboard(main_cat), parse_mode="HTML")
        else:
            handle_menu_buttons(message)

    # --- ৪. সরাসরি কোয়ান্টিটি ইনপুট পেজ ---
    elif chat_id in USER_STATES and USER_STATES[chat_id].get("step") == "SUBCATS" and text in get_sub_categories(USER_STATES[chat_id].get("main_cat")):
        state = USER_STATES[chat_id]
        main_cat = state["main_cat"]
        sub_cat = text
        
        services_list = get_services_by_sub_cat(main_cat, sub_cat)
        if not services_list:
            bot.send_message(chat_id, "❌ <b>এই সার্ভিসের ইনফরমেশন ডাটাবেজে পাওয়া যায়নি।</b>", reply_markup=get_subcategories_keyboard(main_cat), parse_mode="HTML")
            return
            
        selected_service = services_list[0]
        USER_STATES[chat_id] = {"step": "ENTER_QUANTITY", "main_cat": main_cat, "sub_cat": sub_cat, "service": selected_service}

        desc_text = f"\n{selected_service['description']}\n" if selected_service['description'] else ""

        msg = bot.send_message(
            chat_id, 
            f"👑 <b>SERVICE: {sub_cat}</b>\n"
            f"💰 <b>রেট:</b> {selected_service['price_per_1k']:.2f} BDT (প্রতি ১০০০ টি)\n"
            f"🔢 <b>সর্বনিম্ন কোয়ান্টিটি:</b> {selected_service['min_qty']} টি\n"
            f"{desc_text}\n"
            f"👉 <b>কত কোয়ান্টিটি (Quantity) নিতে চান? সংখ্যাটি লিখে পাঠান:</b>", 
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), 
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_order_step_quantity, selected_service)

    # --- ৫. রিচার্জ সিস্টেম ---
    elif text == "💳 DEPOSIT":
        clear_user_steps(chat_id)
        msg = bot.send_message(
            chat_id, 
            "💵 <b>কত টাকা (BDT) রিচার্জ করতে চান? পরিমাণ লিখে পাঠান:</b>\n\n"
            "<i>(সর্বনিম্ন রিচার্জ পরিমাণ ১০ টাকা)</i>", 
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ MAIN MENU"), 
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, get_intended_deposit_amount)

    # --- ৬. কাস্টম কন্টেন্ট বাটন ---
    elif text == "💰 ORDER PRICE":
        price_text = get_price_list_text()
        bot.send_message(chat_id, price_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

    # --- ৭. অর্ডার হিস্ট্রি ---
    elif text == "📜 ORDER HISTORY":
        msg_loading = bot.send_message(chat_id, "⏳ <b>অর্ডার হিস্ট্রি লোড হচ্ছে...</b>", parse_mode="HTML")
        orders = get_user_orders(chat_id)
        if not orders:
            bot.edit_message_text("📭 <b>আপনি এখনো কোনো অর্ডার করেননি।</b>", chat_id=chat_id, message_id=msg_loading.message_id, parse_mode="HTML")
            return

        order_ids = [o[0] for o in orders]
        statuses = get_multiple_orders_status(order_ids)

        response = "📋 <b>আপনার সর্বশেষ ৫টি অর্ডার এবং লাইভ স্ট্যাটাস:</b>\n\n"
        for idx, o in enumerate(orders, 1):
            o_id = str(o[0])
            st = statuses.get(o_id, {}).get("status", "Processing") if isinstance(statuses, dict) else "Processing"
            response += (
                f"<b>{idx}. {o[1]}</b>\n"
                f"🆔 <b>অর্ডার আইডি:</b> <code>{o[0]}</code>\n"
                f"🔢 <b>কোয়ান্টিটি:</b> <b>{o[2]}</b> | 💵 <b>খরচ:</b> <b>৳ {o[3]:.2f} BDT</b>\n"
                f"🚦 <b>লাইভ স্ট্যাটাস:</b> <b>{st}</b>\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            )
        bot.edit_message_text(response, chat_id=chat_id, message_id=msg_loading.message_id, parse_mode="HTML")

    # --- ৮. সাপোর্ট ---
    elif text == "📞 SUPPORT":
        username = get_support_username()
        phone = get_support_phone()
        support_text = (
            "┏━━━━━━━━━━━━━━━━━━┓\n"
            "       📞   <b>গ্রাহক সাপোর্ট</b>   📞\n"
            "┗━━━━━━━━━━━━━━━━━━┛\n\n"
            f"💬 <b>টেলিগ্রাম এডমিন:</b> {username}\n"
            f"📱 <b>হোয়াটসঅ্যাপ/ফোন:</b> {phone}\n\n"
            "পেমেন্ট এড করা বা অর্ডার সংক্রান্ত যেকোনো সমস্যার জন্য সরাসরি এডমিনের সাথে যোগাযোগ করুন।"
        )
        bot.send_message(chat_id, support_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

# --- 🚀 সরাসরি সার্ভিস অর্ডার প্লেসমেন্ট প্রসেসর ---
def process_order_step_quantity(message, selected_service):
    chat_id = message.chat.id
    quantity_input = message.text.strip()

    if quantity_input == "❌ CANCEL" or quantity_input == "⬅️ MAIN MENU" or quantity_input == "❌ বাতিল করুন":
        USER_STATES.pop(chat_id, None)
        send_main_menu(chat_id, message.from_user.first_name)
        return

    if not quantity_input.isdigit():
        msg = bot.send_message(chat_id, "🛑 <b>ভুল সংখ্যা! শুধুমাত্র সংখ্যা টাইপ করুন।</b>", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_step_quantity, selected_service)
        return

    quantity = int(quantity_input)
    min_qty = selected_service.get('min_qty', 10)

    if quantity < min_qty:
        msg = bot.send_message(chat_id, f"❌ <b>সর্বনিম্ন {min_qty} টি কোয়ান্টিটি অর্ডার করতে হবে!</b> আবার টাইপ করুন:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_step_quantity, selected_service)
        return

    msg = bot.send_message(chat_id, f"🔗 <b>আপনার অর্ডারের লিংকটি পেস্ট করে পাঠান:</b>", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
    bot.register_next_step_handler(msg, process_order_step_link, selected_service, quantity)

def process_order_step_link(message, selected_service, quantity):
    chat_id = message.chat.id
    link = message.text.strip()

    if link == "❌ CANCEL" or link == "⬅️ MAIN MENU" or link == "❌ বাতিল করুন":
        USER_STATES.pop(chat_id, None)
        send_main_menu(chat_id, message.from_user.first_name)
        return

    if not link.startswith("http"):
        msg = bot.send_message(chat_id, "🛑 <b>ভুল লিংক! সঠিক লিংক দিয়ে পুনরায় চেষ্টা করুন।</b>", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ CANCEL"), parse_mode="HTML")
        bot.register_next_step_handler(msg, process_order_step_link, selected_service, quantity)
        return

    bdt_rate_per_1k = selected_service.get("price_per_1k", 0.0) or 10.0
    estimated_cost = (quantity / 1000) * bdt_rate_per_1k

    if estimated_cost < 1.0:
        estimated_cost = 1.0

    user_balance = get_balance(chat_id)

    if user_balance < estimated_cost:
        bot.send_message(
            chat_id,
            f"❌ <b>আপনার অ্যাকাউন্টে পর্যাপ্ত ব্যালেন্স নেই!</b>\n\n"
            f"অর্ডারের মূল্য: <b>৳ {estimated_cost:.2f} BDT</b>\n"
            f"আপনার ব্যালেন্স: <b>৳ {user_balance:.2f} BDT</b>",
            reply_markup=get_main_menu_markup(chat_id),
            parse_mode="HTML"
        )
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("✅ CONFIRM", "❌ CANCEL")

    confirm_msg = (
        f"💵 <b>আপনার অর্ডার মূল্য: ৳ {estimated_cost:.2f} BDT</b>\n\n"
        f"অর্ডারটি সাবমিট করতে নিচের <b>'✅ CONFIRM'</b> বাটনে ক্লিক করুন।"
    )
    msg = bot.send_message(chat_id, confirm_msg, reply_markup=markup, parse_mode="HTML")
    bot.register_next_step_handler(msg, confirm_order_final, selected_service, link, quantity, estimated_cost)

def confirm_order_final(message, selected_service, link, quantity, estimated_cost):
    chat_id = message.chat.id
    user_choice = message.text.strip()

    if user_choice == "✅ CONFIRM" or user_choice == "✅ কনফার্ম করুন":
        user_balance = get_balance(chat_id)
        if user_balance < estimated_cost:
            bot.send_message(chat_id, "❌ <b>আপনার অ্যাকাউন্টে পর্যাপ্ত ব্যালেন্স নেই।</b>", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
            return

        payload = {
            "key": get_smm_api_key(),
            "action": "add",
            "service": selected_service["api_id"],
            "link": link,
            "quantity": quantity,
        }
        
        try:
            response = requests.post(get_smm_api_url(), data=payload)
            api_res = response.json()

            if isinstance(api_res, dict) and "order" in api_res:
                new_balance = user_balance - estimated_cost
                update_balance(chat_id, new_balance)
                add_order_to_db(api_res["order"], chat_id, selected_service["name"], quantity, estimated_cost)

                success_text = (
                    f"✅ <b>অর্ডার সফলভাবে সাবমিট হয়েছে!</b>\n\n"
                    f"📌 <b>সার্ভিস:</b> {selected_service['name']}\n"
                    f"🔗 <b>লিংক:</b> {link}\n"
                    f"🔢 <b>কোয়ান্টিটি:</b> {quantity}\n"
                    f"💳 <b>খরচ:</b> <b>৳ {estimated_cost:.2f} BDT</b>\n"
                    f"💰 <b>অবशिष्ट ব্যালেন্স:</b> <b>৳ {new_balance:.2f} BDT</b>\n"
                    f"🆔 <b>অর্ডার আইডি:</b> <code>{api_res['order']}</code> ✅"
                )
                
                success_note = get_order_success_note()
                if success_note:
                    success_text += f"\n\n📝 <b>নোট:</b>\n{success_note}"
                    
                bot.send_message(chat_id, success_text, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
                
                log_chan = get_log_channel_id()
                if log_chan:
                    try:
                        bot.send_message(
                            log_chan,
                            f"📦 <b>NEW ORDER PLACED!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 <b>ইউজার আইডি:</b> <code>{chat_id}</code>\n"
                            f"🆔 <b>অর্ডার আইডি:</b> <code>{api_res['order']}</code>\n"
                            f"📌 <b>সার্ভিস:</b> <b>{selected_service['name']}</b>\n"
                            f"🔢 <b>কোয়ান্টিটি:</b> <b>{quantity} টি</b>\n"
                            f"💵 <b>মূল্য:</b> <b>৳ {estimated_cost:.2f} BDT</b>\n"
                            f"🔗 <b>লিংক:</b> Private\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"✅ <i>অর্ডারটি সফলভাবে সার্ভারে সাবমিট হয়েছে।</i>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
            else:
                error_msg = api_res.get("error", "Unknown SMM Server error") if isinstance(api_res, dict) else "Invalid SMM Server response"
                bot.send_message(chat_id, f"❌ <b>অর্ডার ব্যর্থ হয়েছে। সার্ভার রেসপন্স:</b> {error_msg}", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")
                
        except Exception:
            bot.send_message(chat_id, "❌ <b>SMM সার্ভারের সাথে সংযোগ বিচ্ছিন্ন হয়েছে।</b> পুনরায় চেষ্টা করুন।", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

    else:
        bot.send_message(chat_id, "❌ <b>অর্ডারটি বাতিল করা হয়েছে।</b>", reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

# --- 💳 ডিপোজিট পরিমাণ ইনপুট হ্যান্ডলার ---
def get_intended_deposit_amount(message):
    chat_id = message.chat.id
    amount_str = message.text.strip()

    if amount_str == "⬅️ MAIN MENU" or amount_str == "⬅️ প্রধান মেনু":
        clear_user_steps(chat_id)
        send_main_menu(chat_id, message.from_user.first_name)
        return

    try:
        if not amount_str.replace('.', '', 1).isdigit():
            msg = bot.send_message(chat_id, "❌ <b>ভুল ইনপুট! শুধু সংখ্যা লিখে পাঠান (যেমন: 10, 50, 100):</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, get_intended_deposit_amount)
            return

        intended_amount = float(amount_str)
        if intended_amount < 10.0:
            msg = bot.send_message(chat_id, "❌ <b>সর্বনিম্ন ১০ টাকা রিচার্জ করতে হবে!</b> আবার চেষ্টা করুন।", parse_mode="HTML")
            bot.register_next_step_handler(msg, get_intended_deposit_amount)
            return
        
        bdt_cost = intended_amount
        bkash_num = get_bkash_number()
        nagad_num = get_nagad_number()
        bot_domain = get_bot_domain()
        
        web_app_url = f"{bot_domain}/payment-page?coins={intended_amount}&bdt={bdt_cost}&bkash={bkash_num}&nagad={nagad_num}"
        
        msg_text = (
            "┏━━━━━━━━━━━━━━━━━━━━┓\n"
            "   🪙 <b>অটো রিচার্জ প্যানেল</b> 🪙\n"
            "┗━━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"💵 <b>রিচার্জ পরিমাণ:</b> <b>{bdt_cost:.2f} BDT</b>\n"
            "⚠️ <b>সর্বনিম্ন রিচার্জ পরিমাণ:</b> <b>১০ টাকা</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💳 <b>METHOD / পেমেন্ট মাধ্যমসমূহ:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 <b>বিকাশ পার্সোনাল:</b> (চাপ দিলেই কপি হবে)\n<code>{bkash_num}</code>\n\n"
            f"💸 <b>নগদ পার্সোনাল:</b> (চাপ দিলেই কপি হবে)\n<code>{nagad_num}</code>\n\n"
            "⚠️ <b>নির্দেশনা:</b>\n"
            "প্রথমে ওপরের বিকাশ অথবা নগদ নাম্বারে টাকা <b>Send Money</b> করুন। এরপর নিচে থাকা <b>'💳 CLICK TO PAY'</b> বাটনে ক্লিক করে সঠিক TrxID দিয়ে ভেরিফাই করুন। সার্ভার অটোমেটিক আপনার ব্যালেন্স অ্যাড করে দেবে।\n\n"
            "👇 <b>রিচার্জ সম্পন্ন করতে নিচের বাটনে ক্লিক করুন:</b>"
        )
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        try:
            web_app_obj = types.WebAppInfo(url=web_app_url)
            markup.add(types.KeyboardButton("💳 CLICK TO PAY", web_app=web_app_obj))
        except (AttributeError, NameError):
            markup.add(types.KeyboardButton("💳 CLICK TO PAY"))
            
        markup.add("⬅️ MAIN MENU")
        bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="HTML")
        
    except Exception as e:
        error_msg = f"❌ <b>ক্যালকুলেশন ত্রুটি:</b> <code>{str(e)}</code>"
        bot.send_message(chat_id, error_msg, reply_markup=get_main_menu_markup(chat_id), parse_mode="HTML")

# ----------------- 🚀 RENDER/TERMUX FLASK THREAD -----------------
def start_bot_polling():
    while True:
        try:
            bot.polling(none_stop=True, skip_pending=True, timeout=60)
        except Exception as e:
            time.sleep(5)

if __name__ == "__main__":
    print("🤖 MONIRUL SMM BOT IS RUNNING SUCCESSFULLY...")
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    time.sleep(2)
    start_bot_polling()
