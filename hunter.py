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
        return {"teams": {}, "points": {}, "join_requests": {}}
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

# ================== Events ==================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot Ready | {bot.user}")

# ================== MOD + HEAD MOD ==================
@bot.tree.command(name="team-leader", description="إعطاء رول TEAM-LEADER")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def team_leader(interaction: discord.Interaction, member: discord.Member):
    role = await get_or_create_role(interaction.guild, "TEAM-LEADER")
    await member.add_roles(role)
    await interaction.response.send_message(
        f"✅ {member.mention} أصبح TEAM-LEADER", ephemeral=True
    )

@bot.tree.command(name="remove-leader", description="إزالة رول TEAM-LEADER")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def remove_leader(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.guild.roles, name="TEAM-LEADER")
    if role:
        await member.remove_roles(role)
    await interaction.response.send_message(
        f"❌ تم إزالة TEAM-LEADER من {member.mention}", ephemeral=True
    )

@bot.tree.command(name="give-points", description="إعطاء نقاط للاعب")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def give_points(interaction: discord.Interaction, member: discord.Member, points: int):
    uid = str(member.id)
    data["points"][uid] = data["points"].get(uid, 0) + points
    save_data(data)
    await interaction.response.send_message(
        f"⭐ {member.mention} حصل على {points} نقاط", ephemeral=True
    )

@bot.tree.command(name="points-leaderboard", description="أفضل 10 لاعبين نقاط")
@app_commands.checks.has_any_role("Mod", "HEAD MOD")
async def points_leaderboard(interaction: discord.Interaction):
    leaderboard = sorted(
        data["points"].items(), key=lambda x: x[1], reverse=True
    )[:10]

    msg = "🏆 **Top 10 Players** 🏆\n"
    for i, (uid, pts) in enumerate(leaderboard, start=1):
        user = await bot.fetch_user(int(uid))
        msg += f"{i}. {user.name} - {pts} نقاط\n"

    await interaction.response.send_message(msg)

# ================== TEAM LEADER ==================
@bot.tree.command(name="create-team", description="إنشاء فريق (مرة واحدة)")
async def create_team(interaction: discord.Interaction, team_name: str):
    if not has_role(interaction.user, "TEAM-LEADER"):
        return await interaction.response.send_message(
            "❌ هذا الأمر خاص بـ TEAM-LEADER", ephemeral=True
        )

    uid = str(interaction.user.id)
    if uid in data["teams"]:
        return await interaction.response.send_message(
            "❌ أنشأت فريق مسبقًا", ephemeral=True
        )

    role = await get_or_create_role(interaction.guild, team_name)
    await interaction.user.add_roles(role)

    data["teams"][uid] = {
        "team": team_name,
        "members": []
    }
    save_data(data)

    await interaction.response.send_message(
        f"🏆 تم إنشاء فريق **{team_name}**", ephemeral=True
    )

@bot.tree.command(name="team-accept", description="قبول لاعب في الفريق")
async def team_accept(interaction: discord.Interaction, member: discord.Member):
    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message(
            "❌ أنت لست قائد فريق", ephemeral=True
        )

    team_name = data["teams"][uid]["team"]

    # التحقق من وجود طلب الانضمام
    if team_name not in data["join_requests"]:
        return await interaction.response.send_message(
            "❌ لا يوجد طلبات انضمام لهذا الفريق", ephemeral=True
        )
    if member.id not in data["join_requests"][team_name]:
        return await interaction.response.send_message(
            "❌ هذا العضو لم يرسل طلب الانضمام", ephemeral=True
        )

    # إضافة الرول للعضو
    role = discord.utils.get(interaction.guild.roles, name=team_name)
    await member.add_roles(role)

    # إضافة العضو لقائمة أعضاء الفريق
    data["teams"][uid]["members"].append(member.id)

    # إزالة العضو من قائمة الانتظار
    data["join_requests"][team_name].remove(member.id)
    save_data(data)

    await interaction.response.send_message(
        f"✅ تم قبول {member.mention} في فريق {team_name}", ephemeral=True
    )

@bot.tree.command(name="remove-team", description="إزالة لاعب من الفريق")
async def remove_team(interaction: discord.Interaction, member: discord.Member):
    uid = str(interaction.user.id)
    if uid not in data["teams"]:
        return await interaction.response.send_message(
            "❌ أنت لست قائد فريق", ephemeral=True
        )

    team_name = data["teams"][uid]["team"]
    role = discord.utils.get(interaction.guild.roles, name=team_name)
    await member.remove_roles(role)

    await interaction.response.send_message(
        f"❌ تم إزالة {member.mention} من الفريق", ephemeral=True
    )

# ================== ALL USERS ==================
@bot.tree.command(name="team-join", description="طلب الانضمام لفريق")
async def team_join(interaction: discord.Interaction, team_name: str):
    if "join_requests" not in data:
        data["join_requests"] = {}
    if team_name not in data["join_requests"]:
        data["join_requests"][team_name] = []

    if interaction.user.id in data["join_requests"][team_name]:
        return await interaction.response.send_message(
            "❌ لقد قدمت طلب لهذا الفريق مسبقًا", ephemeral=True
        )

    # إضافة العضو لطلبات الانضمام
    data["join_requests"][team_name].append(interaction.user.id)
    save_data(data)

    # العثور على قائد الفريق
    leader_id = None
    for uid, team_info in data["teams"].items():
        if team_info["team"].lower() == team_name.lower():
            leader_id = int(uid)
            break

    # إرسال إشعار للقائد
    if leader_id:
        leader = interaction.guild.get_member(leader_id)
        if leader:
            try:
                await leader.send(
                    f"📩 العضو {interaction.user.mention} طلب الانضمام إلى فريقك: **{team_name}**"
                )
            except:
                # إذا لم يستطع البوت إرسال DM
                await interaction.guild.text_channels[0].send(
                    f"📩 {interaction.user.mention} طلب الانضمام إلى فريق **{team_name}**. القائد {leader.mention}"
                )

    await interaction.response.send_message(
        f"✅ تم إرسال طلب الانضمام إلى فريق **{team_name}**", ephemeral=True
    )

# ================== RUN ==================
bot.run(TOKEN)
