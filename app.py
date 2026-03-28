import os, json, time, base64, secrets, string, hashlib, math, threading
import requests
from flask import Flask, request, jsonify, render_template
from crypto import *

app = Flask(__name__)

# ==============================
# CONFIG
# ==============================

# Groq ключ — вставь сюда или задай переменную окружения GROQ_API_KEY на Railway
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "сюда_вставь_ключ")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

BOT_ID = "Crypto_Assistor"
BOT_KEY_FILE = "key_bot.json"

SYSTEM_PROMPT = (
    "Ты Crypto Assistant — помощник по криптографии и кибербезопасности. "
    "Отвечай кратко и по делу. Используй HTML теги: "
    "<b>жирный</b>, <code>код</code>, <br> для переноса строки. "
    "Не используй markdown (**, ##, ``` и т.д.) — только HTML."
)

# ==============================
# ХРАНИЛИЩЕ (в памяти)
# ==============================

users    = {}    # { user_id: public_key_b64 }
messages = {}    # { user_id: [messages] }
profiles = {}    # { user_id: {display_name, avatar, status, theme} }

# ==============================
# БОТ — КЛЮЧИ
# ==============================

if os.path.exists(BOT_KEY_FILE):
    with open(BOT_KEY_FILE, 'r') as f:
        d = json.load(f)
        bot_priv = b64_decode_private_key(d['priv'])
        bot_pub  = b64_decode_public_key(d['pub'])
else:
    bot_priv, bot_pub = generate_identity_keypair()
    with open(BOT_KEY_FILE, 'w') as f:
        json.dump({"priv": b64_encode_key(bot_priv), "pub": b64_encode_key(bot_pub)}, f)

# Регистрируем бота
users[BOT_ID] = b64_encode_key(bot_pub)
messages[BOT_ID] = []
profiles[BOT_ID] = {"display_name": "Crypto Assistant", "avatar": "🤖", "status": "E2EE · всегда онлайн", "theme": "dark"}

# ==============================
# FLASK ROUTES — СЕРВЕР
# ==============================

@app.route('/')
def index():
    return render_template('chat.html')

@app.post('/register')
def register():
    data = request.json
    uid  = data['user_id']
    users[uid] = data['identity_key']
    if uid not in messages:
        messages[uid] = []
    if uid not in profiles:
        profiles[uid] = {"display_name": uid, "avatar": "🙂", "status": "", "theme": "dark"}
    return jsonify({"status": "ok"})

@app.get('/users')
def list_users():
    return jsonify(list(users.keys()))

@app.get('/public_key/<user_id>')
def get_key(user_id):
    return jsonify({"public_key": users.get(user_id)})

@app.post('/send')
def send():
    data = request.json
    to   = data['to']
    if to not in messages:
        messages[to] = []
    messages[to].append({
        "from": data['from'],
        "ciphertext": data['ciphertext'],
        "timestamp": time.time()
    })
    return jsonify({"status": "sent"})

@app.get('/messages/<user_id>')
def get_msgs(user_id):
    msgs = messages.get(user_id, []).copy()
    messages[user_id] = []
    return jsonify(msgs)

@app.get('/profile/<user_id>')
def get_profile(user_id):
    p = profiles.get(user_id)
    if not p:
        return jsonify({"error": "not found"}), 404
    return jsonify(p)

@app.post('/profile/<user_id>')
def set_profile(user_id):
    if user_id not in profiles:
        return jsonify({"error": "not registered"}), 404
    data = request.json
    for key in ["display_name", "avatar", "status", "theme"]:
        if key in data:
            profiles[user_id][key] = data[key]
    return jsonify({"status": "ok", "profile": profiles[user_id]})

@app.get('/profiles')
def get_all_profiles():
    return jsonify({
        uid: {"display_name": p["display_name"], "avatar": p["avatar"], "status": p["status"]}
        for uid, p in profiles.items()
    })

# ==============================
# БОТ — GROQ AI
# ==============================

def groq_request(history):
    resp = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": GROQ_MODEL, "messages": history, "max_tokens": 1024},
        timeout=20
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

chat_history = {}

def menu():
    return (
        "<b>🤖 Crypto Assistant v4.6</b><br><br>"
        "<div class='bot-menu'>"
        "<button class='menu-btn' onclick='fillCmd(\"hash \")'>#️⃣ Hash</button>"
        "<button class='menu-btn' onclick='sendCmd(\"pass\")'>🔐 Pass</button>"
        "<button class='menu-btn' onclick='fillCmd(\"stego hide \")'>📦 Hide</button>"
        "<button class='menu-btn' onclick='fillCmd(\"stego reveal \")'>🔓 Reveal</button>"
        "<button class='menu-btn' onclick='fillCmd(\"encrypt \")'>📥 Enc</button>"
        "<button class='menu-btn' onclick='fillCmd(\"decrypt \")'>📤 Dec</button>"
        "<button class='menu-btn' onclick='fillCmd(\"entropy \")'>📊 Entropy</button>"
        "<button class='menu-btn' onclick='fillCmd(\"caesar enc 3 \")'>🔤 Caesar</button>"
        "<button class='menu-btn' onclick='sendCmd(\"keygen\")'>🗝️ Keygen</button>"
        "<button class='menu-btn full' onclick='sendCmd(\"info\")'>ℹ️ Info</button>"
        "</div>"
    )

