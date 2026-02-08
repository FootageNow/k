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
            "teams": {},
            "points": {},
            "join_requests": {},
            "leaderboard_msg_id": None,
            "leaderboard_channel": None,
            "blacklist_roles": {}
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

# ================== TEAM SYSTEM ==================
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

# ================== TEAM CHANNELS ==================
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

    # base: only team role can SEE, nobody else
    base_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        team_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False
        )
    }

    rules = await guild.create_text_channel(
        "📖〢rules",
        category=category,
        overwrites=base_overwrites
    )
    await rules.set_permissions(
        interaction.user,
        send_messages=True
    )

    announcements = await guild.create_text_channel(
        "📢・announcements",
        category=category,
        overwrites=base_overwrites
    )
    await announcements.set_permissions(
        interaction.user,
        send_messages=True
    )

    missions = await guild.create_text_channel(
        "🛡・missions",
        category=category,
        overwrites=base_overwrites
    )
    await missions.set_permissions(
        interaction.user,
        send_messages=True
    )

    await interaction.response.send_message(
        "Team channels created successfully.", ephemeral=True
    )

# ================== CHANNEL MANAGEMENT ==================
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
    category = discord.utils.get(guild.categories, name="TEAMS")

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

    # leader can always write
    await channel.set_permissions(interaction.user, send_messages=True)

    await interaction.response.send_message(
        "Channel created successfully.", ephemeral=True
    )

@bot.tree.command(name="delete_channel")
async def delete_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message(
            "Only TEAM-LEADER can use this command.", ephemeral=True
        )

    if channel.category and channel.category.name == "TEAMS":
        await channel.delete()
        await interaction.response.send_message(
            "Channel deleted.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "You can only delete team channels.", ephemeral=True
        )

@bot.tree.command(name="move_channel")
async def move_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    position: int
):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message(
            "Only TEAM-LEADER can use this command.", ephemeral=True
        )

    await channel.edit(position=position)
    await interaction.response.send_message(
        "Channel position updated.", ephemeral=True
    )

@bot.tree.command(name="grant_write")
async def grant_write(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    member: discord.Member
):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message(
            "Only TEAM-LEADER can use this command.", ephemeral=True
        )

    ow = channel.overwrites_for(member)
    ow.send_messages = True
    await channel.set_permissions(member, overwrite=ow)

    await interaction.response.send_message(
        "Write permission granted.", ephemeral=True
    )

@bot.tree.command(name="remove_write")
async def remove_write(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    member: discord.Member
):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message(
            "Only TEAM-LEADER can use this command.", ephemeral=True
        )

    ow = channel.overwrites_for(member)
    ow.send_messages = False
    await channel.set_permissions(member, overwrite=ow)

    await interaction.response.send_message(
        "Write permission removed.", ephemeral=True
    )

# ================== RUN ==================
bot.run(TOKEN)
