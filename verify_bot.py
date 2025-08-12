# verify_bot.py
import os
import time
import threading

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask

# ========= ENV / CONFIG =========
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1399747611602194432
VERIFIED_ROLE_ID = 1403065664788234275
WAITING_ROOM_ROLE_ID = 1403065666243657878

EARLY_ROLE_ID = 1403063368083836948   # first 200 verified get this role
EARLY_CAP = 200

# ========= Keepalive web server (for Render) =========
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ========= Discord client =========
intents = discord.Intents.default()
intents.members = True  # required for managing/reading member roles
bot = commands.Bot(command_prefix="!", intents=intents)

# ----- helpers -----
async def current_early_count(guild: discord.Guild, early_role: discord.Role) -> int:
    if early_role is None:
        return 0
    # cache count is fast and good enough for small/medium servers
    return len(early_role.members)

async def try_grant_early_role(member: discord.Member, early_role: discord.Role):
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

# ----- events -----
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔄 Synced {len(synced)} command(s) to guild {GUILD_ID}.")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

# ----- command -----
@bot.tree.command(
    name="verify",
    description="Verify yourself to get access",
    guild=discord.Object(id=GUILD_ID),
)
async def verify(interaction: discord.Interaction):
    guild: discord.Guild = interaction.guild
    member: discord.Member = interaction.user

    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    waiting_role  = guild.get_role(WAITING_ROOM_ROLE_ID)
    early_role    = guild.get_role(EARLY_ROLE_ID)

    if verified_role in member.roles:
        await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        return

    try:
        # 1) give main verified role
        if verified_role:
            await member.add_roles(verified_role, reason="Human verification passed")

        # 2) remove waiting room role if present
        if waiting_role and waiting_role in member.roles:
            await member.remove_roles(waiting_role, reason="Left waiting room")

        # 3) early role for first EARLY_CAP
        await try_grant_early_role(member, early_role)

        await interaction.response.send_message("🎉 You are now verified!", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to manage roles. Check my role position and Manage Roles.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"⚠ An error occurred: {e}", ephemeral=True)

# ========= Entrypoint with gentle login backoff =========
if __name__ == "__main__":
    # keepalive web server (Render)
    threading.Thread(target=run_web, daemon=True).start()
    time.sleep(1)

    if not TOKEN:
        print("ERROR: DISCORD_TOKEN is missing from environment")
        raise SystemExit(1)

    attempt = 1
    base_delay = 30        # seconds
    max_delay  = 10 * 60   # cap 10 minutes

    while True:
        try:
            print(f"Attempting Discord login… (attempt {attempt})")
            bot.run(TOKEN)           # blocks until disconnect or error
            print("Discord client stopped cleanly.")
            break
        except Exception as e:
            msg = str(e)
            print("Discord login failed:", msg)

            # exponential backoff: 30s, 60s, 90s … up to 10 min
            delay = min(base_delay * attempt, max_delay)

            # if a Retry-After appears in the error text, honor it
            low = msg.lower()
            if "retry-after" in low or "retry_after" in low:
                import re
                try:
                    nums = re.findall(r"(\d+\.?\d*)", msg)
                    if nums:
                        hint = int(float(max(nums, key=lambda x: float(x))))
                        delay = max(delay, hint)
                except Exception:
                    pass

            print(f"Rate-limited or login error. Sleeping {delay} seconds before retry…")
            time.sleep(delay)
            attempt += 1
