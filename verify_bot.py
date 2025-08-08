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

# Load env (works locally and on Render if you set DISCORD_TOKEN in Variables)
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ====== YOUR IDs ======
GUILD_ID = 1399747611602194432
VERIFIED_ROLE_ID = 1403065664788234275
WAITING_ROOM_ROLE_ID = 1403065666243657878
# ======================

FIRST200_PATH = "first200.json"
MAX_TRACK = 200

# ---------- Keep-alive web server for Render Web Service ----------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
# -----------------------------------------------------------------

# ---------- Discord bot setup ----------
intents = discord.Intents.default()
intents.members = True  # IMPORTANT: enable "Server Members Intent" in the Dev Portal

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory cache
first200 = []  # list of dicts: {"id": int, "name": str, "joined_at": iso8601}
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

def add_if_slot(member: discord.Member):
    """Add member to first-200 if there's space and not already captured."""
    if len(first200) >= MAX_TRACK:
        return False
    if member.id in first200_ids:
        return False

    joined_at = member.joined_at
    # joined_at can be None in rare cases, fallback to now
    ts = (joined_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()

    entry = {
        "id": member.id,
        "name": f"{member.name}#{member.discriminator}" if hasattr(member, "discriminator") else member.name,
        "joined_at": ts,
    }
    first200.append(entry)
    first200_ids.add(member.id)
    save_first200()
    return True

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    load_first200()
    try:
        # sync commands only to your guild for instant availability
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔄 Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

@bot.event
async def on_member_join(member: discord.Member):
    # Only track for the configured guild
    if member.guild and member.guild.id == GUILD_ID:
        added = add_if_slot(member)
        if added:
            print(f"➕ Tracked join: {member} ({len(first200)}/{MAX_TRACK})")

# ----------------- Verify command (unchanged, with defer) -----------------
@bot.tree.command(
    name="verify",
    description="Verify yourself to get access",
    guild=discord.Object(id=GUILD_ID)
)
async def verify(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    guild = interaction.guild
    member = interaction.user

    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    waiting_role  = guild.get_role(WAITING_ROOM_ROLE_ID)

    if not verified_role:
        await interaction.followup.send("⚠ Verified role not found. Check the role ID.")
        return

    if verified_role in member.roles:
        await interaction.followup.send("✅ You are already verified!")
        return

    try:
        # Award role and remove waiting room
        await member.add_roles(verified_role, reason="Human verification")
        if waiting_role and (waiting_role in member.roles):
            await member.remove_roles(waiting_role, reason="Human verification")

        # Also try to capture them in first-200 if there's space
        add_if_slot(member)

        await interaction.followup.send("🎉 You are now verified!")
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to manage roles. Move my role above Verified/Waiting Room.")
    except Exception as e:
        await interaction.followup.send(f"⚠ An error occurred: {e}")
# --------------------------------------------------------------------------

# ----------------- First 200 commands -----------------
@bot.tree.command(
    name="first200",
    description="Show how many first-joiners have been tracked (max 200).",
    guild=discord.Object(id=GUILD_ID)
)
async def first200_status(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"📊 Currently tracked: **{len(first200)}/{MAX_TRACK}**.",
        ephemeral=True
    )

@bot.tree.command(
    name="first200_export",
    description="Export the tracked list as a CSV.",
    guild=discord.Object(id=GUILD_ID)
)
async def first200_export(interaction: discord.Interaction):
    # Build CSV in-memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "joined_at_utc"])
    for entry in first200:
        writer.writerow([entry["id"], entry["name"], entry["joined_at"]])
    output.seek(0)

    file = discord.File(fp=io.BytesIO(output.getvalue().encode("utf-8")), filename="first200.csv")
    await interaction.response.send_message(
        content=f"📎 Exported **{len(first200)}** entries.",
        file=file,
        ephemeral=True
    )

@bot.tree.command(
    name="first200_reset",
    description="ADMIN ONLY: Reset the first-200 tracker.",
    guild=discord.Object(id=GUILD_ID)
)
async def first200_reset(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Admins only.", ephemeral=True)
        return

    first200.clear()
    first200_ids.clear()
    save_first200()
    await interaction.response.send_message("🧹 Tracker reset.", ephemeral=True)
# ------------------------------------------------------

# Run both Flask and the bot
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
