# ========================= IMPORTS =========================
import discord
from discord.ext import commands
from discord import app_commands
import os, json, aiohttp, asyncio, random, time

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
            "teams": {},                 # leader_id : team_name
            "join_requests": {},         # team_name : [user_ids]
            "points": {},                # user_id : points
            "leaderboard_channel": None,
            "leaderboard_msg_id": None,
            "team_lb_channel": None,
            "team_lb_msg_id": None,
            "blacklist_roles": {},       # user_id : [role_ids]
            "invisible_users": {},       # user_id : {id, expires}
            "invisible_teams": {}        # team_name : {id, expires}
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

def generate_id():
    return str(random.randint(10**10, 10**11))

def now():
    return int(time.time())

# ========================= LEADERBOARDS =========================
async def update_player_leaderboard():
    if not data["leaderboard_channel"] or not data["leaderboard_msg_id"]:
        return
    channel = bot.get_channel(data["leaderboard_channel"])
    if not channel:
        return

    msg = await channel.fetch_message(data["leaderboard_msg_id"])
    top = sorted(data["points"].items(), key=lambda x: x[1], reverse=True)[:10]

    text = "**🏆 Top 10 Players 🏆**\n"
    for i, (uid, pts) in enumerate(top, start=1):
        if uid in data["invisible_users"]:
            name = data["invisible_users"][uid]["id"]
        else:
            user = await bot.fetch_user(int(uid))
            name = user.name
        text += f"{i}. {name} — {pts} points\n"

    await msg.edit(content=text)

async def update_team_leaderboard(guild):
    if not data["team_lb_channel"] or not data["team_lb_msg_id"]:
        return
    channel = guild.get_channel(data["team_lb_channel"])
    if not channel:
        return

    msg = await channel.fetch_message(data["team_lb_msg_id"])
    teams_points = {}

    for leader_id, team in data["teams"].items():
        role = discord.utils.get(guild.roles, name=team)
        if not role:
            continue
        total = sum(data["points"].get(str(m.id), 0) for m in role.members)
        display = data["invisible_teams"].get(team, {}).get("id", team)
        teams_points[display] = total

    sorted_teams = sorted(teams_points.items(), key=lambda x: x[1], reverse=True)[:10]

    text = "**🏆 Top 10 Teams 🏆**\n"
    for i, (team, pts) in enumerate(sorted_teams, start=1):
        text += f"{i}. {team} — {pts} points\n"

    await msg.edit(content=text)

# ========================= READY =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    bot.loop.create_task(invisible_refresher())
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
    data["join_requests"][team_name] = []
    save_data()

    await interaction.response.send_message("Team created successfully.", ephemeral=True)

@bot.tree.command(name="team-join")
async def team_join(interaction: discord.Interaction, team_name: str):
    if team_name not in data["join_requests"]:
        return await interaction.response.send_message("Team not found.", ephemeral=True)

    if interaction.user.id in data["join_requests"][team_name]:
        return await interaction.response.send_message("Already requested.", ephemeral=True)

    data["join_requests"][team_name].append(interaction.user.id)
    save_data()

    # ---------------- NOTIFY TEAM LEADER ----------------
    for leader_id, tname in data["teams"].items():
        if tname.lower() == team_name.lower():
            leader = interaction.guild.get_member(int(leader_id))
            if leader:
                try:
                    await leader.send(f"📩 **{interaction.user.name}** requested to join your team **{team_name}**")
                except:
                    pass

    await interaction.response.send_message("Join request sent.", ephemeral=True)


