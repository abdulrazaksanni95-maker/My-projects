"""
QRMENU.NG - QR Code Restaurant Menu & Ordering SaaS
Single-file Flask application (SQLite backend)
"""

import os
import sqlite3
import hashlib
import random
import string
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, session, redirect, url_for,
    render_template_string, g, flash, jsonify
)
from werkzeug.utils import secure_filename

# ============================================================
# CONFIG
# ============================================================
TEST_MODE = True

SUPERADMIN_EMAIL = "your_email@gmail.com"
SUPERADMIN_PASSWORD = "admin123"

BANK_NAME = "Opay"
BANK_ACCOUNT = "0123456789"
BANK_ACCOUNT_NAME = "Your Name"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "your_email@gmail.com"
SMTP_PASSWORD = "your_app_password"

PLANS = {
    "1_month": {"label": "1 Month", "price": 5000},
    "3_months": {"label": "3 Months", "price": 12000},
    "6_months": {"label": "6 Months", "price": 20000},
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "qrmenu.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-before-production"
)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB uploads


# ============================================================
# DATABASE
# ============================================================
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            slug TEXT UNIQUE NOT NULL,
            logo TEXT,
            status TEXT DEFAULT 'inactive',
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            image TEXT,
            available INTEGER DEFAULT 1
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            track_code TEXT UNIQUE NOT NULL,
            customer_name TEXT,
            customer_phone TEXT,
            items TEXT,
            total REAL,
            status TEXT DEFAULT 'new',
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            plan TEXT,
            amount REAL,
            screenshot TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


