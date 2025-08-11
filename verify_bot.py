import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
import threading
from flask import Flask

# Load environment variables from .env or Render's Environment
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ====== CONFIG ======
GUILD_ID = 1399747611602194432
VERIFIED_ROLE_ID = 1403065664788234275
WAITING_ROOM_ROLE_ID = 1403065666243657878

EARLY_ROLE_ID = 1403063368083836948  # <<< NEW: put your Xeno/Xenomorph role ID here
EARLY_CAP = 200                     # <<< NEW: first 200 verified members get EARLY_ROLE_ID
# ====================

# Create a small Flask app to keep Render Web Service alive
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

# Discord bot setup
intents = discord.Intents.default()
intents.members = True  # required for counting members
bot = commands.Bot(command_prefix="!", intents=intents)

# <<< NEW: helper to count how many already have the early role
async def current_early_count(guild: discord.Guild, early_role: discord.Role) -> int:
    # Try cache first
    if early_role is None:
        return 0
    count = len(early_role.members)

    # If you want a more accurate count on larger servers, uncomment below
    # count = 0
    # async for m in guild.fetch_members(limit=None):
    #     if early_role in m.roles:
    #         count += 1

    return count

# <<< NEW: try to grant the early role if we are under the cap
async def try_grant_early_role(member: discord.Member, early_role: discord.Role):
    if early_role is None:
        return
    try:
        # already has it
        if early_role in member.roles:
            return

        count = await current_early_count(member.guild, early_role)
        if count >= EARLY_CAP:
            return

        await member.add_roles(early_role, reason="Early member bonus (first 200)")
    except discord.Forbidden:
        print("Missing permissions to add early role. Check role order and Manage Roles.")
    except Exception as e:
        print(f"Failed to grant early role: {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔄 Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

@bot.tree.command(name="verify", description="Verify yourself to get access", guild=discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    guild = interaction.guild
    member = interaction.user

    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    waiting_role = guild.get_role(WAITING_ROOM_ROLE_ID)
    early_role   = guild.get_role(EARLY_ROLE_ID)  # <<< NEW

    if verified_role in member.roles:
        await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        return

    try:
        # give main verified role
        await member.add_roles(verified_role, reason="Human verification passed")

        # remove waiting room role if present
        if waiting_role in member.roles:
            await member.remove_roles(waiting_role, reason="Left waiting room")

        # try to grant early role to first 200
        await try_grant_early_role(member, early_role)  # <<< NEW
