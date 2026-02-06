import discord
from discord.ext import commands
import os
import json

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

DATA_FILE = "data.json"

# تحميل / حفظ البيانات
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"teams": {}, "points": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# ====== أدوات مساعدة ======
def has_role(member, role_name):
    return any(role.name == role_name for role in member.roles)

async def get_or_create_role(guild, name):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name)
    return role

# ====== أحداث ======
@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")

# ====== أوامر MOD + HEAD MOD ======
@bot.command()
@commands.has_any_role("Mod", "HEAD MOD")
async def team_leader(ctx, member: discord.Member):
    role = await get_or_create_role(ctx.guild, "TEAM-LEADER")
    await member.add_roles(role)
    await ctx.send(f"✅ {member.mention} أصبح TEAM-LEADER")

@bot.command()
@commands.has_any_role("Mod", "HEAD MOD")
async def remove_leader(ctx, member: discord.Member):
    role = discord.utils.get(ctx.guild.roles, name="TEAM-LEADER")
    if role:
        await member.remove_roles(role)
    await ctx.send(f"❌ تم إزالة TEAM-LEADER من {member.mention}")

@bot.command()
@commands.has_any_role("Mod", "HEAD MOD")
async def give_points(ctx, member: discord.Member, points: int):
    user_id = str(member.id)
    data["points"][user_id] = data["points"].get(user_id, 0) + points
    save_data(data)
    await ctx.send(f"⭐ {member.mention} حصل على {points} نقاط")

# ====== أوامر TEAM-LEADER ======
@bot.command()
async def create_team(ctx, team_name: str):
    if not has_role(ctx.author, "TEAM-LEADER"):
        return await ctx.send("❌ هذا الأمر خاص بـ TEAM-LEADER")

    user_id = str(ctx.author.id)
    if user_id in data["teams"]:
        return await ctx.send("❌ لا يمكنك إنشاء أكثر من فريق")

    role = await get_or_create_role(ctx.guild, team_name)
    await ctx.author.add_roles(role)

    data["teams"][user_id] = {
        "team": team_name,
        "members": []
    }
    save_data(data)

    await ctx.send(f"🏆 تم إنشاء فريق **{team_name}**")

@bot.command()
async def team_accept(ctx, member: discord.Member):
    user_id = str(ctx.author.id)
    if user_id not in data["teams"]:
        return await ctx.send("❌ أنت لست قائد فريق")

    team_name = data["teams"][user_id]["team"]
    role = discord.utils.get(ctx.guild.roles, name=team_name)

    await member.add_roles(role)
    data["teams"][user_id]["members"].append(member.id)
    save_data(data)

    await ctx.send(f"✅ تم قبول {member.mention} في فريق {team_name}")

@bot.command()
async def remove_team(ctx, member: discord.Member):
    user_id = str(ctx.author.id)
    if user_id not in data["teams"]:
        return await ctx.send("❌ أنت لست قائد فريق")

    team_name = data["teams"][user_id]["team"]
    role = discord.utils.get(ctx.guild.roles, name=team_name)

    await member.remove_roles(role)
    await ctx.send(f"❌ تم إزالة {member.mention} من الفريق")

# ====== أوامر عامة ======
@bot.command()
async def team_join(ctx, team_name: str):
    await ctx.send(f"📩 تم إرسال طلب الانضمام إلى فريق **{team_name}**")

# ====== Leaderboard ======
@bot.command()
@commands.has_any_role("Mod", "HEAD MOD")
async def points_leaderboard(ctx):
    leaderboard = sorted(data["points"].items(), key=lambda x: x[1], reverse=True)[:10]

    msg = "🏆 **Top 10 Players** 🏆\n"
    for i, (user_id, points) in enumerate(leaderboard, start=1):
        user = await bot.fetch_user(int(user_id))
        msg += f"{i}. {user.name} - {points} نقاط\n"

    await ctx.send(msg)

bot.run(TOKEN)
