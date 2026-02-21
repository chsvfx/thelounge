import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
import psutil
import random
import traceback

# ===================== CONFIG =====================
GUILD_ID = 1351310078849847358
MEMBER_ROLE_ID = 1386784222781505619

ALLOWED_USER_IDS = [771432636563324929, 1329386427460358188]

SYSTEM_LOG_CHANNEL_ID = 1462412675295481971
VERIFY_LOG_CHANNEL_ID = 1462412645150752890
JOIN_LOG_CHANNEL_ID = 1462412615195164908
LEAVE_LOG_CHANNEL_ID = 1462412568747573422
BOT_STATUS_CHANNEL_ID = 1463660427413033093
VOICE_LOG_CHANNEL_ID = 1463842358448623822
MESSAGE_LOG_CHANNEL_ID = 1462412675295481971
TICKET_CATEGORY_ID = 1462421944170446869

TRACKED_VOICE_CHANNELS = [
    1461424134906056846,
    1462421172519178313,
    1439274257585799198,
    1457046754661765245,
    1432491181006127268
]

PROTECTED_IDS = [1351310078887858299, 1386779868532047982]

# ===================== INTENTS =====================
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===================== MEMORY =====================
START_TIME = datetime.now(timezone.utc)
status_message: discord.Message | None = None
invite_tracker = {}

# ===================== HELPERS =====================
def get_channel_safe(cid: int) -> discord.TextChannel | None:
    return bot.get_channel(cid)

def format_account_age(created_at: datetime):
    delta_days = (datetime.now(timezone.utc) - created_at).days
    years = delta_days // 365
    months = (delta_days % 365) // 30
    days = (delta_days % 365) % 30
    return f"{years}y {months}m {days}d"

def format_uptime():
    delta = datetime.now(timezone.utc) - START_TIME
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"

async def send_embed(channel_id: int, title: str, color, fields=None, thumbnail=None, description=None):
    channel = get_channel_safe(channel_id)
    if not channel:
        return
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    if description:
        embed.description = description
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    embed.set_footer(text=f"{bot.user.name} • {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    await channel.send(embed=embed)

async def build_embed(title, description, color, user=None):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    if user:
        embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"{bot.user.name} • Discord Automation")
    return embed

# ===================== VIEWS =====================
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.success, custom_id="persistent_verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if not role:
            await interaction.response.send_message(embed=await build_embed("❌ Error", "Member role not found.", discord.Color.red()), ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message(embed=await build_embed("ℹ️ Already Verified", "You are already verified!", discord.Color.orange()), ephemeral=True)
            return
        await interaction.user.add_roles(role)
        await interaction.response.send_message(embed=await build_embed("🎉 Verified!", "You have been verified and given access to the server!", discord.Color.green(), interaction.user), ephemeral=True)
        await send_embed(
            VERIFY_LOG_CHANNEL_ID,
            "✅ Member Verified",
            discord.Color.green(),
            fields=[
                ("👤 User", f"{interaction.user.mention}\n`{interaction.user.id}`", False),
                ("📅 Account Age", format_account_age(interaction.user.created_at), False),
                ("🏷️ Role", role.mention, False),
                ("🕒 Time", f"<t:{int(datetime.now().timestamp())}:F>", False)
            ],
            thumbnail=interaction.user.display_avatar.url
        )

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎟️ Open Support Ticket", style=discord.ButtonStyle.primary, custom_id="persistent_ticket_button")
    async def ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        existing = discord.utils.get(guild.channels, name=f"ticket-{interaction.user.name}".lower())
        if existing:
            await interaction.response.send_message(embed=await build_embed("⚠️ Ticket Exists", f"You already have an open ticket: {existing.mention}", discord.Color.orange()), ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}".lower(),
            category=category,
            overwrites=overwrites
        )
        await interaction.response.send_message(embed=await build_embed("🎟️ Ticket Created", f"Your ticket has been created: {ticket_channel.mention}", discord.Color.green()), ephemeral=True)
        await ticket_channel.send(embed=await build_embed("🆘 Support Ticket", f"Hello {interaction.user.mention}, please describe your issue. Staff will respond shortly.", discord.Color.blue(), interaction.user))