# ============================================================
# HELPERS
# ============================================================
def hash_password(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def slugify(name):
    base = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    while "--" in base:
        base = base.replace("--", "-")
    return base or "restaurant"


def unique_slug(name):
    db = get_db()
    base = slugify(name)
    slug = base
    i = 1
    while db.execute("SELECT id FROM restaurants WHERE slug=?", (slug,)).fetchone():
        i += 1
        slug = f"{base}-{i}"
    return slug


def gen_track_code():
    return "QR" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def save_upload(file_storage, prefix):
    if not file_storage or file_storage.filename == "":
        return None
    filename = secure_filename(file_storage.filename)
    unique_name = f"{prefix}_{int(datetime.now().timestamp())}_{filename}"
    path = os.path.join(UPLOAD_DIR, unique_name)
    file_storage.save(path)
    return unique_name


def send_email(to_email, subject, body):
    if TEST_MODE:
        print("\n" + "=" * 60)
        print(f"[EMAIL - TEST MODE] To: {to_email}")
        print(f"Subject: {subject}")
        print(body)
        print("=" * 60 + "\n")
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
    except Exception as e:
        print(f"Email send failed: {e}")


def current_restaurant():
    rid = session.get("restaurant_id")
    if not rid:
        return None
    return get_db().execute("SELECT * FROM restaurants WHERE id=?", (rid,)).fetchone()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("restaurant_id"):
            return redirect(url_for("admin_home"))
        return f(*args, **kwargs)
    return wrapper


def superadmin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("superadmin"):
            return redirect(url_for("superadmin"))
        return f(*args, **kwargs)
    return wrapper


# ============================================================
# SHARED STYLE (Tailwind CDN + custom polish)
# ============================================================
HEAD = """
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script>
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: { sans: ['Plus Jakarta Sans', 'sans-serif'] },
        colors: {
          brand: '#FF6B00',
          brandblue: '#2563EB',
          brandgreen: '#10B981',
          brandbg: '#F8FAFC'
        }
      }
    }
  }
</script>
<style>
  body { font-family: 'Plus Jakarta Sans', sans-serif; background:#F8FAFC; }
  .btn { border-radius: 0.75rem; font-weight: 700; box-shadow: 0 4px 14px rgba(0,0,0,0.08); transition: all .2s ease; }
  .btn:hover { transform: scale(1.05); }
  .card { background:white; border-radius:1rem; box-shadow: 0 10px 30px rgba(0,0,0,0.06); }
  .pill { border-radius: 9999px; transition: all .2s ease; }
  ::-webkit-scrollbar{width:8px;} ::-webkit-scrollbar-thumb{background:#FF6B00;border-radius:9999px;}
  @keyframes pulseborder { 0%,100%{border-color:#FF6B00;} 50%{border-color:#FFB380;} }
  .new-order { animation: pulseborder 1.2s infinite; }
  .fade-in { animation: fadein .35s ease; }
  @keyframes fadein { from{opacity:0; transform:translateY(8px);} to{opacity:1; transform:translateY(0);} }
</style>
"""

DING_SOUND = """
<audio id="dingSound" preload="auto">
  <source src="https://actions.google.com/sounds/v1/alarms/beep_short.ogg" type="audio/ogg">
</audio>
"""


def money(n):
    try:
        return f"₦{float(n):,.0f}"
    except Exception:
        return f"₦{n}"


app.jinja_env.filters["money"] = money


# ============================================================
# SCREEN 1: /admin  (Landing + Login + Signup)
# ============================================================
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <title>QRMENU.NG - QR Menu &amp; Ordering for Restaurants</title>
  """ + HEAD + """
</head>
<body class="min-h-screen bg-gradient-to-br from-orange-500 to-blue-600 flex items-center justify-center p-4">

<div class="w-full max-w-md">
  <div class="rounded-3xl shadow-2xl bg-white p-8 fade-in">

    <div class="flex flex-col items-center mb-6">
      <div class="w-16 h-16 rounded-full bg-brand flex items-center justify-center text-white text-2xl font-extrabold shadow-lg mb-3">Q</div>
      <h1 class="text-3xl font-extrabold text-brand tracking-tight">QRMENU.NG</h1>
      <p class="text-slate-500 text-sm mt-1 text-center">QR menus &amp; orders for your restaurant — no app needed.</p>
    </div>

    {% if signup_result %}
      <div class="rounded-2xl bg-emerald-50 border-2 border-brandgreen p-5 fade-in">
        <p class="font-bold text-brandgreen mb-2">🎉 Account created!</p>
        <p class="text-sm text-slate-700 mb-3">Your restaurant link:</p>
        <div class="bg-white rounded-xl border-2 border-dashed border-brandgreen p-3 text-center font-mono text-sm break-all mb-4">
          {{ request.host_url }}menu/{{ signup_result.slug }}
        </div>
        <a href="https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={{ request.host_url }}menu/{{ signup_result.slug }}"
           download="qrmenu-{{ signup_result.slug }}.png" target="_blank"
           class="btn bg-brandblue text-white w-full py-3 flex items-center justify-center mb-3">⬇️ Download QR Code</a>
        <a href="{{ url_for('admin_login_as', rid=signup_result.id) }}"
           class="btn bg-brand text-white w-full py-3 flex items-center justify-center">💳 Go To Dashboard &amp; Payment</a>
      </div>
    {% else %}

    <div class="flex pill bg-slate-100 p-1 mb-6">
      <button onclick="showTab('login')" id="tab-login-btn"
        class="flex-1 pill py-2.5 font-bold text-sm transition {{ 'bg-brand text-white shadow' if active_tab!='signup' else 'text-slate-500' }}">
        🔑 Login
      </button>
      <button onclick="showTab('signup')" id="tab-signup-btn"
        class="flex-1 pill py-2.5 font-bold text-sm transition {{ 'bg-brand text-white shadow' if active_tab=='signup' else 'text-slate-500' }}">
        ✨ Sign Up Free
      </button>
    </div>

    {% if error %}
      <div class="rounded-xl bg-red-50 border-2 border-red-300 text-red-600 text-sm font-semibold p-3 mb-4">{{ error }}</div>
    {% endif %}

    <div id="pane-login" class="{{ '' if active_tab!='signup' else 'hidden' }}">
      <form method="POST" action="{{ url_for('admin_login') }}" class="space-y-3">
        <input required name="email" type="email" placeholder="Email address"
          class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none transition">
        <input required name="password" type="password" placeholder="Password"
          class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none transition">
        <button type="submit" class="btn bg-brand text-white w-full py-3">Login to Dashboard</button>
      </form>
    </div>

    <div id="pane-signup" class="{{ 'hidden' if active_tab!='signup' else '' }}">
      <form method="POST" action="{{ url_for('admin_signup') }}" class="space-y-3">
        <input required name="name" type="text" placeholder="Restaurant Name"
          class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none transition">
        <input required name="email" type="email" placeholder="Email address"
          class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none transition">
        <input name="phone" type="text" placeholder="Phone number"
          class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none transition">
        <input required name="password" type="password" placeholder="Create Password"
          class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none transition">
        <button type="submit" class="btn bg-brand text-white w-full py-3">Create My Free Account</button>
      </form>
    </div>
    {% endif %}
  </div>
  <p class="text-center text-white/80 text-xs mt-4">© 2026 QRMENU.NG — Built for Nigerian restaurants 🇳🇬</p>
</div>

<script>
function showTab(name){
  document.getElementById('pane-login').classList.toggle('hidden', name!=='login');
  document.getElementById('pane-signup').classList.toggle('hidden', name!=='signup');
  document.getElementById('tab-login-btn').className = 'flex-1 pill py-2.5 font-bold text-sm transition ' + (name==='login' ? 'bg-brand text-white shadow' : 'text-slate-500');
  document.getElementById('tab-signup-btn').className = 'flex-1 pill py-2.5 font-bold text-sm transition ' + (name==='signup' ? 'bg-brand text-white shadow' : 'text-slate-500');
}
</script>
</body>
</html>
"""


@app.route("/admin", methods=["GET"])
def admin_home():
    if session.get("restaurant_id"):
        return redirect(url_for("admin_dashboard"))
    signup_result = session.pop("signup_result", None)
    active_tab = request.args.get("tab", "login")
    error = session.pop("admin_error", None)
    return render_template_string(ADMIN_TEMPLATE, signup_result=signup_result,
                                   active_tab=active_tab, error=error)


@app.route("/admin/signup", methods=["POST"])
def admin_signup():
    db = get_db()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")

    if not name or not email or not password:
        session["admin_error"] = "Please fill in all required fields."
        return redirect(url_for("admin_home", tab="signup"))

    existing = db.execute("SELECT id FROM restaurants WHERE email=?", (email,)).fetchone()
    if existing:
        session["admin_error"] = "An account with this email already exists."
        return redirect(url_for("admin_home", tab="signup"))

    slug = unique_slug(name)
    db.execute(
        "INSERT INTO restaurants (name,email,password,phone,slug,status,created_at) VALUES (?,?,?,?,?,?,?)",
        (name, email, hash_password(password), phone, slug, "inactive", datetime.now().isoformat())
    )
    db.commit()
    rid = db.execute("SELECT id FROM restaurants WHERE email=?", (email,)).fetchone()["id"]

    send_email(email, "Welcome to QRMENU.NG!",
               f"Hi {name},\n\nYour restaurant page is live at /menu/{slug}.\n"
               f"Activate it by making a payment in your dashboard.\n\nQRMENU.NG Team")

    session["signup_result"] = {"slug": slug, "id": rid}
    return redirect(url_for("admin_home"))


@app.route("/admin/login-as/<int:rid>")
def admin_login_as(rid):
    # convenience redirect right after signup, straight into dashboard
    session["restaurant_id"] = rid
    return redirect(url_for("admin_dashboard", tab="payment"))


@app.route("/admin/login", methods=["POST"])
def admin_login():
    db = get_db()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    row = db.execute("SELECT * FROM restaurants WHERE email=?", (email,)).fetchone()
    if row and row["password"] == hash_password(password):
        session["restaurant_id"] = row["id"]
        return redirect(url_for("admin_dashboard"))
    session["admin_error"] = "Invalid email or password."
    return redirect(url_for("admin_home"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("restaurant_id", None)
    return redirect(url_for("admin_home"))


# ============================================================
# SCREEN 2: /admin/dashboard
# ============================================================
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <title>Dashboard - QRMENU.NG</title>
  """ + HEAD + """
</head>
<body class="bg-brandbg min-h-screen pb-16">
""" + DING_SOUND + """

<div class="max-w-5xl mx-auto p-4">

  <!-- HEADER -->
  <div class="card p-5 mb-4 flex items-center justify-between flex-wrap gap-3">
    <div>
      <p class="text-slate-400 text-xs font-semibold">WELCOME BACK</p>
      <h1 class="text-xl font-extrabold text-slate-800">{{ r.name }}</h1>
    </div>
    <div class="flex items-center gap-3">
      {% if r.status == 'active' %}
        <span class="pill bg-emerald-100 text-brandgreen font-bold text-sm px-4 py-2">🟢 Active</span>
      {% else %}
        <span class="pill bg-red-100 text-red-500 font-bold text-sm px-4 py-2">🔴 Offline</span>
      {% endif %}
      <a href="{{ url_for('admin_logout') }}" class="btn bg-slate-800 text-white text-sm px-4 py-2">Logout</a>
    </div>
  </div>

  {% if r.status != 'active' %}
  <div class="rounded-2xl bg-gradient-to-r from-orange-500 to-orange-400 text-white p-5 mb-4 shadow-lg flex items-center justify-between flex-wrap gap-3 fade-in">
    <div>
      <p class="font-extrabold text-lg">⚠️ Your restaurant is OFFLINE</p>
      <p class="text-white/90 text-sm">Customers can't order until you activate your account.</p>
    </div>
    <button onclick="openTab('payment')" class="btn bg-white text-brand px-5 py-3">Pay Now to Activate</button>
  </div>
  {% endif %}

  <!-- PILL TABS -->
  <div class="flex gap-2 mb-4 overflow-x-auto pb-1">
    <button onclick="openTab('orders')" id="btn-orders" class="tabbtn pill px-5 py-3 font-bold text-sm whitespace-nowrap">📦 Orders</button>
    <button onclick="openTab('menu')" id="btn-menu" class="tabbtn pill px-5 py-3 font-bold text-sm whitespace-nowrap">🍔 Menu</button>
    <button onclick="openTab('payment')" id="btn-payment" class="tabbtn pill px-5 py-3 font-bold text-sm whitespace-nowrap">💳 Payment</button>
    <button onclick="openTab('settings')" id="btn-settings" class="tabbtn pill px-5 py-3 font-bold text-sm whitespace-nowrap">⚙️ Settings</button>
  </div>

  <!-- TAB: ORDERS -->
  <div id="pane-orders" class="tabpane space-y-3">
    <div class="card p-4 flex items-center justify-between">
      <p class="font-bold text-slate-700">Live Orders</p>
      <span class="pill bg-slate-100 text-slate-500 text-xs font-semibold px-3 py-1">{{ orders|length }} total</span>
    </div>
    {% if not orders %}
      <div class="card p-8 text-center text-slate-400">No orders yet. Share your QR to get your first order! 🎉</div>
    {% endif %}
    <div class="grid sm:grid-cols-2 gap-4">
      {% for o in orders %}
      <div class="card p-5 {{ 'new-order border-2' if o.status=='new' else '' }}">
        <div class="flex justify-between items-start mb-2">
          <div>
            <p class="font-extrabold text-slate-800">{{ o.customer_name or 'Guest' }}</p>
            <p class="text-xs text-slate-400">{{ o.customer_phone or '' }} · #{{ o.track_code }}</p>
          </div>
          <span class="pill text-xs font-bold px-3 py-1
            {% if o.status=='new' %}bg-orange-100 text-brand
            {% elif o.status=='preparing' %}bg-blue-100 text-brandblue
            {% elif o.status=='ready' %}bg-emerald-100 text-brandgreen
            {% else %}bg-slate-200 text-slate-500{% endif %}">
            {{ o.status|capitalize }}
          </span>
        </div>
        <ul class="text-sm text-slate-600 mb-3 list-disc list-inside">
          {% for item in o.items_list %}
            <li>{{ item.qty }}x {{ item.name }}</li>
          {% endfor %}
        </ul>
        <p class="font-bold text-slate-800 mb-3">Total: {{ o.total|money }}</p>
        <div class="flex gap-2 flex-wrap">
          <form method="POST" action="{{ url_for('order_status', oid=o.id) }}"><input type="hidden" name="status" value="preparing">
            <button class="btn bg-blue-100 text-brandblue px-3 py-2 text-xs">Preparing</button></form>
          <form method="POST" action="{{ url_for('order_status', oid=o.id) }}"><input type="hidden" name="status" value="ready">
            <button class="btn bg-emerald-100 text-brandgreen px-3 py-2 text-xs">Ready</button></form>
          <form method="POST" action="{{ url_for('order_status', oid=o.id) }}"><input type="hidden" name="status" value="delivered">
            <button class="btn bg-slate-200 text-slate-600 px-3 py-2 text-xs">Delivered</button></form>
        </div>
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- TAB: MENU -->
  <div id="pane-menu" class="tabpane space-y-4 hidden">
    <div class="card p-5">
      <p class="font-bold text-slate-700 mb-3">Add New Item</p>
      <form method="POST" action="{{ url_for('menu_add') }}" enctype="multipart/form-data" class="grid sm:grid-cols-2 gap-3">
        <input required name="name" placeholder="Item name" class="rounded-xl border-2 border-slate-200 p-3 focus:border-blue-500 outline-none">
        <input required name="price" type="number" step="0.01" placeholder="Price (₦)" class="rounded-xl border-2 border-slate-200 p-3 focus:border-blue-500 outline-none">
        <input name="image" type="file" accept="image/*" class="rounded-xl border-2 border-slate-200 p-2.5 sm:col-span-2">
        <button type="submit" class="btn bg-brandblue text-white py-3 sm:col-span-2">+ Add New Item</button>
      </form>
    </div>
    <div class="grid sm:grid-cols-3 gap-4">
      {% for m in menu %}
      <div class="card p-4">
        {% if m.image %}
          <img src="{{ url_for('static', filename='uploads/' + m.image) }}" class="rounded-2xl w-full h-32 object-cover mb-3">
        {% else %}
          <div class="rounded-2xl w-full h-32 bg-slate-100 flex items-center justify-center mb-3 text-3xl">🍽️</div>
        {% endif %}
        <p class="font-bold text-slate-800">{{ m.name }}</p>
        <p class="text-brand font-extrabold mb-3">{{ m.price|money }}</p>
        <form method="POST" action="{{ url_for('menu_toggle', mid=m.id) }}" class="flex items-center justify-between">
          <span class="text-xs text-slate-400">{{ 'Available' if m.available else 'Hidden' }}</span>
          <button type="submit" class="w-12 h-7 rounded-full transition {{ 'bg-brandgreen' if m.available else 'bg-slate-300' }} relative">
            <span class="absolute top-1 {{ 'right-1' if m.available else 'left-1' }} w-5 h-5 bg-white rounded-full transition"></span>
          </button>
        </form>
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- TAB: PAYMENT -->
  <div id="pane-payment" class="tabpane space-y-4 hidden">
    <div class="card p-6 text-center">
      <p class="text-slate-400 text-sm font-semibold mb-1">PAY TO ACTIVATE YOUR RESTAURANT</p>
      <p class="text-2xl font-extrabold text-slate-800">Pay to {{ bank_name }}</p>
      <p class="text-3xl font-extrabold text-brand tracking-widest my-2">{{ bank_account }}</p>
      <p class="text-slate-500">Account Name: <span class="font-bold">{{ bank_account_name }}</span></p>
    </div>

    {% if latest_payment and latest_payment.status == 'pending' %}
      <div class="card p-6 text-center">
        <span class="pill bg-orange-100 text-brand font-bold px-4 py-2">⏳ Waiting for Approval</span>
        <p class="text-slate-400 text-sm mt-2">We'll activate your account once your payment is verified.</p>
      </div>
    {% else %}
    <form method="POST" action="{{ url_for('payment_submit') }}" enctype="multipart/form-data" class="space-y-4">
      <div class="card p-6">
        <p class="font-bold text-slate-700 mb-3">Choose Plan</p>
        <div class="grid grid-cols-3 gap-3">
          {% for key,p in plans.items() %}
          <label class="cursor-pointer">
            <input type="radio" name="plan" value="{{ key }}" class="peer hidden" {{ 'checked' if loop.first }}>
            <div class="rounded-xl border-2 border-slate-200 peer-checked:border-brand peer-checked:bg-orange-50 p-4 text-center transition">
              <p class="font-bold text-slate-700">{{ p.label }}</p>
              <p class="text-brand font-extrabold text-sm">{{ p.price|money }}</p>
            </div>
          </label>
          {% endfor %}
        </div>
      </div>
      <div class="card p-6">
        <p class="font-bold text-slate-700 mb-3">Upload Proof of Payment</p>
        <label class="block rounded-2xl border-2 border-dashed border-brand bg-orange-50 p-8 text-center cursor-pointer hover:bg-orange-100 transition">
          <input required type="file" name="screenshot" accept="image/*" class="hidden" onchange="document.getElementById('fname').innerText=this.files[0].name">
          <p class="text-4xl mb-2">📤</p>
          <p class="font-semibold text-slate-600">Click to upload screenshot</p>
          <p id="fname" class="text-xs text-slate-400 mt-1"></p>
        </label>
      </div>
      <button type="submit" class="btn bg-brandgreen text-white w-full py-3">Submit Payment Proof</button>
    </form>
    {% endif %}
  </div>

  <!-- TAB: SETTINGS -->
  <div id="pane-settings" class="tabpane hidden">
    <div class="card p-6">
      <p class="font-bold text-slate-700 mb-4">Restaurant Settings</p>
      <form method="POST" action="{{ url_for('settings_update') }}" enctype="multipart/form-data" class="space-y-3">
        <label class="text-xs font-semibold text-slate-400">Restaurant Name</label>
        <input name="name" value="{{ r.name }}" class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none">
        <label class="text-xs font-semibold text-slate-400">Phone</label>
        <input name="phone" value="{{ r.phone or '' }}" class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none">
        <label class="text-xs font-semibold text-slate-400">Logo</label>
        <input type="file" name="logo" accept="image/*" class="w-full rounded-xl border-2 border-slate-200 p-2.5">
        <label class="text-xs font-semibold text-slate-400">Public Menu Link</label>
        <div class="rounded-xl bg-slate-50 border-2 border-slate-100 p-3 text-sm font-mono break-all">{{ request.host_url }}menu/{{ r.slug }}</div>
        <button type="submit" class="btn bg-brand text-white w-full py-3 mt-2">Save Changes</button>
      </form>
    </div>
  </div>

</div>

<script>
const tabs = ['orders','menu','payment','settings'];
function openTab(name){
  tabs.forEach(t=>{
    document.getElementById('pane-'+t).classList.toggle('hidden', t!==name);
    document.getElementById('btn-'+t).className = 'tabbtn pill px-5 py-3 font-bold text-sm whitespace-nowrap ' +
      (t===name ? 'bg-brand text-white shadow-md' : 'bg-white text-slate-500 shadow');
  });
  localStorage.setItem('qrmenu_tab', name);
  history.replaceState(null,'','?tab='+name);
}
const urlTab = new URLSearchParams(window.location.search).get('tab');
openTab(urlTab || localStorage.getItem('qrmenu_tab') || 'orders');

{% if has_new_order %}
document.getElementById('dingSound').play().catch(()=>{});
{% endif %}
</script>
</body>
</html>
"""


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    db = get_db()
    r = current_restaurant()
    orders_raw = db.execute(
        "SELECT * FROM orders WHERE restaurant_id=? ORDER BY created_at DESC", (r["id"],)
    ).fetchall()
    orders = []
    for o in orders_raw:
        d = dict(o)
        try:
            d["items_list"] = json.loads(o["items"])
        except Exception:
            d["items_list"] = []
        orders.append(d)

    menu = db.execute("SELECT * FROM menu WHERE restaurant_id=? ORDER BY id DESC", (r["id"],)).fetchall()
    latest_payment = db.execute(
        "SELECT * FROM payments WHERE restaurant_id=? ORDER BY created_at DESC LIMIT 1", (r["id"],)
    ).fetchone()

    has_new_order = any(o["status"] == "new" for o in orders)

    return render_template_string(
        DASHBOARD_TEMPLATE, r=r, orders=orders, menu=menu,
        latest_payment=latest_payment, plans=PLANS,
        bank_name=BANK_NAME, bank_account=BANK_ACCOUNT, bank_account_name=BANK_ACCOUNT_NAME,
        has_new_order=has_new_order
    )


@app.route("/admin/order/status/<int:oid>", methods=["POST"])
@login_required
def order_status(oid):
    db = get_db()
    r = current_restaurant()
    status = request.form.get("status")
    db.execute("UPDATE orders SET status=? WHERE id=? AND restaurant_id=?", (status, oid, r["id"]))
    db.commit()
    return redirect(url_for("admin_dashboard", tab="orders"))


@app.route("/admin/menu/add", methods=["POST"])
@login_required
def menu_add():
    db = get_db()
    r = current_restaurant()
    name = request.form.get("name", "").strip()
    price = request.form.get("price", "0")
    image = save_upload(request.files.get("image"), "menu")
    db.execute(
        "INSERT INTO menu (restaurant_id,name,price,image,available) VALUES (?,?,?,?,1)",
        (r["id"], name, price, image)
    )
    db.commit()
    return redirect(url_for("admin_dashboard", tab="menu"))


@app.route("/admin/menu/toggle/<int:mid>", methods=["POST"])
@login_required
def menu_toggle(mid):
    db = get_db()
    r = current_restaurant()
    item = db.execute("SELECT * FROM menu WHERE id=? AND restaurant_id=?", (mid, r["id"])).fetchone()
    if item:
        db.execute("UPDATE menu SET available=? WHERE id=?", (0 if item["available"] else 1, mid))
        db.commit()
    return redirect(url_for("admin_dashboard", tab="menu"))


@app.route("/admin/payment/submit", methods=["POST"])
@login_required
def payment_submit():
    db = get_db()
    r = current_restaurant()
    plan = request.form.get("plan")
    screenshot = save_upload(request.files.get("screenshot"), "payment")
    amount = PLANS.get(plan, {}).get("price", 0)
    db.execute(
        "INSERT INTO payments (restaurant_id,plan,amount,screenshot,status,created_at) VALUES (?,?,?,?,?,?)",
        (r["id"], plan, amount, screenshot, "pending", datetime.now().isoformat())
    )
    db.commit()
    return redirect(url_for("admin_dashboard", tab="payment"))


@app.route("/admin/settings/update", methods=["POST"])
@login_required
def settings_update():
    db = get_db()
    r = current_restaurant()
    name = request.form.get("name", r["name"])
    phone = request.form.get("phone", r["phone"])
    logo_file = request.files.get("logo")
    logo = save_upload(logo_file, "logo") if logo_file and logo_file.filename else r["logo"]
    db.execute("UPDATE restaurants SET name=?, phone=?, logo=? WHERE id=?", (name, phone, logo, r["id"]))
    db.commit()
    return redirect(url_for("admin_dashboard", tab="settings"))


# ============================================================
# SCREEN 3: /menu/<slug> - Customer Facing
# ============================================================
MENU_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <title>{{ r.name }} - Menu</title>
  """ + HEAD + """
</head>
<body class="bg-brandbg min-h-screen pb-24">

<div class="max-w-md mx-auto p-4">

  {% if r.status != 'active' %}
    <div class="card p-10 text-center mt-16 fade-in">
      <p class="text-5xl mb-4">🍽️</p>
      <h1 class="text-2xl font-extrabold text-slate-800 mb-2">{{ r.name }}</h1>
      <p class="text-brand font-bold text-lg">Coming Soon</p>
      <p class="text-slate-400 text-sm mt-2">This menu isn't live yet. Please check back shortly!</p>
    </div>
  {% else %}

  <div class="card p-5 flex items-center gap-4 mb-4">
    {% if r.logo %}
      <img src="{{ url_for('static', filename='uploads/' + r.logo) }}" class="w-16 h-16 rounded-full object-cover shadow-md">
    {% else %}
      <div class="w-16 h-16 rounded-full bg-brand text-white flex items-center justify-center text-2xl font-extrabold shadow-md">
        {{ r.name[0]|upper }}
      </div>
    {% endif %}
    <div>
      <h1 class="font-extrabold text-lg text-slate-800">{{ r.name }}</h1>
      <p class="text-brandgreen text-xs font-bold">🟢 Open for orders</p>
    </div>
  </div>

  <div class="space-y-3 mb-24">
    {% for m in menu %}
    <div class="card p-4 flex items-center gap-4">
      {% if m.image %}
        <img src="{{ url_for('static', filename='uploads/' + m.image) }}" class="w-20 h-20 rounded-2xl object-cover">
      {% else %}
        <div class="w-20 h-20 rounded-2xl bg-slate-100 flex items-center justify-center text-2xl">🍽️</div>
      {% endif %}
      <div class="flex-1">
        <p class="font-bold text-slate-800">{{ m.name }}</p>
        <p class="text-brand font-extrabold">{{ m.price|money }}</p>
      </div>
      <button onclick="addToCart({{ m.id }}, '{{ m.name|replace("'", "") }}', {{ m.price }})"
        class="btn bg-brand text-white px-4 py-2 text-sm">+ Add</button>
    </div>
    {% endfor %}
    {% if not menu %}
      <div class="card p-8 text-center text-slate-400">No menu items yet.</div>
    {% endif %}
  </div>

  <!-- FLOATING CART -->
  <button onclick="openCart()" id="cartBtn"
    class="fixed bottom-6 right-6 w-16 h-16 rounded-full bg-brand text-white shadow-2xl flex items-center justify-center text-2xl hover:scale-110 transition z-40">
    🛒
    <span id="cartCount" class="absolute -top-1 -right-1 bg-brandblue text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center hidden">0</span>
  </button>

  <!-- CART / CHECKOUT MODAL -->
  <div id="cartModal" class="fixed inset-0 bg-black/40 hidden items-end sm:items-center justify-center z-50">
    <div class="bg-white rounded-2xl w-full sm:max-w-md max-h-[85vh] overflow-y-auto p-6 fade-in">
      <div class="flex justify-between items-center mb-4">
        <h2 class="font-extrabold text-lg text-slate-800">Your Cart</h2>
        <button onclick="closeCart()" class="text-slate-400 text-2xl leading-none">&times;</button>
      </div>
      <div id="cartItems" class="space-y-3 mb-4"></div>
      <p class="font-extrabold text-slate-800 mb-4">Total: <span id="cartTotal">₦0</span></p>
      <form id="checkoutForm" onsubmit="return submitOrder(event)" class="space-y-3">
        <input required id="custName" placeholder="Your name" class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none">
        <input required id="custPhone" placeholder="Phone number" class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none">
        <button type="submit" class="btn bg-brandgreen text-white w-full py-3">Place Order</button>
      </form>
    </div>
  </div>

  {% endif %}
