import discord
from discord.ext import commands
from discord import app_commands
import os
import json

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# ================== DATA ==================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "teams": {}
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=4)

data = load_data()

# ================== HELPERS ==================
def has_role(member, role_name):
    return any(r.name == role_name for r in member.roles)

async def get_or_create_role(guild, name):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name)
    return role

# ================== EVENTS ==================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot Ready | {bot.user}")

# ================== TEAM CREATION ==================
@bot.tree.command(name="create-team")
async def create_team(interaction: discord.Interaction, team_name: str):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message(
            "Only TEAM-LEADER can use this command.", ephemeral=True
        )

    uid = str(interaction.user.id)
    if uid in data["teams"]:
        return await interaction.response.send_message(
            "You already own a team.", ephemeral=True
        )

    role = await get_or_create_role(interaction.guild, team_name)
    await interaction.user.add_roles(role)

    data["teams"][uid] = {"team": team_name}
    save_data(data)

    await interaction.response.send_message(
        "Team created successfully.", ephemeral=True
    )

# ================== TEAM CHANNELS (NO DUPLICATION) ==================
@bot.tree.command(name="team_channels")
async def team_channels(interaction: discord.Interaction):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message(
            "Only TEAM-LEADER can use this command.", ephemeral=True
        )

    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message(
            "You do not own a team.", ephemeral=True
        )

    guild = interaction.guild
    team_name = data["teams"][uid]["team"]
    team_role = discord.utils.get(guild.roles, name=team_name)

    category = discord.utils.get(guild.categories, name="TEAMS")
    if not category:
        category = await guild.create_category("TEAMS")

    existing = [c.name for c in category.channels]

    base_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        team_role: discord.PermissionOverwrite(view_channel=True, send_messages=False)
    }

    async def create_once(name):
        if name in existing:
            return None
        ch = await guild.create_text_channel(
            name,
            category=category,
            overwrites=base_overwrites
        )
        await ch.set_permissions(interaction.user, send_messages=True)
        return ch

    await create_once("📖〢rules")
    await create_once("📢・announcements")
    await create_once("🛡・missions")

    await interaction.response.send_message(
        "Team channels checked / created successfully.", ephemeral=True
    )

# ================== CREATE CHANNEL (SPECIAL CATEGORY) ==================
@bot.tree.command(name="create_channel")
async def create_channel(
    interaction: discord.Interaction,
    name: str,
    team_can_write: bool
):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message(
            "Only TEAM-LEADER can use this command.", ephemeral=True
        )

    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message(
            "You do not own a team.", ephemeral=True
        )

    guild = interaction.guild
    team_name = data["teams"][uid]["team"]
    team_role = discord.utils.get(guild.roles, name=team_name)

    category = discord.utils.get(guild.categories, name="-----------------")
    if not category:
        category = await guild.create_category("-----------------")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        team_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=team_can_write
        )
    }

    channel = await guild.create_text_channel(
        name,
        category=category,
        overwrites=overwrites
    )

    await channel.set_permissions(interaction.user, send_messages=True)

    await interaction.response.send_message(
        "Channel created successfully.", ephemeral=True
    )

# ================== RUN ==================
bot.run(TOKEN)