# ===================== COMMANDS =====================
@bot.tree.command(name="verify", description="Verify yourself to access server channels.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    embed = await build_embed("🎉 Server Verification", "Click the button below to verify yourself and gain full access.", discord.Color.green())
    await interaction.response.send_message(embed=embed, view=VerifyView(), ephemeral=True)

@bot.tree.command(name="ticket", description="Open a support ticket.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction):
    embed = await build_embed("🎫 Support Center", "Click below to open a support ticket.", discord.Color.orange())
    await interaction.response.send_message(embed=embed, view=TicketView(), ephemeral=True)

@bot.tree.command(name="8ball")
async def eightball(interaction: discord.Interaction, question: str):
    responses = ["Yes", "No", "Try again later", "Absolutely", "Unlikely", "Outlook good", "Cannot predict"]
    response = random.choice(responses)
    embed = await build_embed("🎱 Magic 8 Ball", f"**Question:** {question}\n\n**Answer:** {response}", discord.Color.purple())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dice")
async def dice(interaction: discord.Interaction, sides: int = 6):
    if sides < 2 or sides > 100:
        await interaction.response.send_message(embed=await build_embed("❌ Invalid Dice", "Must be between 2 and 100 sides.", discord.Color.red()), ephemeral=True)
        return
    roll = random.randint(1, sides)
    embed = await build_embed("🎲 Dice Roll", f"You rolled a **d{sides}** and got **{roll}**!", discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    embed = await build_embed("🪙 Coin Flip", f"Result: **{result}**", discord.Color.light_gray())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rps")
async def rps(interaction: discord.Interaction, choice: str):
    choice = choice.lower()
    options = ["rock", "paper", "scissors"]
    if choice not in options:
        await interaction.response.send_message(embed=await build_embed("❌ Invalid Choice", "Choose rock, paper, or scissors.", discord.Color.red()), ephemeral=True)
        return
    bot_choice = random.choice(options)
    if choice == bot_choice:
        result = "🤝 It's a tie!"
    elif (choice, bot_choice) in [("rock", "scissors"), ("scissors", "paper"), ("paper", "rock")]:
        result = "🎉 You win!"
    else:
        result = "😈 Bot wins!"
    embed = await build_embed("🪨 Rock, Paper, Scissors", f"You chose **{choice}**\nBot chose **{bot_choice}**\n\n{result}", discord.Color.blurple())
    await interaction.response.send_message(embed=embed)

# ===================== EVENTS =====================
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    bot.add_view(TicketView())
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    guild = bot.get_guild(GUILD_ID)
    if guild:
        for invite in await guild.invites():
            invite_tracker[invite.code] = invite.uses
    update_status.start()
    print(f"🟢 Logged in as {bot.user}")

@tasks.loop(seconds=10)
async def update_status():
    global status_message
    channel = get_channel_safe(BOT_STATUS_CHANNEL_ID)
    if not channel:
        return
    guild = bot.get_guild(GUILD_ID)
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    uptime = format_uptime()
    total = len(guild.members)
    bots = len([m for m in guild.members if m.bot])
    embed = discord.Embed(
        title="🤖 Bot Status",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👥 Members", value=f"{total - bots}", inline=True)
    embed.add_field(name="🤖 Bots", value=f"{bots}", inline=True)
    embed.add_field(name="⚙️ CPU", value=f"{cpu}%", inline=True)
    embed.add_field(name="💾 Memory", value=f"{mem.percent}% Used", inline=True)
    embed.add_field(name="🕒 Uptime", value=uptime, inline=True)
    embed.set_footer(text=f"{bot.user.name} • System Monitor")
    try:
        if status_message is None:
            status_message = await channel.send(embed=embed)
        else:
            await status_message.edit(embed=embed)
    except:
        pass

# ===================== RUN BOT =====================
bot.run(os.getenv("TOKEN"))