</div>

<script>
const SLUG = "{{ r.slug }}";
let cart = JSON.parse(localStorage.getItem('cart_'+SLUG) || '[]');

function saveCart(){ localStorage.setItem('cart_'+SLUG, JSON.stringify(cart)); renderCartBadge(); }
function renderCartBadge(){
  const count = cart.reduce((a,i)=>a+i.qty,0);
  const badge = document.getElementById('cartCount');
  if(count>0){ badge.classList.remove('hidden'); badge.innerText = count; } else { badge.classList.add('hidden'); }
}
function addToCart(id,name,price){
  const existing = cart.find(i=>i.id===id);
  if(existing) existing.qty++; else cart.push({id,name,price,qty:1});
  saveCart();
}
function openCart(){
  const box = document.getElementById('cartItems');
  box.innerHTML = '';
  let total = 0;
  cart.forEach(i=>{
    total += i.price*i.qty;
    box.innerHTML += `<div class="flex justify-between items-center">
      <span class="text-sm text-slate-700">${i.qty}x ${i.name}</span>
      <span class="text-sm font-bold text-slate-800">₦${(i.price*i.qty).toLocaleString()}</span>
    </div>`;
  });
  if(cart.length===0) box.innerHTML = '<p class="text-slate-400 text-sm text-center">Cart is empty</p>';
  document.getElementById('cartTotal').innerText = '₦'+total.toLocaleString();
  document.getElementById('cartModal').classList.remove('hidden');
  document.getElementById('cartModal').classList.add('flex');
}
function closeCart(){
  document.getElementById('cartModal').classList.add('hidden');
  document.getElementById('cartModal').classList.remove('flex');
}
function submitOrder(e){
  e.preventDefault();
  if(cart.length===0){ alert('Your cart is empty'); return false; }
  fetch(`/order/${SLUG}`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      customer_name: document.getElementById('custName').value,
      customer_phone: document.getElementById('custPhone').value,
      items: cart
    })
  }).then(r=>r.json()).then(data=>{
    if(data.track_code){
      cart = []; saveCart();
      window.location.href = `/track?code=${data.track_code}`;
    } else { alert('Something went wrong. Please try again.'); }
  });
  return false;
}
renderCartBadge();
</script>
</body>
</html>
"""


@app.route("/menu/<slug>")
def customer_menu(slug):
    db = get_db()
    r = db.execute("SELECT * FROM restaurants WHERE slug=?", (slug,)).fetchone()
    if not r:
        return "Restaurant not found", 404
    menu = db.execute(
        "SELECT * FROM menu WHERE restaurant_id=? AND available=1 ORDER BY id DESC", (r["id"],)
    ).fetchall()
    return render_template_string(MENU_TEMPLATE, r=r, menu=menu)


@app.route("/order/<slug>", methods=["POST"])
def place_order(slug):
    db = get_db()
    r = db.execute("SELECT * FROM restaurants WHERE slug=?", (slug,)).fetchone()
    if not r or r["status"] != "active":
        return jsonify({"error": "restaurant not available"}), 400

    data = request.get_json(force=True)
    items = data.get("items", [])
    total = sum(i["price"] * i["qty"] for i in items)
    track_code = gen_track_code()

    db.execute(
        "INSERT INTO orders (restaurant_id,track_code,customer_name,customer_phone,items,total,status,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (r["id"], track_code, data.get("customer_name"), data.get("customer_phone"),
         json.dumps(items), total, "new", datetime.now().isoformat())
    )
    db.commit()
    return jsonify({"track_code": track_code})


# ============================================================
# SCREEN 4: /track
# ============================================================
TRACK_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <title>Track Order - QRMENU.NG</title>
  """ + HEAD + """
</head>
<body class="bg-brandbg min-h-screen flex items-center justify-center p-4">

<div class="card p-8 max-w-md w-full fade-in">
  {% if not order %}
    <h1 class="text-xl font-extrabold text-slate-800 mb-4 text-center">Track Your Order</h1>
    <form method="GET" action="{{ url_for('track') }}" class="flex gap-2">
      <input name="code" placeholder="Enter your order code" class="flex-1 rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none">
      <button class="btn bg-brand text-white px-5">Track</button>
    </form>
    {% if not_found %}<p class="text-red-500 text-sm mt-3 text-center">Order not found.</p>{% endif %}
  {% else %}
    <p class="text-center text-slate-400 text-xs font-semibold mb-1">ORDER #{{ order.track_code }}</p>
    <h1 class="text-xl font-extrabold text-slate-800 mb-6 text-center">{{ order.restaurant_name }}</h1>

    {% set steps = ['new','preparing','ready','delivered'] %}
    {% set labels = {'new':'Order Placed','preparing':'Preparing','ready':'Ready','delivered':'Delivered'} %}
    {% set icons = {'new':'🧾','preparing':'👨‍🍳','ready':'✅','delivered':'🎉'} %}
    {% set current_index = steps.index(order.status) %}

    <div class="flex items-center justify-between mb-8">
      {% for s in steps %}
        <div class="flex flex-col items-center flex-1">
          <div class="w-10 h-10 rounded-full flex items-center justify-center text-lg
            {{ 'bg-brand text-white shadow-lg' if loop.index0 <= current_index else 'bg-slate-100 text-slate-300' }}">
            {{ icons[s] }}
          </div>
          <p class="text-[10px] font-semibold mt-2 text-center {{ 'text-brand' if loop.index0 <= current_index else 'text-slate-300' }}">{{ labels[s] }}</p>
        </div>
        {% if not loop.last %}
          <div class="h-1 flex-1 -mt-6 {{ 'bg-brand' if loop.index0 < current_index else 'bg-slate-100' }}"></div>
        {% endif %}
      {% endfor %}
    </div>

    <div class="rounded-2xl bg-slate-50 p-4">
      {% for item in order.items_list %}
        <p class="text-sm text-slate-600">{{ item.qty }}x {{ item.name }}</p>
      {% endfor %}
      <p class="font-extrabold text-slate-800 mt-2">Total: {{ order.total|money }}</p>
    </div>
  {% endif %}
</div>
</body>
</html>
"""