@bot.tree.command(name="team-accept")
async def team_accept(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message("Not a team leader.", ephemeral=True)

    team = data["teams"][leader_id]
    if member.id not in data["join_requests"].get(team, []):
        return await interaction.response.send_message("No join request.", ephemeral=True)

    role = discord.utils.get(interaction.guild.roles, name=team)
    await member.add_roles(role)
    data["join_requests"][team].remove(member.id)
    save_data()

    await interaction.response.send_message("Member accepted.", ephemeral=True)

# ========================= POINTS =========================
@bot.tree.command(name="give-points")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def give_points(interaction: discord.Interaction, member: discord.Member, points: int):
    uid = str(member.id)
    data["points"][uid] = data["points"].get(uid, 0) + points
    save_data()

    await update_player_leaderboard()
    await update_team_leaderboard(interaction.guild)

    await interaction.response.send_message("Points updated.", ephemeral=True)

@bot.tree.command(name="points-leaderboard")
async def points_leaderboard(interaction: discord.Interaction):
    msg = await interaction.channel.send("Loading leaderboard...")
    data["leaderboard_channel"] = interaction.channel.id
    data["leaderboard_msg_id"] = msg.id
    save_data()
    await update_player_leaderboard()

@bot.tree.command(name="team-leaderboard")
async def team_leaderboard(interaction: discord.Interaction):
    msg = await interaction.channel.send("Loading team leaderboard...")
    data["team_lb_channel"] = interaction.channel.id
    data["team_lb_msg_id"] = msg.id
    save_data()
    await update_team_leaderboard(interaction.guild)

# ========================= SHOW MY STATS =========================
@bot.tree.command(name="show-my-points")
async def show_my_points(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    pts = data["points"].get(uid, 0)
    sorted_players = sorted(data["points"].items(), key=lambda x: x[1], reverse=True)
    rank = next((i+1 for i, (pid, _) in enumerate(sorted_players) if pid == uid), "N/A")
    await interaction.response.send_message(f"Your Points: {pts}\nRank: #{rank}", ephemeral=True)

@bot.tree.command(name="show-my-team-points")
async def show_my_team_points(interaction: discord.Interaction):
    member = interaction.user
    team_role = next((r for r in member.roles if r.name in data["teams"].values()), None)
    if not team_role:
        return await interaction.response.send_message("You are not in a team.", ephemeral=True)

    total = sum(data["points"].get(str(m.id), 0) for m in team_role.members)
    await interaction.response.send_message(f"Team **{team_role.name}** Points: {total}", ephemeral=True)

# ========================= MISSIONS (GLOBAL) =========================
@bot.tree.command(name="create_mission")
async def create_mission(
    interaction: discord.Interaction,
    roblox_username: str,
    bounty: str,
    note: str,
    time_left: str,
    ping_role: discord.Role | None = None
):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [roblox_username]}
        ) as r:
            js = await r.json()
            if not js["data"]:
                return await interaction.response.send_message("Roblox user not found.", ephemeral=True)
            rid = js["data"][0]["id"]

        async with session.get(
            f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={rid}&size=420x420&format=Png"
        ) as r:
            img = await r.json()
            avatar = img["data"][0]["imageUrl"]

    embed = discord.Embed(title="🛡 New Mission")
    embed.add_field(name="Target", value=roblox_username, inline=False)
    embed.add_field(name="Bounty", value=bounty, inline=False)
    embed.add_field(name="Note", value=note, inline=False)
    embed.add_field(name="Time", value=time_left, inline=False)
    embed.set_image(url=avatar)

    for ch in interaction.guild.text_channels:
        if ch.name.startswith("🛡"):
            if ping_role:
                await ch.send(ping_role.mention)
            await ch.send(embed=embed)

    await interaction.response.send_message("Mission sent.", ephemeral=True)

# ========================= INVISIBLE =========================
@bot.tree.command(name="invisible")
async def invisible(interaction: discord.Interaction, days: int):
    uid = str(interaction.user.id)
    fake = generate_id()
    data["invisible_users"][uid] = {
        "id": fake,
        "expires": now() + days * 86400
    }
    save_data()
    await interaction.user.send(f"Your Invisible ID: `{fake}`")
    await interaction.response.send_message("Invisible enabled.", ephemeral=True)

@bot.tree.command(name="uninvisible")
async def uninvisible(interaction: discord.Interaction):
    data["invisible_users"].pop(str(interaction.user.id), None)
    save_data()
    await interaction.response.send_message("Invisible disabled.", ephemeral=True)

async def invisible_refresher():
    await bot.wait_until_ready()
    while not bot.is_closed():
        t = now()
        for uid, info in list(data["invisible_users"].items()):
            if t >= info["expires"]:
                new_id = generate_id()
                data["invisible_users"][uid]["id"] = new_id
                data["invisible_users"][uid]["expires"] = t + 86400
                user = bot.get_user(int(uid))
                if user:
                    await user.send(f"🔄 Invisible ID refreshed: `{new_id}`")
        save_data()
        await asyncio.sleep(60)

# ========================= RUN =========================
bot.run(TOKEN)
