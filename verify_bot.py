# verify_bot.py
import os
import threading
import time

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask

# ========= ENV =========
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Required
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
VERIFIED_ROLE_ID = int(os.getenv("VERIFIED_ROLE_ID", "0"))

# Optional: waiting room role & early role
WAITING_ROOM_ROLE_ID = int(os.getenv("WAITING_ROOM_ROLE_ID", "0"))
EARLY_ROLE_ID = int(os.getenv("EARLY_ROLE_ID", "0"))
EARLY_CAP = int(os.getenv("EARLY_CAP", "200"))

# ========= Flask keepalive (Render Web Service) =========
app = Flask(__name__)

@app.get("/")
def home():
    return "Human verification bot is running."

def run_web():
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

# ========= Discord client =========
intents = discord.Intents.default()
intents.members = True  # needed to see members and manage roles
client = commands.Bot(command_prefix="!", intents=intents)

# Helper: count early role holders
async def early_count(guild: discord.Guild, role: discord.Role) -> int:
    return len(role.members) if role else 0

async def try_grant_early(member: discord.Member, early_role: discord.Role):
    if not early_role:
        return
    try:
        if early_role in member.roles:
            return
        count = await early_count(member.guild, early_role)
        if count < EARLY_CAP:
            await member.add_roles(early_role, reason=f"Early bonus (first {EARLY_CAP})")
    except discord.Forbidden:
        print("[WARN] Missing permission to add early role. Check Manage Roles & role order.")
    except Exception as e:
        print("[ERROR] early role:", e)

# ========= Events =========
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (id={client.user.id})")
    try:
        synced = await client.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔄 Synced {len(synced)} command(s) to guild {GUILD_ID}.")
    except Exception as e:
        print("❌ Slash command sync failed:", e)

# ========= /verify =========
@client.tree.command(name="verify", description="Verify yourself to get access", guild=discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    guild: discord.Guild = interaction.guild
    member: discord.Member = interaction.user

    verified_role = guild.get_role(VERIFIED_ROLE_ID) if VERIFIED_ROLE_ID else None
    waiting_role  = guild.get_role(WAITING_ROOM_ROLE_ID) if WAITING_ROOM_ROLE_ID else None
    early_role    = guild.get_role(EARLY_ROLE_ID) if EARLY_ROLE_ID else None

    if verified_role and verified_role in member.roles:
        await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        return

    try:
        if verified_role:
            await member.add_roles(verified_role, reason="Human verification passed")
        if waiting_role and waiting_role in member.roles:
            await member.remove_roles(waiting_role, reason="Left waiting room")
        await try_grant_early(member, early_role)
        await interaction.response.send_message("🎉 You are now verified!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to manage roles. Check my role position and Manage Roles.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"⚠ An error occurred: {e}", ephemeral=True)

# ========= Entrypoint =========
if __name__ == "__main__":
    # Start web server (Render Web Service)
    threading.Thread(target=run_web, daemon=True).start()
    time.sleep(1)

    # Loud login logs so we can see issues in Render
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN is missing from environment")
        raise SystemExit(1)

    print("Attempting Discord login…")
    try:
        client.run(TOKEN)
    except Exception as e:
        print("Discord login failed:", e)
        raise
