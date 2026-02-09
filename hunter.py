import discord
from discord.ext import commands
from discord import app_commands
import os, json, asyncio, random, time

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

DATA_FILE = "data.json"

# ================= DATA =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "teams": {},                # leader_id : team_name
            "join_requests": {},        # team_name : [user_ids]
            "points": {},               # user_id : points
            "team_points": {},          # team_name : points
            "leaderboard_channel": None,
            "leaderboard_msg_id": None,
            "team_lb_channel": None,
            "team_lb_msg_id": None,
            "blacklist_roles": {},
            "invisible": {},            # user_id : {id, expires}
            "invisible_teams": {}       # team_name : {id, expires}
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)

data = load_data()

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ================= BOT =================
class MyBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(auto_refresh_invisible())
        await self.tree.sync()

bot = MyBot(command_prefix="!", intents=intents)

# ================= HELPERS =================
def has_role(member, name):
    return any(r.name == name for r in member.roles)

async def get_or_create_role(guild, name):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name)
    return role

def gen_invisible_id():
    return str(random.randint(10000000000, 99999999999))

# ================= LEADERBOARDS =================
async def update_leaderboard():
    if not data["leaderboard_channel"] or not data["leaderboard_msg_id"]:
        return
    ch = bot.get_channel(data["leaderboard_channel"])
    if not ch:
        return
    msg = await ch.fetch_message(data["leaderboard_msg_id"])

    top = sorted(data["points"].items(), key=lambda x: x[1], reverse=True)[:10]
    text = "**🏆 Top 10 Players 🏆**\n"
    for i, (uid, pts) in enumerate(top, 1):
        name = f"<@{uid}>"
        if uid in data["invisible"]:
            name = data["invisible"][uid]["id"]
        text += f"{i}. {name} — {pts} pts\n"
    await msg.edit(content=text)

async def update_team_leaderboard():
    if not data["team_lb_channel"] or not data["team_lb_msg_id"]:
        return
    ch = bot.get_channel(data["team_lb_channel"])
    if not ch:
        return
    msg = await ch.fetch_message(data["team_lb_msg_id"])

    top = sorted(data["team_points"].items(), key=lambda x: x[1], reverse=True)
    text = "**🏆 Team Leaderboard 🏆**\n"
    for i, (team, pts) in enumerate(top, 1):
        name = team
        if team in data["invisible_teams"]:
            name = data["invisible_teams"][team]["id"]
        text += f"{i}. {name} — {pts} pts\n"
    await msg.edit(content=text)

# ================= AUTO INVISIBLE =================
async def auto_refresh_invisible():
    while True:
        now = time.time()

        for uid in list(data["invisible"].keys()):
            if data["invisible"][uid]["expires"] <= now:
                new_id = gen_invisible_id()
                data["invisible"][uid]["id"] = new_id
                data["invisible"][uid]["expires"] = now + 86400
                user = await bot.fetch_user(int(uid))
                try:
                    await user.send(f"🔁 Your invisible ID refreshed: `{new_id}`")
                except:
                    pass

        for team in list(data["invisible_teams"].keys()):
            if data["invisible_teams"][team]["expires"] <= now:
                data["invisible_teams"][team]["id"] = gen_invisible_id()
                data["invisible_teams"][team]["expires"] = now + 86400

        save_data()
        await update_leaderboard()
        await update_team_leaderboard()
        await asyncio.sleep(3600)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"Bot ready as {bot.user}")

# ================= TEAMS =================
@bot.tree.command(name="create-team")
async def create_team(interaction: discord.Interaction, name: str):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("Only TEAM-LEADER.", ephemeral=True)

    uid = str(interaction.user.id)
    if uid in data["teams"]:
        return await interaction.response.send_message("You already have a team.", ephemeral=True)

    role = await get_or_create_role(interaction.guild, name)
    await interaction.user.add_roles(role)

    data["teams"][uid] = name
    data["join_requests"][name] = []
    data["team_points"][name] = 0
    save_data()
    await interaction.response.send_message("Team created.", ephemeral=True)

@bot.tree.command(name="team-join")
async def team_join(interaction: discord.Interaction, team: str):
    if team not in data["join_requests"]:
        return await interaction.response.send_message("Team not found.", ephemeral=True)

    data["join_requests"][team].append(interaction.user.id)
    save_data()
    await interaction.response.send_message("Request sent.", ephemeral=True)

@bot.tree.command(name="team-accept")
async def team_accept(interaction: discord.Interaction, member: discord.Member):
    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message("Not leader.", ephemeral=True)

    team = data["teams"][uid]
    if member.id not in data["join_requests"][team]:
        return await interaction.response.send_message("No request.", ephemeral=True)

    role = discord.utils.get(interaction.guild.roles, name=team)
    await member.add_roles(role)
    data["join_requests"][team].remove(member.id)
    save_data()
    await interaction.response.send_message("Accepted.", ephemeral=True)

