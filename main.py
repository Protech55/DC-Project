import asyncio
import json
import os
import requests
import websockets
from threading import Thread
from flask import Flask

# ================== SETTINGS ==================
TOKEN = os.getenv("TOKEN")
# ==============================================

headers = {"Authorization": TOKEN}

# Last known values
last_status = "online"
last_custom_status = ""
last_emoji = ""
initialized = False

r = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
if r.status_code != 200:
    print("Invalid token!")
    exit()

user = r.json()
user_id = user["id"]
print(f"Logged in as {user['username']} ({user_id})")

# Fetch current status settings from API
def fetch_current_settings():
    global last_status, last_custom_status, last_emoji
    try:
        s = requests.get("https://discord.com/api/v10/users/@me/settings", headers=headers)
        if s.status_code == 200:
            settings = s.json()
            
            # Status
            status = settings.get("status", "online")
            if status not in ["invisible", "offline"]:
                last_status = status
            
            # Custom Status
            custom = settings.get("custom_status", {})
            if custom:
                last_custom_status = custom.get("text", "")
                emoji = custom.get("emoji_name", "")
                if emoji:
                    last_emoji = emoji
            
            print(f"Fetched current settings | Status: {last_status} | Custom: {last_custom_status} | Emoji: {last_emoji}")
    except Exception as e:
        print(f"Could not fetch settings: {e}")

fetch_current_settings()

# ================== KEEP ALIVE ==================
app = Flask('')

@app.route('/')
def home():
    return f"{user['username']} | Status: {last_status} | Custom: {last_custom_status} {last_emoji}"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server = Thread(target=run)
    server.start()
# ================================================

def build_activity():
    # Return None if no custom status or emoji is set
    if not last_custom_status and not last_emoji:
        return None
    activity = {
        "name": "Custom Status",
        "type": 4,
        "state": last_custom_status,
        "id": "custom"
    }
    # Add emoji if exists
    if last_emoji:
        activity["emoji"] = {"name": last_emoji, "id": None, "animated": False}
    return activity

async def discord_gateway():
    global last_status, last_custom_status, last_emoji, initialized
    uri = "wss://gateway.discord.gg/?v=10&encoding=json"

    async with websockets.connect(uri) as ws:
        hello = json.loads(await ws.recv())
        heartbeat_interval = hello["d"]["heartbeat_interval"]

        # Send heartbeat to keep connection alive
        async def heartbeat():
            while True:
                await asyncio.sleep(heartbeat_interval / 1000)
                await ws.send(json.dumps({"op": 1, "d": None}))

        asyncio.create_task(heartbeat())

        # Connect with last known values
        activities = []
        act = build_activity()
        if act:
            activities.append(act)

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
                    "activities": activities
                }
            }
        }
        await ws.send(json.dumps(identify))
        print(f"Connected | Status: {last_status} | Custom: {last_custom_status} | Emoji: {last_emoji}")

        # Check settings from API every 60 seconds
        async def check_settings():
            global last_status, last_custom_status, last_emoji
            while True:
                await asyncio.sleep(60)
                try:
                    s = requests.get("https://discord.com/api/v10/users/@me/settings", headers=headers)
                    if s.status_code == 200:
                        settings = s.json()
                        
                        # Check status
                        new_status = settings.get("status", "online")
                        if new_status not in ["invisible", "offline"]:
                            if new_status != last_status:
                                last_status = new_status
                                print(f"Status changed: {last_status}")
                                # Send new status to gateway
                                activities = []
                                act = build_activity()
                                if act:
                                    activities.append(act)
                                update = {
                                    "op": 3,
                                    "d": {
                                        "since": None,
                                        "activities": activities,
                                        "status": last_status,
                                        "afk": False
                                    }
                                }
                                await ws.send(json.dumps(update))

                        # Check custom status
                        custom = settings.get("custom_status", {})
                        if custom:
                            new_text = custom.get("text", "")
                            new_emoji = custom.get("emoji_name", "")
                            
                            if new_text != last_custom_status or new_emoji != last_emoji:
                                last_custom_status = new_text
                                last_emoji = new_emoji
                                print(f"Custom status changed: {last_custom_status} {last_emoji}")
                                
                                # Send updated activity to gateway
                                activities = []
                                act = build_activity()
                                if act:
                                    activities.append(act)
                                update = {
                                    "op": 3,
                                    "d": {
                                        "since": None,
                                        "activities": activities,
                                        "status": last_status,
                                        "afk": False
                                    }
                                }
                                await ws.send(json.dumps(update))
                        else:
                            # Custom status was cleared
                            if last_custom_status or last_emoji:
                                last_custom_status = ""
                                last_emoji = ""
                                print("Custom status cleared")
                                update = {
                                    "op": 3,
                                    "d": {
                                        "since": None,
                                        "activities": [],
                                        "status": last_status,
                                        "afk": False
                                    }
                                }
                                await ws.send(json.dumps(update))

                except Exception as e:
                    print(f"Settings check error: {e}")

        asyncio.create_task(check_settings())

        # Listen for incoming gateway events
        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            # Heartbeat acknowledged
            if data.get("op") == 11:
                continue

    print("Connection lost, reconnecting...")

keep_alive()

# Reconnect loop
while True:
    try:
        asyncio.run(discord_gateway())
    except Exception as e:
        print(f"Error: {e}")
        asyncio.sleep(5)