@app.route("/track")
def track():
    code = request.args.get("code", "").strip()
    if not code:
        return render_template_string(TRACK_TEMPLATE, order=None, not_found=False)
    db = get_db()
    row = db.execute(
        "SELECT o.*, r.name as restaurant_name FROM orders o "
        "JOIN restaurants r ON r.id=o.restaurant_id WHERE o.track_code=?", (code,)
    ).fetchone()
    if not row:
        return render_template_string(TRACK_TEMPLATE, order=None, not_found=True)
    order = dict(row)
    try:
        order["items_list"] = json.loads(row["items"])
    except Exception:
        order["items_list"] = []
    return render_template_string(TRACK_TEMPLATE, order=order, not_found=False)


# ============================================================
# SCREEN 5: /superadmin - CEO Dashboard
# ============================================================
SUPERADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <title>Superadmin - QRMENU.NG</title>
  """ + HEAD + """
</head>
<body class="bg-brandbg min-h-screen pb-16">

{% if not logged_in %}
<div class="min-h-screen flex items-center justify-center p-4">
  <div class="card p-8 max-w-sm w-full fade-in">
    <h1 class="text-xl font-extrabold text-slate-800 mb-1 text-center">Superadmin Access</h1>
    <p class="text-slate-400 text-sm mb-5 text-center">Authorized personnel only</p>
    {% if error %}<div class="rounded-xl bg-red-50 border-2 border-red-300 text-red-600 text-sm font-semibold p-3 mb-4">{{ error }}</div>{% endif %}
    <form method="POST" class="space-y-3">
      <input required name="email" type="email" placeholder="Email" class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none">
      <input required name="password" type="password" placeholder="Password" class="w-full rounded-xl border-2 border-slate-200 p-3 focus:border-orange-500 outline-none">
      <button class="btn bg-slate-900 text-white w-full py-3">Enter Dashboard</button>
    </form>
  </div>
