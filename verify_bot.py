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
XENO_ROLE_ID = 1403063368083836948
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
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

first200 = []
first200_ids = set()
list_locked = False  # NEW: prevents adding after hitting 200

def load_first200():
    global first200, first200_ids, list_locked
    if os.path.exists(FIRST200_PATH):
        try:
            with open(FIRST200_PATH, "r", encoding="utf-8") as f:
                first200 = json.load(f)
            first200_ids = {entry["id"] for entry in first200}
            if len(first200) >= MAX_TRACK:
                list_locked = True
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
    global list_locked
    if list_locked:
        return False
    if len(first200) >= MAX_TRACK:
        list_locked = True
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

    if len(first200) >= MAX_TRACK:
        list_locked = True
        print("🔒 First 200 list is now LOCKED.")

    return True

async def remove_from_list(member: discord.Member):
    """Remove member from tracker if not locked."""
    global list_locked
    if list_locked:
        return False
    if member.id in first200_ids:
        first200[:] = [m for m in first200 if m["id"] != member.id]
        first200_ids.remove(member.id)
        save_first200()
        print(f"❌ Removed {member} from first-200 list (slot freed).")
        return True
    return False

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
async def on_member_join(member: discord.Member):
    if member.guild and member.guild.id == GUILD_ID:
        added = await add_if_slot(member)
        if added:
            print(f"➕ Tracked join: {member} ({len(first200)}/{MAX_TRACK})")

@bot.event
async def on_member_remove(member: discord.Member):
    if member.guild and member.guild.id == GUILD_ID:
        removed = await remove_from_list(member)
        if removed:
            # Remove Xeno role from them if rejoin happens before lock
            print(f"🚫 {member} left before list lock — slot freed.")
# -------- /verify command --------
@bot.tree.command(name="verify", description="Verify yourself to get access", guild=discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    member = interaction.user

    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    waiting_role  = guild.get_role(WAITING_ROOM_ROLE_ID)

    if verified_role in member.roles:
        await interaction.followup.send("✅ You are already verified!")
        return

    try:
        await member.add_roles(verified_role, reason="Human verification")
        if waiting_role in member.roles:
            await member.remove_roles(waiting_role, reason="Human verification")

        await add_if_slot(member)

        await interaction.followup.send("🎉 You are now verified!")
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to manage roles. Move my role above target roles.")
    except Exception as e:
        await interaction.followup.send(f"⚠ An error occurred: {e}")

# -------- First 200 commands --------
@bot.tree.command(name="first200", description="Show how many have been tracked", guild=discord.Object(id=GUILD_ID))
async def first200_status(interaction: discord.Interaction):
    status = f"📊 Currently tracked: **{len(first200)}/{MAX_TRACK}**."
    if list_locked:
        status += " 🔒 List is locked."
    await interaction.response.send_message(status, ephemeral=True)

@bot.tree.command(name="first200_export", description="Export tracked list as CSV", guild=discord.Object(id=GUILD_ID))
async def first200_export(interaction: discord.Interaction):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "joined_at"])
    for entry in first200:
        writer.writerow([entry["id"], entry["name"], entry["joined_at"]])
    output.seek(0)
    file = discord.File(fp=io.BytesIO(output.getvalue().encode("utf-8")), filename="first200.csv")
    await interaction.response.send_message(content=f"📎 Exported **{len(first200)}** entries.", file=file, ephemeral=True)

@bot.tree.command(name="first200_reset", description="Reset the tracker (admin only)", guild=discord.Object(id=GUILD_ID))
async def first200_reset(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Admins only.", ephemeral=True)
        return
    first200.clear()
    first200_ids.clear()
    global list_locked
    list_locked = False
    save_first200()
    await interaction.response.send_message("🧹 Tracker reset.", ephemeral=True)

# -------- Run bot + keepalive --------
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
