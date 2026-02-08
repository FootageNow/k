import discord
from discord.ext import commands
from discord import app_commands
import os, json

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# ================= DATA =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "teams": {},
            "points": {},
            "join_requests": {},
            "leaderboard_channel": None,
            "leaderboard_msg_id": None,
            "blacklist_roles": {}
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# ================= HELPERS =================
def has_role(member, name):
    return any(r.name == name for r in member.roles)

async def get_or_create_role(guild, name):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name)
    return role

async def update_leaderboard():
    if not data["leaderboard_channel"] or not data["leaderboard_msg_id"]:
        return
    channel = bot.get_channel(data["leaderboard_channel"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(data["leaderboard_msg_id"])
        top = sorted(data["points"].items(), key=lambda x: x[1], reverse=True)[:10]
        text = "**🏆 Top 10 Players 🏆**\n"
        for i, (uid, pts) in enumerate(top, start=1):
            user = await bot.fetch_user(int(uid))
            text += f"{i}. {user.name} - {pts} points\n"
        await msg.edit(content=text)
    except:
        pass

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot ready as {bot.user}")

# ================= POINTS =================
@bot.tree.command(name="give-points")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def give_points(interaction: discord.Interaction, member: discord.Member, points: int):
    uid = str(member.id)
    data["points"][uid] = data["points"].get(uid, 0) + points
    save_data()
    await update_leaderboard()
    await interaction.response.send_message("Points updated.", ephemeral=True)

@bot.tree.command(name="points-leaderboard")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def leaderboard(interaction: discord.Interaction):
    msg = await interaction.channel.send("Loading leaderboard...")
    data["leaderboard_channel"] = interaction.channel.id
    data["leaderboard_msg_id"] = msg.id
    save_data()
    await update_leaderboard()
    await interaction.response.send_message("Leaderboard created.", ephemeral=True)

# ================= TEAM =================
@bot.tree.command(name="create-team")
async def create_team(interaction: discord.Interaction, team_name: str):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("Only TEAM-LEADER can use this.", ephemeral=True)

    uid = str(interaction.user.id)
    if uid in data["teams"]:
        return await interaction.response.send_message("You already own a team.", ephemeral=True)

    role = await get_or_create_role(interaction.guild, team_name)
    await interaction.user.add_roles(role)

    data["teams"][uid] = {"team": team_name}
    save_data()
    await interaction.response.send_message("Team created successfully.", ephemeral=True)

# ================= TEAM CHANNELS =================
@bot.tree.command(name="team_channels")
async def team_channels(interaction: discord.Interaction):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("Only TEAM-LEADER can use this.", ephemeral=True)

    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message("You do not own a team.", ephemeral=True)

    guild = interaction.guild
    team_name = data["teams"][uid]["team"]
    team_role = discord.utils.get(guild.roles, name=team_name)

    category = discord.utils.get(guild.categories, name="TEAMS")
    if not category:
        category = await guild.create_category("TEAMS")

    existing = [c.name for c in category.channels]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        team_role: discord.PermissionOverwrite(view_channel=True, send_messages=False)
    }

    async def create_once(name):
        if name in existing:
            return
        ch = await guild.create_text_channel(name, category=category, overwrites=overwrites)
        await ch.set_permissions(interaction.user, send_messages=True)

    await create_once("📖〢rules")
    await create_once("📢・announcements")
    await create_once("🛡・missions")

    await interaction.response.send_message("Team channels ready.", ephemeral=True)

# ================= CUSTOM CHANNEL =================
@bot.tree.command(name="create_channel")
async def create_channel(interaction: discord.Interaction, name: str, team_can_write: bool):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("Only TEAM-LEADER can use this.", ephemeral=True)

    uid = str(interaction.user.id)
    guild = interaction.guild
    team_name = data["teams"][uid]["team"]
    team_role = discord.utils.get(guild.roles, name=team_name)

    category = discord.utils.get(guild.categories, name="-----------------")
    if not category:
        category = await guild.create_category("-----------------")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        team_role: discord.PermissionOverwrite(view_channel=True, send_messages=team_can_write)
    }

    ch = await guild.create_text_channel(name, category=category, overwrites=overwrites)
    await ch.set_permissions(interaction.user, send_messages=True)

    await interaction.response.send_message("Channel created.", ephemeral=True)

# ================= CHANNEL MANAGEMENT =================
@bot.tree.command(name="delete_channel")
async def delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("Only TEAM-LEADER can use this.", ephemeral=True)

    await channel.delete()
    await interaction.response.send_message("Channel deleted.", ephemeral=True)

@bot.tree.command(name="move_channel")
async def move_channel(interaction: discord.Interaction, channel: discord.TextChannel, position: int):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("Only TEAM-LEADER can use this.", ephemeral=True)

    await channel.edit(position=position)
    await interaction.response.send_message("Channel moved.", ephemeral=True)

@bot.tree.command(name="grant_write")
async def grant_write(interaction: discord.Interaction, channel: discord.TextChannel, member: discord.Member):
    ow = channel.overwrites_for(member)
    ow.send_messages = True
    await channel.set_permissions(member, overwrite=ow)
    await interaction.response.send_message("Write permission granted.", ephemeral=True)

@bot.tree.command(name="remove_write")
async def remove_write(interaction: discord.Interaction, channel: discord.TextChannel, member: discord.Member):
    ow = channel.overwrites_for(member)
    ow.send_messages = False
    await channel.set_permissions(member, overwrite=ow)
    await interaction.response.send_message("Write permission removed.", ephemeral=True)

# ================= RUN =================
bot.run(TOKEN)
