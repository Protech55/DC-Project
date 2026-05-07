import asyncio
import json
import os
import requests
import time
import websockets
from threading import Thread
from flask import Flask, render_template_string
# Script was made by Protech55
# ================== SETTINGS ==================
# İstediğin kadar token ekleyebilirsin
TOKENS = [
    os.getenv("TOKEN1"),
    os.getenv("TOKEN2"),
    os.getenv("TOKEN3"),
    os.getenv("TOKEN4"),
]
# ==============================================

accounts = []
headers_list = []

for i, token in enumerate(TOKENS, 1):
    if not token:
        print(f"TOKEN{i} is empty, skipping...")
        continue
        
    headers = {"Authorization": token}
    r = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
    
    if r.status_code != 200:
        print(f"TOKEN{i} is invalid!")
        continue
        
    user = r.json()
    print(f"Logged in as {user['username']} ({user['id']})")
    
    accounts.append({
        "token": token,
        "user": user,
        "last_status": "online",
        "last_custom_status": "Running 24/7",
        "last_emoji": "⚡"
    })

if not accounts:
    print("No valid accounts found! Exiting...")
    exit()

# ================== FLASK (More Natural Look) ==================
app = Flask('')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Status Manager</title>
    <style>
        body { font-family: Arial, sans-serif; background: #0f0f0f; color: #00ff9d; text-align: center; padding: 40px; }
        h1 { color: #00ff9d; }
        .account { background: #1a1a1a; margin: 15px auto; padding: 15px; border-radius: 8px; max-width: 600px; }
    </style>
</head>
<body>
    <h1>Discord 24/7 Status Manager</h1>
    <p>Service is running smoothly.</p>
    {% for acc in accounts %}
    <div class="account">
        <strong>{{ acc.username }}</strong><br>
        Status: {{ acc.status }} | Custom: {{ acc.custom }} {{ acc.emoji }}
    </div>
    {% endfor %}
</body>
</html>
"""

@app.route('/')
def home():
    data = []
    for acc in accounts:
        data.append({
            "username": acc["user"]["username"],
            "status": acc["last_status"],
            "custom": acc["last_custom_status"],
            "emoji": acc["last_emoji"]
        })
    return render_template_string(HTML_TEMPLATE, accounts=data)

@app.route('/health')
def health():
    return {"status": "ok", "accounts": len(accounts)}, 200

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    server = Thread(target=run)
    server.start()
# ================================================

def build_activity(acc):
    if not acc["last_custom_status"] and not acc["last_emoji"]:
        return None
    activity = {
        "name": "Custom Status",
        "type": 4,
        "state": acc["last_custom_status"],
        "id": "custom"
    }
    if acc["last_emoji"]:
        activity["emoji"] = {"name": acc["last_emoji"]}
    return activity

async def run_account(acc):
    username = acc["user"]["username"]
    
    while True:
        try:
            async with websockets.connect(
                "wss://gateway.discord.gg/?v=10&encoding=json",
                max_size=None                    # Sınırsız mesaj boyutu
            ) as ws:
                
                hello = json.loads(await ws.recv())
                heartbeat_interval = hello["d"]["heartbeat_interval"]

                async def heartbeat():
                    while True:
                        await asyncio.sleep(heartbeat_interval / 1000)
                        await ws.send(json.dumps({"op": 1, "d": None}))

                asyncio.create_task(heartbeat())

                # İlk bağlantı
                identify = {
                    "op": 2,
                    "d": {
                        "token": acc["token"],
                        "properties": {"$os": "linux", "$browser": "chrome", "$device": "pc"},
                        "presence": {
                            "status": acc["last_status"],
                            "afk": False,
                            "activities": [build_activity(acc)] if build_activity(acc) else []
                        }
                    }
                }
                await ws.send(json.dumps(identify))
                print(f"✅ {username} | Connected | Status: {acc['last_status']}")

                # Her 12 saniyede bir ayarları kontrol et
                async def check_settings():
                    while True:
                        await asyncio.sleep(12)
                        try:
                            s = requests.get(
                                "https://discord.com/api/v10/users/@me/settings",
                                headers={"Authorization": acc["token"]}
                            )
                            if s.status_code == 200:
                                settings = s.json()
                                changed = False

                                new_status = settings.get("status", "online")
                                if new_status not in ["offline"]:
                                    if new_status != acc["last_status"]:
                                        acc["last_status"] = new_status
                                        changed = True
                                        print(f"🔄 {username} | Status changed → {new_status}")

                                custom = settings.get("custom_status", {})
                                if custom:
                                    new_text = custom.get("text", "")
                                    new_emoji = custom.get("emoji_name", "")
                                    if new_text != acc["last_custom_status"] or new_emoji != acc["last_emoji"]:
                                        acc["last_custom_status"] = new_text
                                        acc["last_emoji"] = new_emoji
                                        changed = True
                                        print(f"✏️ {username} | Custom changed → {new_text} {new_emoji}")

                                if changed:
                                    update = {
                                        "op": 3,
                                        "d": {
                                            "since": None,
                                            "activities": [build_activity(acc)] if build_activity(acc) else [],
                                            "status": acc["last_status"],
                                            "afk": False
                                        }
                                    }
                                    await ws.send(json.dumps(update))
                        except:
                            pass

                asyncio.create_task(check_settings())

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("op") == 11:
                        continue

        except Exception as e:
            print(f"❌ {username} | Connection lost: {e}")
            await asyncio.sleep(5)

keep_alive()

# Tüm hesapları paralel çalıştır
asyncio.run(asyncio.gather(*(run_account(acc) for acc in accounts)))
