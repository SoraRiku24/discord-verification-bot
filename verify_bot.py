import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ====== CONFIG ======
GUILD_ID = 1399747611602194432
VERIFIED_ROLE_ID = 1403065664788234275
WAITING_ROOM_ROLE_ID = 1403065666243657878
# ====================

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

    if verified_role in member.roles:
        await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
        return

    try:
        await member.add_roles(verified_role)
        if waiting_role in member.roles:
            await member.remove_roles(waiting_role)
        await interaction.response.send_message("🎉 You are now verified!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to manage roles. Check my role position.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"⚠ An error occurred: {e}", ephemeral=True)

bot.run(TOKEN)