def try_builtin(raw):
    t  = raw.strip()
    tl = t.lower()

    if tl in ["/help", "help", "❓", "меню", "/start"]:
        return menu()
    if tl == "info":
        return ("🛡️ <b>Архитектура:</b><br>• E2EE<br>• Curve25519<br>"
                "• XSalsa20-Poly1305<br>• Стеганография Unicode<br>• AI: Llama 3.3 70B (Groq)")
    if tl.startswith("hash "):
        val = t[5:].strip()
        return f"#️⃣ <b>SHA256:</b><br><code>{hashlib.sha256(val.encode()).hexdigest()}</code>"
    if tl.startswith("encrypt "):
        return f"📥 <b>Base64:</b><br><code>{base64.b64encode(t[8:].encode()).decode()}</code>"
    if tl.startswith("decrypt "):
        try:
            return f"📤 <b>Decoded:</b><br>{base64.b64decode(t[8:].encode()).decode()}"
        except:
            return "❌ Ошибка декодирования"
    if tl.startswith("entropy "):
        data  = t[8:]
        chars = len(set(data))
        ent   = len(data) * math.log2(chars) if chars > 1 else len(data)
        return f"📊 <b>Энтропия:</b> {ent:.2f} бит"
    if tl.startswith("stego hide "):
        secret = t[11:]
        binary = ''.join(format(ord(c), '08b') for c in secret)
        inv    = ''.join('\u200b' if b == '0' else '\u200c' for b in binary)
        return f"<b>Скрытое:</b><div class='stego-copy-box'>SAFE{inv}</div>"
    if tl.startswith("stego reveal "):
        bits = "".join('0' if c == '\u200b' else '1' for c in t if c in ['\u200b', '\u200c'])
        try:
            res = ''.join(chr(int(bits[i:i+8], 2)) for i in range(0, len(bits), 8))
            return f"<b>Раскрыто:</b> <code>{res}</code>"
        except:
            return "Скрытых данных не найдено"
    if tl.startswith("caesar enc "):
        try:
            parts = t.split(" ", 3)
            shift = int(parts[2])
            res   = "".join(
                chr((ord(c)-65+shift)%26+65) if c.isupper()
                else chr((ord(c)-97+shift)%26+97) if c.islower()
                else c for c in parts[3]
            )
            return f"🔤 <b>Шифр Цезаря:</b><br><code>{res}</code>"
        except:
            return "Использование: caesar enc 3 hello"
    if tl == "pass":
        p = ''.join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(16))
        return f"🔐 <b>Пароль:</b><br><code>{p}</code>"
    if tl == "keygen":
        _, pb = generate_identity_keypair()
        return f"🗝️ <b>Публичный ключ:</b><br><code>{b64_encode_key(pb)}</code>"
    return None

def ask_ai(sender, message):
    if sender not in chat_history:
        chat_history[sender] = [{"role": "system", "content": SYSTEM_PROMPT}]
    chat_history[sender].append({"role": "user", "content": message})

    for attempt in range(3):
        try:
            reply = groq_request(chat_history[sender])
            chat_history[sender].append({"role": "assistant", "content": reply})
            if len(chat_history[sender]) > 21:
                chat_history[sender] = [chat_history[sender][0]] + chat_history[sender][-20:]
            return reply
        except Exception as e:
            print(f"AI попытка {attempt+1}: {e}")
            if "429" in str(e):
                time.sleep(5)
            else:
                break

    chat_history[sender].pop()
    return "⚠️ AI перегружен, попробуй через 10 сек"

# ==============================
# БОТ — ФОНОВЫЙ ПОТОК
# ==============================

def bot_loop():
    print("🤖 Бот запущен")
    while True:
        try:
            for m in messages.get(BOT_ID, []).copy():
                messages[BOT_ID] = []
                sender = m['from']
                if sender not in users:
                    continue
                sender_pub = b64_decode_public_key(users[sender])
                income = decrypt_message(bot_priv, sender_pub, m['ciphertext'])
                reply  = try_builtin(income) or ask_ai(sender, income)
                ciphertext = encrypt_message(bot_priv, sender_pub, reply)
                if sender not in messages:
                    messages[sender] = []
                messages[sender].append({
                    "from": BOT_ID,
                    "ciphertext": ciphertext,
                    "timestamp": time.time()
                })
        except Exception as e:
            print("Bot error:", e)
        time.sleep(1)

# Запускаем бота в фоне
threading.Thread(target=bot_loop, daemon=True).start()

# ==============================
# ЗАПУСК
# ==============================

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
