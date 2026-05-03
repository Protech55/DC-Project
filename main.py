import asyncio
import json
import os
import requests
import websockets
from threading import Thread
from flask import Flask

# ================== SETTINGS ==================
TOKEN = os.getenv("TOKEN")
# ============================================

headers = {"Authorization": TOKEN}

# Starter value
last_status = "online"
last_custom_status = ""
last_emoji = ""

r = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
if r.status_code != 200:
    print("Invalid token")
    exit()

user = r.json()
print(f"✅ Logged in as {user['username']} ({user['id']})")

# ================== KEEP ALIVE ==================
app = Flask('')

@app.route('/')
def home():
    return f"{user['username']} | Status: {last_status} | Custom: {last_custom_status}"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server = Thread(target=run)
    server.start()
# ===============================================

def build_activity():
    """Mevcut custom status ve emoji ile activity objesi oluştur"""
    activity = {
        "name": "Custom Status",
        "type": 4,
        "state": last_custom_status,
        "id": "custom"
    }
    if last_emoji:
        activity["emoji"] = {"name": last_emoji, "id": None, "animated": False}
    return activity

async def discord_gateway():
    global last_status, last_custom_status, last_emoji
    uri = "wss://gateway.discord.gg/?v=10&encoding=json"

    async with websockets.connect(uri) as ws:
        hello = json.loads(await ws.recv())
        heartbeat_interval = hello["d"]["heartbeat_interval"]

        # Heartbeat
        async def heartbeat():
            while True:
                await asyncio.sleep(heartbeat_interval / 1000)
                await ws.send(json.dumps({"op": 1, "d": None}))

        asyncio.create_task(heartbeat())

        # Connect last identification
        identify = {
            "op": 2,
            "d": {
                "token": TOKEN,
                "properties": {
                    "$os": "linux",
                    "$browser": "chrome",
                    "$device": "pc"
                },
                "presence": {
                    "status": last_status,
                    "afk": False,
                    "activities": [build_activity()]
                }
            }
        }
        await ws.send(json.dumps(identify))
        print(f"Connected! | Status: {last_status} | Custom: {last_custom_status}")

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            # Status Change
            if data.get("t") == "PRESENCE_UPDATE":
                presence = data.get("d", {})
                
                if presence.get("user", {}).get("id") == user["id"]:
                    
                    # Online/Idle/DND changes
                    new_status = presence.get("status")
                    if new_status and new_status != "invisible":
                        if new_status != last_status:
                            last_status = new_status
                            print(f"🔄 Status değişti: {last_status}")

                    # Custom status
                    activities = presence.get("activities", [])
                    for act in activities:
                        if act.get("type") == 4:
                            
                            # Writing
                            new_custom = act.get("state", "")
                            if new_custom != last_custom_status:
                                last_custom_status = new_custom
                                print(f"Custom Status changed to: {last_custom_status}")
                            
                            # Emoji Changes
                            new_emoji = act.get("emoji", {})
                            if new_emoji:
                                emoji_name = new_emoji.get("name", "")
                                if emoji_name != last_emoji:
                                    last_emoji = emoji_name
                                    print(f"Emote Changed to: {last_emoji}")
                            else:
                                # if emoji is removed
                                if last_emoji:
                                    last_emoji = ""
                                    print("Emote Removed")
                            break

            if data.get("op") == 11:
                continue

    print("Connection failed! trying to connect")

keep_alive()

while True:
    try:
        asyncio.run(discord_gateway())
    except Exception as e:
        print("Hata:", e)
        asyncio.sleep(5)
