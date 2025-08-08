import os
import threading
from flask import Flask

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load env (works locally and on Render if you also set DISCORD_TOKEN in Variables)
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ====== YOUR IDs ======
GUILD_ID = 1399747611602194432
VERIFIED_ROLE_ID = 1403065664788234275
WAITING_ROOM_ROLE_ID = 1403065666243657878
# ======================

# ---------- Keep-alive web server for Render Web Service ----------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    # Render sets PORT in the environment. Default to 5000 if running local
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
# -----------------------------------------------------------------

# ---------- Discord bot setup ----------
intents = discord.Intents.default()
intents.members = True  # needed to add/remove roles

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        # sync commands only to your guild for instant availability
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔄 Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

# Slash command: /verify
@bot.tree.command(
    name="verify",
    description="Verify yourself to get access",
    guild=discord.Object(id=GUILD_ID)
)
async def verify(interaction: discord.Interaction):
    # Defer immediately to avoid 404 Unknown Interaction on slow starts
    await interaction.response.defer(ephemeral=True, thinking=True)

    guild = interaction.guild
    member = interaction.user

    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    waiting_role  = guild.get_role(WAITING_ROOM_ROLE_ID)

    if not verified_role:
        await interaction.followup.send("⚠ Verified role not found. Check the role ID.")
        return
    if not guild:
        await interaction.followup.send("⚠ This command must be used in the server.")
        return

    if verified_role in member.roles:
        await interaction.followup.send("✅ You are already verified!")
        return

    try:
        await member.add_roles(verified_role, reason="Human verification")
        if waiting_role and (waiting_role in member.roles):
            await member.remove_roles(waiting_role, reason="Human verification")
        await interaction.followup.send("🎉 You are now verified!")
    except discord.Forbidden:
        await interaction.followup.send("❌ I do not have permission to manage roles. Move my role above Verified and Waiting Room.")
    except Exception as e:
        await interaction.followup.send(f"⚠ An error occurred: {e}")

# Run both Flask and the bot
if __name__ == "__main__":
    # Start the keep‑alive server first, then the bot
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
