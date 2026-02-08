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
            "teams": {},           # leader_id : team_name
            "join_requests": {},   # team_name : [user_ids]
            "points": {},
            "leaderboard_channel": None,
            "leaderboard_msg_id": None
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

# ================= READY =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot ready as {bot.user}")

# ================= TEAM CREATE =================
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

    data["teams"][uid] = team_name
    data["join_requests"].setdefault(team_name, [])
    save_data()

    await interaction.response.send_message(
        "Team created successfully.", ephemeral=True
    )

# ================= TEAM JOIN =================
@bot.tree.command(name="team-join")
async def team_join(interaction: discord.Interaction, team_name: str):
    if team_name not in data["join_requests"]:
        return await interaction.response.send_message(
            "This team does not exist.", ephemeral=True
        )

    if interaction.user.id in data["join_requests"][team_name]:
        return await interaction.response.send_message(
            "You already sent a join request.", ephemeral=True
        )

    data["join_requests"][team_name].append(interaction.user.id)
    save_data()

    # notify leader
    for leader_id, tname in data["teams"].items():
        if tname.lower() == team_name.lower():
            leader = interaction.guild.get_member(int(leader_id))
            if leader:
                try:
                    await leader.send(
                        f"📩 {interaction.user.name} requested to join your team **{team_name}**"
                    )
                except:
                    pass

    await interaction.response.send_message(
        "Join request sent successfully.", ephemeral=True
    )

# ================= TEAM ACCEPT =================
@bot.tree.command(name="team-accept")
async def team_accept(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)

    if leader_id not in data["teams"]:
        return await interaction.response.send_message(
            "You are not a team leader.", ephemeral=True
        )

    team_name = data["teams"][leader_id]

    if team_name not in data["join_requests"]:
        return await interaction.response.send_message(
            "No join requests for your team.", ephemeral=True
        )

    if member.id not in data["join_requests"][team_name]:
        return await interaction.response.send_message(
            "This user did not send a join request.", ephemeral=True
        )

    role = discord.utils.get(interaction.guild.roles, name=team_name)
    if not role:
        return await interaction.response.send_message(
            "Team role not found.", ephemeral=True
        )

    await member.add_roles(role)

    data["join_requests"][team_name].remove(member.id)
    save_data()

    await interaction.response.send_message(
        f"{member.mention} has been accepted into the team.", ephemeral=True
    )

# ================= TEAM REMOVE =================
@bot.tree.command(name="remove-team")
async def remove_team(interaction: discord.Interaction, member: discord.Member):
    leader_id = str(interaction.user.id)
    if leader_id not in data["teams"]:
        return await interaction.response.send_message(
            "You are not a team leader.", ephemeral=True
        )

    team_name = data["teams"][leader_id]
    role = discord.utils.get(interaction.guild.roles, name=team_name)

    if role in member.roles:
        await member.remove_roles(role)
        await interaction.response.send_message(
            "Member removed from team.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "Member is not in your team.", ephemeral=True
        )

# ================= RUN =================
bot.run(TOKEN)
