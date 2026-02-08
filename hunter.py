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

# ================== Data ==================
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

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# ================== Helpers ==================
def has_role(member, role_name):
    return any(role.name == role_name for role in member.roles)

async def get_or_create_role(guild, name):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name)
    return role

async def update_leaderboard():
    if not data.get("leaderboard_channel") or not data.get("leaderboard_msg_id"):
        return
    channel = bot.get_channel(data["leaderboard_channel"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(data["leaderboard_msg_id"])
        leaderboard = sorted(data["points"].items(), key=lambda x: x[1], reverse=True)[:10]
        content = "**🏆 Top 10 Players 🏆**\n"
        for i, (uid, pts) in enumerate(leaderboard, start=1):
            try:
                user = await bot.fetch_user(int(uid))
                content += f"{i}. {user.name} - {pts} نقاط\n"
            except:
                content += f"{i}. Unknown - {pts} نقاط\n"
        await msg.edit(content=content)
    except:
        pass

# ================== Events ==================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot Ready | {bot.user}")

# ================== MOD + HEAD MOD ==================
@bot.tree.command(name="team-leader")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def team_leader(interaction: discord.Interaction, member: discord.Member):
    role = await get_or_create_role(interaction.guild, "TEAM-LEADER")
    await member.add_roles(role)
    await interaction.response.send_message("✅ تم إعطاء الرول", ephemeral=True)

@bot.tree.command(name="remove-leader")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def remove_leader(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.guild.roles, name="TEAM-LEADER")
    if role:
        await member.remove_roles(role)
    await interaction.response.send_message("❌ تم إزالة الرول", ephemeral=True)

@bot.tree.command(name="give-points")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def give_points(interaction: discord.Interaction, member: discord.Member, points: int):
    uid = str(member.id)
    data["points"][uid] = data["points"].get(uid, 0) + points
    save_data(data)
    await interaction.response.send_message("⭐ تم تعديل النقاط", ephemeral=True)
    await update_leaderboard()

@bot.tree.command(name="points-leaderboard")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def points_leaderboard(interaction: discord.Interaction):
    leaderboard = sorted(data["points"].items(), key=lambda x: x[1], reverse=True)[:10]
    content = "**🏆 Top 10 Players 🏆**\n"
    for i, (uid, pts) in enumerate(leaderboard, start=1):
        try:
            user = await bot.fetch_user(int(uid))
            content += f"{i}. {user.name} - {pts} نقاط\n"
        except:
            content += f"{i}. Unknown - {pts} نقاط\n"
    msg = await interaction.channel.send(content)
    data["leaderboard_channel"] = interaction.channel.id
    data["leaderboard_msg_id"] = msg.id
    save_data(data)
    await interaction.response.send_message("✅ تم إنشاء القائمة", ephemeral=True)

# ================== BLACKLIST ==================
@bot.tree.command(name="blacklist")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def blacklist(interaction: discord.Interaction, member: discord.Member):
    guild = interaction.guild
    bl_role = await get_or_create_role(guild, "blacklist")

    saved_roles = [role.id for role in member.roles if role != guild.default_role]
    data["blacklist_roles"][str(member.id)] = saved_roles

    for role in member.roles:
        if role != guild.default_role:
            await member.remove_roles(role)

    await member.add_roles(bl_role)
    save_data(data)

    await interaction.response.send_message("⛔ تم بلاك ليست العضو", ephemeral=True)

@bot.tree.command(name="unblacklist")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def unblacklist(interaction: discord.Interaction, member: discord.Member):
    guild = interaction.guild
    bl_role = discord.utils.get(guild.roles, name="blacklist")
    if bl_role:
        await member.remove_roles(bl_role)

    saved = data["blacklist_roles"].get(str(member.id), [])
    for role_id in saved:
        role = guild.get_role(role_id)
        if role:
            await member.add_roles(role)

    data["blacklist_roles"].pop(str(member.id), None)
    save_data(data)

    await interaction.response.send_message("✅ تم فك البلاك ليست وإرجاع الرولات", ephemeral=True)

# ================== TEAM SYSTEM ==================
@bot.tree.command(name="create-team")
async def create_team(interaction: discord.Interaction, team_name: str):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message("❌ ليس لديك صلاحية", ephemeral=True)
    uid = str(interaction.user.id)
    if uid in data["teams"]:
        return await interaction.response.send_message("❌ لديك فريق بالفعل", ephemeral=True)
    role = await get_or_create_role(interaction.guild, team_name)
    await interaction.user.add_roles(role)
    data["teams"][uid] = {"team": team_name, "members": []}
    save_data(data)
    await interaction.response.send_message("✅ تم إنشاء الفريق", ephemeral=True)

@bot.tree.command(name="team-join")
async def team_join(interaction: discord.Interaction, team_name: str):
    data["join_requests"].setdefault(team_name, [])
    uid = str(interaction.user.id)
    if uid in data["join_requests"][team_name]:
        return await interaction.response.send_message("❌ لديك طلب مسبق", ephemeral=True)
    data["join_requests"][team_name].append(uid)
    save_data(data)
    await interaction.response.send_message("📩 تم إرسال الطلب", ephemeral=True)

@bot.tree.command(name="team-accept")
async def team_accept(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message("❌ لست قائد فريق", ephemeral=True)
    team = data["teams"][leader_id]["team"]
    if str(member.id) not in data["join_requests"].get(team, []):
        return await interaction.response.send_message("❌ لم يطلب الانضمام", ephemeral=True)
    role = discord.utils.get(interaction.guild.roles, name=team)
    await member.add_roles(role)
    data["join_requests"][team].remove(str(member.id))
    save_data(data)
    await interaction.response.send_message("✅ تم قبول العضو", ephemeral=True)

@bot.tree.command(name="remove-team")
async def remove_team(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message("❌ لست قائد فريق", ephemeral=True)
    team = data["teams"][leader_id]["team"]
    role = discord.utils.get(interaction.guild.roles, name=team)
    if role:
        await member.remove_roles(role)
    await interaction.response.send_message("❌ تم إزالة العضو", ephemeral=True)

# ================== RUN ==================
bot.run(TOKEN)
