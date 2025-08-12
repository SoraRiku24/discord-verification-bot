# verify_bot.py
import os
import asyncio
import threading
import logging
from typing import Optional

from dotenv import load_dotenv
from flask import Flask

import discord
from discord.ext import commands

# =========================
# Environment / Config
# =========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

def _env_int(name: str, default: Optional[int] = None) -> Optional[int]:
    v = os.getenv(name)
    try:
        return int(v) if v else default
    except Exception:
        return default

# IDs (env overrides allowed; defaults are your server/roles)
GUILD_ID              = _env_int("GUILD_ID",              1399747611602194432)
VERIFIED_ROLE_ID      = _env_int("VERIFIED_ROLE_ID",      1403065664788234275)
WAITING_ROOM_ROLE_ID  = _env_int("WAITING_ROOM_ROLE_ID",  1403065666243657878)
EARLY_ROLE_ID         = _env_int("EARLY_ROLE_ID",         1403063368083836948)  # "Xeno" early role
EARLY_CAP             = _env_int("EARLY_CAP",             200)                  # first N get early role

# =========================
# Logging
# =========================
logging.basicConfig(level=logging.INFO)
try:
    discord.utils.setup_logging(level=logging.INFO)  # discord.py v2+
except Exception:
    pass

# =========================
# Keep-alive (Render)
# =========================
app = Flask(__name__)

@app.get("/")
def home():
    return "Human verification bot is running!"

def run_web():
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

# =========================
# Discord bot setup
# =========================
# We only need guilds + members for slash commands and role edits.
intents = discord.Intents.none()
intents.guilds = True
intents.members = True
intents.message_content = True  # add this line

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- Diagnostics ----------
@bot.event
async def on_connect():
    print(">>> on_connect (Gateway connected)")

@bot.event
async def on_ready():
    print(f">>> READY as {bot.user} ({bot.user.id}) in {len(bot.guilds)} guild(s)")

@bot.event
async def on_disconnect():
    print(">>> on_disconnect (Gateway disconnected)")

@bot.event
async def on_error(event, *args, **kwargs):
    import traceback
    print(f"[on_error] event={event}")
    traceback.print_exc()

# =========================
# Early role helpers
# =========================
async def current_early_count(guild: discord.Guild, early_role: Optional[discord.Role]) -> int:
    """Count how many members currently have the early role."""
    if early_role is None:
        return 0
    return len(early_role.members)  # cached, fast

async def try_grant_early_role(member: discord.Member, early_role: Optional[discord.Role]):
    """Grant EARLY_ROLE_ID if under the EARLY_CAP."""
    if early_role is None:
        return
    try:
        if early_role in member.roles:
            return
        count = await current_early_count(member.guild, early_role)
        if (EARLY_CAP or 0) and count >= EARLY_CAP:
            return
        await member.add_roles(early_role, reason=f"Early member bonus (first {EARLY_CAP})")
    except discord.Forbidden:
        print("[early] Missing permissions to add early role. Check Manage Roles & role order.")
    except Exception as e:
        print(f"[early] Failed to grant early role: {e}")

# =========================
# Command sync on startup
# =========================
@bot.event
async def setup_hook():
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f">>> Synced {len(synced)} command(s) to guild {GUILD_ID}")
    except Exception as e:
        print(f">>> Command sync failed: {e}")

# =========================
# Slash command: /verify
# =========================
@bot.tree.command(
    name="verify",
    description="Verify yourself to get access",
    guild=discord.Object(id=GUILD_ID),
)
async def verify(interaction: discord.Interaction):
    try:
        # Acknowledge fast to avoid 3s timeout
        await interaction.response.defer(ephemeral=True)

        guild: discord.Guild = interaction.guild
        member: discord.Member = interaction.user

        verified_role     = guild.get_role(VERIFIED_ROLE_ID)     if VERIFIED_ROLE_ID     else None
        waiting_room_role = guild.get_role(WAITING_ROOM_ROLE_ID) if WAITING_ROOM_ROLE_ID else None
        early_role        = guild.get_role(EARLY_ROLE_ID)        if EARLY_ROLE_ID        else None

        if not verified_role:
            await interaction.followup.send(
                "❌ I can't find the **Verified** role. Check the role ID in my config.",
                ephemeral=True
            )
            return

        if verified_role in member.roles:
            await interaction.followup.send("✅ You are already verified!", ephemeral=True)
            return

        # Grant verified
        try:
            await member.add_roles(verified_role, reason="Human verification passed")
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to manage roles. "
                "Give me **Manage Roles** and place my bot role **above** the roles I assign.",
                ephemeral=True
            )
            return

        # Remove waiting room, if present
        try:
            if waiting_room_role and waiting_room_role in member.roles:
                await member.remove_roles(waiting_room_role, reason="Left waiting room")
        except Exception:
            pass

        # Try the early role
        await try_grant_early_role(member, early_role)

        await interaction.followup.send("🎉 You are now verified!", ephemeral=True)

    except Exception as e:
        import traceback
        print("[/verify] unhandled error:", e)
        print(traceback.format_exc())
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⚠️ Something went wrong. Please try again.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "⚠️ Something went wrong. Please try again.", ephemeral=True
                )
        except Exception:
            pass

# =========================
# Gentle login backoff
# =========================
async def start_with_backoff():
    if not TOKEN:
        print("DISCORD_TOKEN is missing from env.")
        raise SystemExit(1)

    delay = 5
    while True:
        try:
            print("Attempting Discord login…")
            await bot.start(TOKEN)  # returns only on close/exception
            break
        except Exception as e:
            msg = getattr(e, "message", str(e))
            # If Cloudflare/429 is returned, you could increase delay here
            print(f"❌ Login/start failed: {msg} — retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay + 5, 60)  # 5s, 10s, … up to 60s

# =========================
# Entrypoint
# =========================
if __name__ == "__main__":
    # Start the keepalive web server (for Render)
    threading.Thread(target=run_web, daemon=True).start()
    # Start Discord client with backoff
    asyncio.run(start_with_backoff())
