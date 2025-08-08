import os
import json
import csv
import io
import threading
from datetime import datetime, timezone
from flask import Flask

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ====== CONFIG ======
GUILD_ID = 1399747611602194432
VERIFIED_ROLE_ID = 1403065664788234275
WAITING_ROOM_ROLE_ID = 1403065666243657878
XENO_ROLE_ID = 1403063368083836948  # NEW: Xeno role for first 200
MAX_TRACK = 200
FIRST200_PATH = "first200.json"
# ====================

# ---------- Keep-alive web server ----------
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot is running!"
def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
# --------------------------------------------

# ---------- Discord bot setup ----------
intents = discord.Intents.default()
intents.members = True  # Must be enabled in Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)

first200 = []
first200_ids = set()

def load_first200():
    global first200, first200_ids
    if os.path.exists(FIRST200_PATH):
        try:
            with open(FIRST200_PATH, "r", encoding="utf-8") as f:
                first200 = json.load(f)
            first200_ids = {entry["id"] for entry in first200}
            print(f"📥 Loaded {len(first200)} entries from {FIRST200_PATH}")
        except Exception as e:
            print(f"⚠ Failed to load {FIRST200_PATH}: {e}")

def save_first200():
    try:
        with open(FIRST200_PATH, "w", encoding="utf-8") as f:
            json.dump(first200, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved {len(first200)} entries to {FIRST200_PATH}")
    except Exception as e:
        print(f"⚠ Failed to save {FIRST200_PATH}: {e}")

async def add_if_slot(member: discord.Member):
    """Add member to first-200 if slot is available, give Xeno role."""
    if len(first200) >= MAX_TRACK:
        return False
    if member.id in first200_ids:
        return False

    ts = (member.joined_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    entry = {
        "id": member.id,
        "name": f"{member.name}#{member.discriminator}",
        "joined_at": ts,
    }
    first200.append(entry)
    first200_ids.add(member.id)
    save_first200()

    # Assign Xeno role
    xeno_role = member.guild.get_role(XENO_ROLE_ID)
    if xeno_role:
        try:
            await member.add_roles(xeno_role, reason="First 200 joiners")
            print(f"🏅 Gave Xeno role to {member}")
        except discord.Forbidden:
            print(f"⚠ Missing permission to give Xeno role to {member}")
    else:
        print("⚠ Xeno role not found in guild!")

    return True

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    load_first200()
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔄 Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

@bot.event
async d
