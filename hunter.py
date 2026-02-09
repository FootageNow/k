# ========================= IMPORTS =========================
import discord
from discord.ext import commands
from discord import app_commands
import os, json, aiohttp

# ========================= CONFIG =========================
TOKEN = os.getenv("TOKEN")
DATA_FILE = "data.json"

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ========================= DATA =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "teams": {},
            "join_requests": {},
            "points": {},
            "leaderboard_channel": None,
            "leaderboard_msg_id": None,
            "team_lb_channel": None,
            "team_lb_msg_id": None,
            "blacklist_roles": {}
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# ========================= HELPERS =========================
def has_role(member, name):
    return any(r.name == name for r in member.roles)

async def get_or_create_role(guild, name):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name)
    return role

# ========================= PLAYER LEADERBOARD =========================
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
            text += f"{i}. {user.name} — {pts} points\n"
        await msg.edit(content=text)
    except:
        pass

# ========================= TEAM LEADERBOARD =========================
async def update_team_leaderboard(guild):
    if not data["team_lb_channel"] or not data["team_lb_msg_id"]:
        return
    channel = guild.get_channel(data["team_lb_channel"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(data["team_lb_msg_id"])
        teams_points = {}

        for leader_id, team_name in data["teams"].items():
            role = discord.utils.get(guild.roles, name=team_name)
            if not role:
                continue
            total = 0
            for member in role.members:
                total += data["points"].get(str(member.id), 0)
            teams_points[team_name] = total

        sorted_teams = sorted(teams_points.items(), key=lambda x: x[1], reverse=True)[:10]

        text = "**🏆 Top 10 Teams 🏆**\n"
        for i, (team, pts) in enumerate(sorted_teams, start=1):
            text += f"{i}. {team} — {pts} points\n"

        await msg.edit(content=text)
    except:
        pass

# ========================= READY =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot ready as {bot.user}")

# ========================= TEAM SYSTEM =========================
@bot.tree.command(name="create-team")
async def create_team(interaction: discord.Interaction, team_name: str):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("Only TEAM-LEADER can use this.", ephemeral=True)
    uid = str(interaction.user.id)
    if uid in data["teams"]:
        return await interaction.response.send_message("You already own a team.", ephemeral=True)
    role = await get_or_create_role(interaction.guild, team_name)
    await interaction.user.add_roles(role)
    data["teams"][uid] = team_name
    data["join_requests"].setdefault(team_name, [])
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
    await interaction.response.send_message("Join request sent.", ephemeral=True)

@bot.tree.command(name="team-accept")
async def team_accept(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message("Not a team leader.", ephemeral=True)
    team_name = data["teams"][leader_id]
    if member.id not in data["join_requests"].get(team_name, []):
        return await interaction.response.send_message("No request found.", ephemeral=True)
    role = discord.utils.get(interaction.guild.roles, name=team_name)
    await member.add_roles(role)
    data["join_requests"][team_name].remove(member.id)
    save_data()
    await interaction.response.send_message("Member accepted.", ephemeral=True)

# ========================= BLACKLIST =========================
@bot.tree.command(name="blacklist")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def blacklist(interaction: discord.Interaction, member: discord.Member):
    bl_role = await get_or_create_role(interaction.guild, "blacklist")
    data["blacklist_roles"][str(member.id)] = [r.id for r in member.roles if r != interaction.guild.default_role]
    await member.edit(roles=[bl_role])
    save_data()
    await interaction.response.send_message("User blacklisted.", ephemeral=True)

@bot.tree.command(name="unblacklist")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def unblacklist(interaction: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    if uid not in data["blacklist_roles"]:
        return await interaction.response.send_message("Not blacklisted.", ephemeral=True)
    roles = [interaction.guild.get_role(rid) for rid in data["blacklist_roles"][uid] if interaction.guild.get_role(rid)]
    await member.edit(roles=roles)
    del data["blacklist_roles"][uid]
    save_data()
    await interaction.response.send_message("Blacklist removed.", ephemeral=True)

# ========================= POINTS =========================
@bot.tree.command(name="give-points")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def give_points(interaction: discord.Interaction, member: discord.Member, points: int):
    uid = str(member.id)
    data["points"][uid] = data["points"].get(uid, 0) + points
    save_data()
    await update_leaderboard()
    await update_team_leaderboard(interaction.guild)
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

@bot.tree.command(name="team-leaderboard")
async def team_leaderboard(interaction: discord.Interaction):
    msg = await interaction.channel.send("Loading team leaderboard...")
    data["team_lb_channel"] = interaction.channel.id
    data["team_lb_msg_id"] = msg.id
    save_data()
    await update_team_leaderboard(interaction.guild)
    await interaction.response.send_message("Team leaderboard created.", ephemeral=True)

# ========================= MISSION SYSTEM =========================
@bot.tree.command(name="create_mission")
async def create_mission(
    interaction: discord.Interaction,
    roblox_username: str,
    bounty_ping: discord.Role,
    bounty: str,
    note: str,
    time: str,
    ping: bool
):
    await interaction.response.defer(ephemeral=True)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [roblox_username]}
        ) as r:
            js = await r.json()
            if not js["data"]:
                return await interaction.followup.send("Roblox user not found.", ephemeral=True)
            user_id = js["data"][0]["id"]

        async with session.get(
            f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png"
        ) as r:
            img = await r.json()
            avatar = img["data"][0]["imageUrl"]

    embed = discord.Embed(title="🛡 New Mission", color=discord.Color.red())
    embed.add_field(name="Target", value=roblox_username, inline=False)
    embed.add_field(name="Bounty", value=bounty, inline=False)
    embed.add_field(name="Note", value=note, inline=False)
    embed.add_field(name="Time", value=time, inline=False)
    embed.set_image(url=avatar)

    for ch in interaction.guild.text_channels:
        if ch.name == "🛡・missions":
            try:
                if ping:
                    await ch.send(bounty_ping.mention)
                await ch.send(embed=embed)
            except:
                pass

    await interaction.followup.send("Mission sent to all missions channels.", ephemeral=True)

# ========================= RUN =========================
bot.run(TOKEN)