# ================= CHANNELS =================
@bot.tree.command(name="team_channels")
async def team_channels(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message("No team.", ephemeral=True)

    team = data["teams"][uid]
    role = discord.utils.get(interaction.guild.roles, name=team)
    category = discord.utils.get(interaction.guild.categories, name="TEAMS")
    if not category:
        category = await interaction.guild.create_category("TEAMS")

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
        interaction.user: discord.PermissionOverwrite(send_messages=True)
    }

    for name in ["📖〢rules", "📢・announcements", "🛡️missions"]:
        if not discord.utils.get(category.channels, name=name):
            await interaction.guild.create_text_channel(name, category=category, overwrites=overwrites)

    await interaction.response.send_message("Team channels ready.", ephemeral=True)

@bot.tree.command(name="create_channel")
async def create_channel(interaction: discord.Interaction, name: str, team_write: bool):
    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message("No team.", ephemeral=True)

    team = data["teams"][uid]
    role = discord.utils.get(interaction.guild.roles, name=team)
    category = discord.utils.get(interaction.guild.categories, name="-----------------")
    if not category:
        category = await interaction.guild.create_category("-----------------")

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: discord.PermissionOverwrite(view_channel=True, send_messages=team_write),
        interaction.user: discord.PermissionOverwrite(send_messages=True)
    }

    await interaction.guild.create_text_channel(name, category=category, overwrites=overwrites)
    await interaction.response.send_message("Channel created.", ephemeral=True)

@bot.tree.command(name="delete_channel")
async def delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await channel.delete()
    await interaction.response.send_message("Deleted.", ephemeral=True)

@bot.tree.command(name="move_channel")
async def move_channel(interaction: discord.Interaction, channel: discord.TextChannel, position: int):
    await channel.edit(position=position)
    await interaction.response.send_message("Moved.", ephemeral=True)

# ================= MISSIONS =================
@bot.tree.command(name="create_mission")
async def create_mission(
    interaction: discord.Interaction,
    title: str,
    bounty: str,
    note: str,
    time_limit: str,
    ping_bounty: bool
):
    embed = discord.Embed(title=title, description=note)
    embed.add_field(name="Bounty", value=bounty)
    embed.add_field(name="Time", value=time_limit)

    for ch in interaction.guild.text_channels:
        if "missions" in ch.name:
            if ping_bounty:
                await ch.send(f"@here", embed=embed)
            else:
                await ch.send(embed=embed)

    await interaction.response.send_message("Mission sent.", ephemeral=True)

@bot.tree.command(name="create-team-mission")
async def create_team_mission(interaction: discord.Interaction, title: str, bounty: str, note: str, time_limit: str):
    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message("No team.", ephemeral=True)

    embed = discord.Embed(title=title, description=note)
    embed.add_field(name="Bounty", value=bounty)
    embed.add_field(name="Time", value=time_limit)

    for ch in interaction.guild.text_channels:
        if "missions" in ch.name:
            await ch.send(embed=embed)

    await interaction.response.send_message("Team mission sent.", ephemeral=True)

# ================= POINTS =================
@bot.tree.command(name="give-points")
async def give_points(interaction: discord.Interaction, member: discord.Member, pts: int):
    uid = str(member.id)
    data["points"][uid] = data["points"].get(uid, 0) + pts

    for leader, team in data["teams"].items():
        role = discord.utils.get(interaction.guild.roles, name=team)
        if role in member.roles:
            data["team_points"][team] += pts

    save_data()
    await update_leaderboard()
    await update_team_leaderboard()
    await interaction.response.send_message("Points updated.", ephemeral=True)

@bot.tree.command(name="show-my-points")
async def show_my_points(interaction: discord.Interaction):
    pts = data["points"].get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"You have {pts} points.", ephemeral=True)

@bot.tree.command(name="show-my-team-points")
async def show_my_team_points(interaction: discord.Interaction):
    for leader, team in data["teams"].items():
        role = discord.utils.get(interaction.guild.roles, name=team)
        if role in interaction.user.roles:
            await interaction.response.send_message(f"Team **{team}** has {data['team_points'][team]} points.", ephemeral=True)
            return
    await interaction.response.send_message("No team.", ephemeral=True)

# ================= INVISIBLE =================
@bot.tree.command(name="invisible")
async def invisible(interaction: discord.Interaction, days: int):
    uid = str(interaction.user.id)
    iid = gen_invisible_id()
    data["invisible"][uid] = {
        "id": iid,
        "expires": time.time() + days * 86400
    }
    save_data()
    await interaction.user.send(f"🔒 Invisible ID: `{iid}`")
    await interaction.response.send_message("Invisible enabled.", ephemeral=True)

@bot.tree.command(name="uninvisible")
async def uninvisible(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    data["invisible"].pop(uid, None)
    save_data()
    await interaction.response.send_message("Invisible disabled.", ephemeral=True)

# ================= LEADERBOARD SHOW =================
@bot.tree.command(name="show-the-leaderboard")
async def show_lb(interaction: discord.Interaction, leaderboard_type: str):
    if leaderboard_type == "team":
        await update_team_leaderboard()
        await interaction.response.send_message("Team leaderboard updated.", ephemeral=True)
    else:
        await update_leaderboard()
        await interaction.response.send_message("Player leaderboard updated.", ephemeral=True)

# ================= RUN =================
bot.run(TOKEN)