</div>
{% else %}

<div class="bg-slate-900 text-white p-6 mb-6">
  <div class="max-w-6xl mx-auto flex items-center justify-between">
    <div>
      <p class="text-slate-400 text-xs font-semibold">QRMENU.NG</p>
      <h1 class="text-xl font-extrabold">Superadmin Command Center</h1>
    </div>
    <a href="{{ url_for('superadmin_logout') }}" class="btn bg-white text-slate-900 text-sm px-4 py-2">Logout</a>
  </div>
</div>

<div class="max-w-6xl mx-auto px-4">

  <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
    <div class="card p-5 text-center">
      <p class="text-3xl font-extrabold text-slate-800">{{ stats.total }}</p>
      <p class="text-xs text-slate-400 font-semibold mt-1">Restaurants</p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-3xl font-extrabold text-brandgreen">{{ stats.active }}</p>
      <p class="text-xs text-slate-400 font-semibold mt-1">Active</p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-3xl font-extrabold text-brand">{{ stats.pending }}</p>
      <p class="text-xs text-slate-400 font-semibold mt-1">Pending Payments</p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-3xl font-extrabold text-brandblue">{{ stats.orders }}</p>
      <p class="text-xs text-slate-400 font-semibold mt-1">Total Orders</p>
    </div>
  </div>

  {% if pending_payments %}
  <div class="rounded-2xl bg-red-500 text-white p-5 mb-6 flex items-center justify-between flex-wrap gap-3 shadow-lg">
    <p class="font-extrabold">🔔 {{ pending_payments|length }} Pending Payment(s) awaiting approval</p>
    <form method="POST" action="{{ url_for('superadmin_approve_all') }}">
      <button class="btn bg-white text-red-500 px-5 py-2">APPROVE ALL</button>
    </form>
  </div>
  {% endif %}

  <div class="card p-5 mb-6 overflow-x-auto">
    <p class="font-bold text-slate-700 mb-3">Pending Payments</p>
    <table class="w-full text-sm">
      <thead><tr class="text-left text-slate-400 text-xs">
        <th class="pb-2">Restaurant</th><th class="pb-2">Plan</th><th class="pb-2">Amount</th><th class="pb-2">Proof</th><th class="pb-2">Action</th>
      </tr></thead>
      <tbody>
        {% for p in pending_payments %}
        <tr class="hover:bg-orange-50 transition border-t border-slate-100">
          <td class="py-3 font-semibold">{{ p.restaurant_name }}</td>
          <td class="py-3">{{ p.plan }}</td>
          <td class="py-3">{{ p.amount|money }}</td>
          <td class="py-3">
            {% if p.screenshot %}<a href="{{ url_for('static', filename='uploads/'+p.screenshot) }}" target="_blank" class="text-brandblue underline">View</a>{% else %}—{% endif %}
          </td>
          <td class="py-3">
            <form method="POST" action="{{ url_for('superadmin_approve', pid=p.id) }}">
              <button class="btn bg-brandgreen text-white px-4 py-2 text-xs">APPROVE</button>
            </form>
          </td>
        </tr>
        {% endfor %}
        {% if not pending_payments %}
        <tr><td colspan="5" class="py-6 text-center text-slate-400">No pending payments 🎉</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

  <div class="card p-5 overflow-x-auto">
    <p class="font-bold text-slate-700 mb-3">All Restaurants</p>
    <table class="w-full text-sm">
      <thead><tr class="text-left text-slate-400 text-xs">
        <th class="pb-2">Name</th><th class="pb-2">Email</th><th class="pb-2">Slug</th><th class="pb-2">Status</th><th class="pb-2">Joined</th>
      </tr></thead>
      <tbody>
        {% for r in restaurants %}
        <tr class="hover:bg-orange-50 transition border-t border-slate-100">
          <td class="py-3 font-semibold">{{ r.name }}</td>
          <td class="py-3">{{ r.email }}</td>
          <td class="py-3 font-mono text-xs">{{ r.slug }}</td>
          <td class="py-3">
            {% if r.status=='active' %}<span class="pill bg-emerald-100 text-brandgreen text-xs font-bold px-3 py-1">Active</span>
            {% else %}<span class="pill bg-red-100 text-red-500 text-xs font-bold px-3 py-1">Inactive</span>{% endif %}
          </td>
          <td class="py-3 text-slate-400 text-xs">{{ r.created_at[:10] }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
</body>
</html>
"""


@app.route("/superadmin", methods=["GET", "POST"])
def superadmin():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if email == SUPERADMIN_EMAIL.lower() and password == SUPERADMIN_PASSWORD:
            session["superadmin"] = True
            return redirect(url_for("superadmin"))
        return render_template_string(SUPERADMIN_TEMPLATE, logged_in=False, error="Invalid credentials.")

    if not session.get("superadmin"):
        return render_template_string(SUPERADMIN_TEMPLATE, logged_in=False, error=None)

    db = get_db()
    restaurants = db.execute("SELECT * FROM restaurants ORDER BY created_at DESC").fetchall()
    total = len(restaurants)
    active = sum(1 for r in restaurants if r["status"] == "active")
    orders_count = db.execute("SELECT COUNT(*) as c FROM orders").fetchone()["c"]

    pending_raw = db.execute(
        "SELECT p.*, r.name as restaurant_name FROM payments p "
        "JOIN restaurants r ON r.id=p.restaurant_id WHERE p.status='pending' ORDER BY p.created_at DESC"
    ).fetchall()
    pending_payments = [dict(p) for p in pending_raw]

    stats = {"total": total, "active": active, "pending": len(pending_payments), "orders": orders_count}

    return render_template_string(
        SUPERADMIN_TEMPLATE, logged_in=True, restaurants=restaurants,
        pending_payments=pending_payments, stats=stats
    )


@app.route("/superadmin/logout")
def superadmin_logout():
    session.pop("superadmin", None)
    return redirect(url_for("superadmin"))


@app.route("/superadmin/approve/<int:pid>", methods=["POST"])
@superadmin_required
def superadmin_approve(pid):
    db = get_db()
    payment = db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if payment:
        db.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        db.execute("UPDATE restaurants SET status='active' WHERE id=?", (payment["restaurant_id"],))
        db.commit()
    return redirect(url_for("superadmin"))


@app.route("/superadmin/approve-all", methods=["POST"])
@superadmin_required
def superadmin_approve_all():
    db = get_db()
    pending = db.execute("SELECT * FROM payments WHERE status='pending'").fetchall()
    for p in pending:
        db.execute("UPDATE payments SET status='approved' WHERE id=?", (p["id"],))
        db.execute("UPDATE restaurants SET status='active' WHERE id=?", (p["restaurant_id"],))
    db.commit()
    return redirect(url_for("superadmin"))


# ============================================================
# ROOT REDIRECT (only 2 real entry points exist)
# ============================================================
@app.route("/")
def root():
    return redirect(url_for("admin_home"))


# ============================================================
# INITIALIZE DATABASE
# ============================================================
with app.app_context():
    init_db()

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("QRMENU.NG running!")
    print(f"  Admin:      http://127.0.0.1:5000/admin")
    print(f"  Superadmin: http://127.0.0.1:5000/superadmin")
    print(f"  Superadmin login: {SUPERADMIN_EMAIL} / {SUPERADMIN_PASSWORD}")
    print(f"  TEST_MODE: {TEST_MODE}")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=False)