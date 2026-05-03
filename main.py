import asyncio
import json
import os
import requests
import websockets
from threading import Thread
from flask import Flask

# ================== SETTINGS ==================
TOKEN = os.getenv("TOKEN")
CUSTOM_STATUS = os.getenv("CUSTOM_STATUS", "Hello!")
EMOJI = os.getenv("EMOJI", "")
# ==============================================

headers = {"Authorization": TOKEN}
last_status = None

r = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
if r.status_code != 200:
    print("Invalid token!")
    exit()

user = r.json()
print(f"Logged in as {user['username']} ({user['id']})")

# ================== KEEP ALIVE ==================
app = Flask('')

@app.route('/')
def home():
    return f"{user['username']} | Status: {last_status} | Custom: {CUSTOM_STATUS}"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server = Thread(target=run)
    server.start()
# ================================================

def build_activity():
    activity = {
        "name": "Custom Status",
        "type": 4,
        "state": CUSTOM_STATUS,
        "id": "custom"
    }
    if EMOJI:
        activity["emoji"] = {"name": EMOJI, "id": None, "animated": False}
    return activity

async def discord_gateway():
    global last_status
    uri = "wss://gateway.discord.gg/?v=10&encoding=json"

    async with websockets.connect(uri) as ws:
        hello = json.loads(await ws.recv())
        heartbeat_interval = hello["d"]["heartbeat_interval"]

        async def heartbeat():
            while True:
                await asyncio.sleep(heartbeat_interval / 1000)
                await ws.send(json.dumps({"op": 1, "d": None}))

        asyncio.create_task(heartbeat())

        # change status
        connect_status = last_status if last_status else "online"

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
                    "status": connect_status,
                    "afk": False,
                    "activities": [build_activity()]
                }
            }
        }
        await ws.send(json.dumps(identify))
        print(f"Connected | Status: {connect_status} | Custom: {CUSTOM_STATUS}")

        async def refresh_status():
            while True:
                await asyncio.sleep(30)
                # last_status None no refresh
                if last_status is None:
                    continue
                update = {
                    "op": 3,
                    "d": {
                        "since": None,
                        "activities": [build_activity()],
                        "status": last_status,
                        "afk": False
                    }
                }
                await ws.send(json.dumps(update))
                print(f"Status refreshed | Status: {last_status} | Custom: {CUSTOM_STATUS}")

        asyncio.create_task(refresh_status())

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            # READY event
            if data.get("t") == "READY":
                try:
                    # take precence information
                    presences = data["d"].get("presences", [])
                    for p in presences:
                        if p.get("user", {}).get("id") == user["id"]:
                            status = p.get("status")
                            if status and status not in ["invisible", "offline"]:
                                last_status = status
                                print(f"Initial status detected: {last_status}")
                            break

                    # if precense empty, accept as empty
                    if last_status is None:
                        last_status = "online"
                        print(f"No initial status found, defaulting to: {last_status}")
                except Exception as e:
                    print(f"Error reading READY: {e}")
                    last_status = "online"

            # PRESENCE_UPDATE - change status only if update
            if data.get("t") == "PRESENCE_UPDATE":
                presence = data.get("d", {})
                if presence.get("user", {}).get("id") == user["id"]:
                    new_status = presence.get("status")
                    if new_status and new_status not in ["invisible", "offline"]:
                        if new_status != last_status:
                            last_status = new_status
                            print(f"Status changed: {last_status}")

            if data.get("op") == 11:
                continue

    print("Connection lost, reconnecting...")

keep_alive()

while True:
    try:
        asyncio.run(discord_gateway())
    except Exception as e:
        print(f"Error: {e}")
        asyncio.sleep(5)
