# verify_bot.py
import os
import threading
import time

import discord
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask

# =========================
# Load environment variables
# =========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ---------- Guild & Roles ----------
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# The role a user should receive after running /verify (your normal access role)
VERIFIED_ROLE_ID = int(os.getenv("VERIFIED_ROLE_ID", "0"))

# Optional: a "waiting room" role you want to remove after verification
WAITING_ROOM_ROLE_ID = int(os.getenv("WAITING_ROOM_ROLE_ID", "0"))

# Early role settings — the first EARLY_CAP members who verify get this bonus role
EARLY_ROLE_ID = int(os.getenv("EARLY_ROLE_ID", "0"))
EARLY_CAP = int(os.getenv("EARLY_CAP", "200"))

# =========================
# Flask keepalive web server
# =========================
app = Flask(__name__)

@app.get("/")
def home():
    return "Human verification bot is running!"

def run_web():
    # Render provides $PORT, default to 5000 for local
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

# =========================
# Discord bot setup
# =========================
intents = discord.Intents.default()
# Needed so we can see members and their roles to count / grant roles
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------- Helpers -------------
async def current_early_count(guild: discord.Guild, early_role: discord.Role) -> int:
    """
    Count how many members currently have the early role.

    Fast path (good for small/medium servers): use the role's cached members list.
    If you want maximum accuracy on very large servers immediately after a restart,
    swap to the fetch_members loop below (slower, but exact).
    """
    if early_role is None:
        return 0

    # Fast cached count:
    return len(early_role.members)

    # Exact but slower:
    # count = 0
    # async for m in guild.fetch_members(limit=None):
    #     if early_role in m.roles:
    #         count += 1
    # return count

async def try_grant_early_role(member: discord.Member, early_role: discord.Role):
    """
    Give EARLY_ROLE_ID to the member if:
      - early_role exists
      - member doesn't already have it
      - total holders < EARLY_CAP
    """
    if early_role is None:
        return
    try:
        if early_role in member.roles:
            return

        count = await current_early_count(member.guild, early_role)
        if count >= EARLY_CAP:
            return

        await member.add_roles(early_role, reason=f"Early member bonus (first {EARLY_CAP})")
    except discord.Forbidden:
        print("[WARN] Missing permission to add early role. Check Manage Roles and role order.")
    except Exception as e:
        print(f"[ERROR] Failed to grant early role: {e}")

# ------------- Events -------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    # Sync slash commands to the guild for instant availability
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔄 Synced {len(synced)} command(s) to guild {GUILD_ID}.")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

# ------------- Commands -------------
@bot.tree.command(name="verify", description="Verify yourself to get access", guild=discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    guild: discord.Guild = interaction.guild
    member: discord.Member = interaction.user  # the user who ran the command

    verified_role = guild.get_role(VERIFIED_ROLE_ID) if VERIFIED_ROLE_ID else None
    waiting_role = guild.get_role(WAITING_ROOM_ROLE_ID) if WAITING_ROOM_ROLE_ID else None
    early_role   = guild.get_role(EARLY_ROLE_ID) if EARLY_ROLE_ID else None

    if verified_role and verified_role in member.roles:
        await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        return

    try:
        # 1) Give the main verified role
        if verified_role:
            await member.add_roles(verified_role, reason="Human verification passed")

        # 2) Remove waiting room role if present
        if waiting_role and waiting_role in member.roles:
            await member.remove_roles(waiting_role, reason="Left waiting room")

        # 3) Try to give the early role if under cap
        await try_grant_early_role(member, early_role)

        await interaction.response.send_message("🎉 You are now verified!", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to manage roles. Check my role position and Manage Roles.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"⚠ An error occurred: {e}", ephemeral=True)

# =========================
# Entrypoint
# =========================
if __name__ == "__main__":
    # Start the keepalive web server in a background thread (for Render)
    threading.Thread(target=run_web, daemon=True).start()
    # Give Flask a moment to start
    time.sleep(1)
    # Run the Discord bot
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set")
    bot.run(TOKEN)
