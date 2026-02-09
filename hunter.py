import discord
from discord.ext import commands
from discord import app_commands
import os, json, aiohttp

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# ================= DATA =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "teams": {},
            "join_requests": {},
            "points": {},
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

    msg = await channel.fetch_message(data["leaderboard_msg_id"])
    top = sorted(data["points"].items(), key=lambda x: x[1], reverse=True)[:10]
    text = "**🏆 Top 10 Players 🏆**\n"
    for i, (uid, pts) in enumerate(top, start=1):
        user = await bot.fetch_user(int(uid))
        text += f"{i}. {user.name} - {pts} points\n"
    await msg.edit(content=text)

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot Ready")

# ================= TEAM SYSTEM =================
@bot.tree.command(name="create-team")
async def create_team(interaction: discord.Interaction, team_name: str):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("Only TEAM-LEADER.", ephemeral=True)

    uid = str(interaction.user.id)
    if uid in data["teams"]:
        return await interaction.response.send_message("You already have a team.", ephemeral=True)

    role = await get_or_create_role(interaction.guild, team_name)
    await interaction.user.add_roles(role)

    data["teams"][uid] = team_name
    data["join_requests"][team_name] = []
    save_data()

    await interaction.response.send_message("Team created.", ephemeral=True)

@bot.tree.command(name="team-join")
async def team_join(interaction: discord.Interaction, team_name: str):
    if team_name not in data["join_requests"]:
        return await interaction.response.send_message("Team not found.", ephemeral=True)

    if interaction.user.id in data["join_requests"][team_name]:
        return await interaction.response.send_message("Already requested.", ephemeral=True)

    data["join_requests"][team_name].append(interaction.user.id)
    save_data()

    for leader_id, t in data["teams"].items():
        if t == team_name:
            leader = interaction.guild.get_member(int(leader_id))
            if leader:
                await leader.send(f"{interaction.user.name} requested to join **{team_name}**")

    await interaction.response.send_message("Request sent.", ephemeral=True)

@bot.tree.command(name="team-accept")
async def team_accept(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message("Not a leader.", ephemeral=True)

    team = data["teams"][leader_id]
    if member.id not in data["join_requests"][team]:
        return await interaction.response.send_message("No request.", ephemeral=True)

    role = discord.utils.get(interaction.guild.roles, name=team)
    await member.add_roles(role)

    data["join_requests"][team].remove(member.id)
    save_data()

    await interaction.response.send_message("Member accepted.", ephemeral=True)

@bot.tree.command(name="remove-team")
async def remove_team(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message("Not a leader.", ephemeral=True)

    team = data["teams"][leader_id]
    role = discord.utils.get(interaction.guild.roles, name=team)

    if role in member.roles:
        await member.remove_roles(role)
        await interaction.response.send_message("Removed.", ephemeral=True)

# ================= TEAM CHANNELS =================
@bot.tree.command(name="team_channels")
async def team_channels(interaction: discord.Interaction):
    team = data["teams"].get(str(interaction.user.id))
    if not team:
        return await interaction.response.send_message("No team.", ephemeral=True)

    guild = interaction.guild
    role = discord.utils.get(guild.roles, name=team)

    category = discord.utils.get(guild.categories, name=f"{team}-CATEGORY")
    if not category:
        category = await guild.create_category(f"{team}-CATEGORY")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
        interaction.user: discord.PermissionOverwrite(send_messages=True)
    }

    async def create(name):
        if not discord.utils.get(category.channels, name=name):
            await guild.create_text_channel(name, category=category, overwrites=overwrites)

    await create("📖〢rules")
    await create("📢・announcements")
    await create("🛡・missions")

    await interaction.response.send_message("Channels ready.", ephemeral=True)

# ================= CHANNEL CONTROL =================
@bot.tree.command(name="delete_channel")
async def delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    team = data["teams"].get(str(interaction.user.id))
    if not team or not channel.category or channel.category.name != f"{team}-CATEGORY":
        return await interaction.response.send_message("Not your channel.", ephemeral=True)

    await channel.delete()
    await interaction.response.send_message("Deleted.", ephemeral=True)

@bot.tree.command(name="move_channel")
async def move_channel(interaction: discord.Interaction, channel: discord.TextChannel, position: int):
    team = data["teams"].get(str(interaction.user.id))
    if not team or not channel.category or channel.category.name != f"{team}-CATEGORY":
        return await interaction.response.send_message("Not your channel.", ephemeral=True)

    await channel.edit(position=position)
    await interaction.response.send_message("Moved.", ephemeral=True)

# ================= MISSIONS (MODIFIED ONLY) =================
@bot.tree.command(name="create_mission")
async def create_mission(interaction: discord.Interaction, roblox_username: str):
    team = data["teams"].get(str(interaction.user.id))
    if not team:
        return await interaction.response.send_message("No team.", ephemeral=True)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [roblox_username]}
        ) as r:
            res = await r.json()
            if not res["data"]:
                return await interaction.response.send_message("Roblox user not found.", ephemeral=True)
            user_id = res["data"][0]["id"]

        async with session.get(
            f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png"
        ) as r:
            img = await r.json()
            avatar = img["data"][0]["imageUrl"]

    embed = discord.Embed(
        title="🛡 New Mission",
        description=f"Target: **{roblox_username}**",
        color=discord.Color.red()
    )
    embed.set_image(url=avatar)

    category = discord.utils.get(interaction.guild.categories, name=f"{team}-CATEGORY")
    for ch in category.text_channels:
        if ch.name == "🛡・missions":
            await ch.send(embed=embed)

    await interaction.response.send_message("Mission created.", ephemeral=True)

# ================= RUN =================
bot.run(TOKEN)
