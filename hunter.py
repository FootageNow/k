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
            "teams": {},               # leader_id : team_name
            "join_requests": {},       # team_name : [user_ids]
            "points": {},              # user_id : points
            "leaderboard_channel": None,
            "leaderboard_msg_id": None,
            "blacklist_roles": {}      # user_id : [role_ids]
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

# ================= TEAM COMMANDS =================
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
    await interaction.response.send_message("Team created successfully.", ephemeral=True)

@bot.tree.command(name="team-join")
async def team_join(interaction: discord.Interaction, team_name: str):
    if team_name not in data["join_requests"]:
        return await interaction.response.send_message("This team does not exist.", ephemeral=True)

    if interaction.user.id in data["join_requests"][team_name]:
        return await interaction.response.send_message("You already sent a join request.", ephemeral=True)

    data["join_requests"][team_name].append(interaction.user.id)
    save_data()

    # notify leader
    for leader_id, tname in data["teams"].items():
        if tname.lower() == team_name.lower():
            leader = interaction.guild.get_member(int(leader_id))
            if leader:
                try:
                    await leader.send(f"📩 {interaction.user.name} requested to join your team **{team_name}**")
                except:
                    pass

    await interaction.response.send_message("Join request sent successfully.", ephemeral=True)

@bot.tree.command(name="team-accept")
async def team_accept(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message("You are not a team leader.", ephemeral=True)

    team_name = data["teams"][leader_id]

    if member.id not in data["join_requests"].get(team_name, []):
        return await interaction.response.send_message("This user did not send a join request.", ephemeral=True)

    role = discord.utils.get(interaction.guild.roles, name=team_name)
    await member.add_roles(role)
    data["join_requests"][team_name].remove(member.id)
    save_data()
    await interaction.response.send_message(f"{member.mention} has been accepted into the team.", ephemeral=True)

@bot.tree.command(name="remove-team")
async def remove_team(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message("You are not a team leader.", ephemeral=True)

    team_name = data["teams"][leader_id]
    role = discord.utils.get(interaction.guild.roles, name=team_name)
    if role in member.roles:
        await member.remove_roles(role)
        await interaction.response.send_message("Member removed from team.", ephemeral=True)
    else:
        await interaction.response.send_message("Member is not in your team.", ephemeral=True)

# ================= TEAM CHANNELS =================
@bot.tree.command(name="team_channels")
async def team_channels(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    team_name = data["teams"].get(uid)
    if not team_name:
        return await interaction.response.send_message("You do not own a team.", ephemeral=True)

    guild = interaction.guild
    team_role = discord.utils.get(guild.roles, name=team_name)
    category = discord.utils.get(guild.categories, name="TEAMS")
    if not category:
        category = await guild.create_category("TEAMS")

    existing = [c.name for c in category.channels]
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                  team_role: discord.PermissionOverwrite(view_channel=True, send_messages=False)}

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
    uid = str(interaction.user.id)
    team_name = data["teams"].get(uid)
    guild = interaction.guild
    team_role = discord.utils.get(guild.roles, name=team_name)

    category = discord.utils.get(guild.categories, name="-----------------")
    if not category:
        category = await guild.create_category("-----------------")

    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                  team_role: discord.PermissionOverwrite(view_channel=True, send_messages=team_can_write)}

    ch = await guild.create_text_channel(name, category=category, overwrites=overwrites)
    await ch.set_permissions(interaction.user, send_messages=True)
    await interaction.response.send_message("Channel created.", ephemeral=True)

@bot.tree.command(name="delete_channel")
async def delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await channel.delete()
    await interaction.response.send_message("Channel deleted.", ephemeral=True)

@bot.tree.command(name="move_channel")
async def move_channel(interaction: discord.Interaction, channel: discord.TextChannel, position: int):
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

# ================= BLACKLIST =================
@bot.tree.command(name="blacklist")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def blacklist(interaction: discord.Interaction, member: discord.Member):
    bl_role = await get_or_create_role(interaction.guild, "blacklist")
    data["blacklist_roles"][str(member.id)] = [r.id for r in member.roles if r != interaction.guild.default_role]
    await member.edit(roles=[bl_role])
    save_data()
    await interaction.response.send_message(f"{member.mention} has been blacklisted.", ephemeral=True)

@bot.tree.command(name="unblacklist")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def unblacklist(interaction: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    if uid not in data["blacklist_roles"]:
        return await interaction.response.send_message("This user is not blacklisted.", ephemeral=True)

    roles = [interaction.guild.get_role(rid) for rid in data["blacklist_roles"][uid] if interaction.guild.get_role(rid)]
    await member.edit(roles=roles)
    del data["blacklist_roles"][uid]
    save_data()
    await interaction.response.send_message(f"{member.mention} has been unblacklisted.", ephemeral=True)

# ================= RUN =================
bot.run(TOKEN)
