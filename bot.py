import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
import psutil
import traceback
import random

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
MESSAGE_LOG_CHANNEL_ID = 1462412675295481971  # Change this to your message logs channel
TICKET_CATEGORY_ID = 1462421944170446869

TRACKED_VOICE_CHANNELS = [
    1461424134906056846,
    1462421172519178313,
    1439274257585799198,
    1457046754661765245,
    1432491181006127268
]

PROTECTED_IDS = [1351310078887858299, 1386779868532047982]  # Admin/Dev/Owner

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
invite_tracker = {}  # track invites

# ===================== HELPERS =====================
def get_channel_safe(cid: int) -> discord.TextChannel | None:
    return bot.get_channel(cid)

def format_account_age(created_at: datetime) -> str:
    delta_days = (datetime.now(timezone.utc) - created_at).days
    years = delta_days // 365
    months = (delta_days % 365) // 30
    days = (delta_days % 365) % 30
    return f"{years}y {months}m {days}d"

def format_uptime() -> str:
    delta = datetime.now(timezone.utc) - START_TIME
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"

def is_allowed(user: discord.User) -> bool:
    return user.id in ALLOWED_USER_IDS

async def send_embed(channel_id: int, title: str, color=discord.Color.green(),
                     fields: list[tuple[str,str,bool]] | None=None, thumbnail: str | None=None):
    channel = get_channel_safe(channel_id)
    if not channel:
        return
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    await channel.send(embed=embed)

async def get_status_embed() -> discord.Embed:
    guild = bot.get_guild(GUILD_ID)
    total_members = sum(1 for m in guild.members if not m.bot) if guild else 0
    total_bots = sum(1 for m in guild.members if m.bot) if guild else 0
    cpu = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    mem_used_gb = memory.used / (1024**2)
    mem_total_gb = memory.total / (1024**2)
    mem_percent = memory.percent

    embed = discord.Embed(
        title="🤖 Bot Status",
        description="Big, aesthetic statistics of the bot's current state",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👥 Members", value=f"{total_members}", inline=True)
    embed.add_field(name="🤖 Bots", value=f"{total_bots}", inline=True)
    embed.add_field(name="⏱️ Uptime", value=format_uptime(), inline=True)
    embed.add_field(name="⚡ CPU Usage", value=f"{cpu}%", inline=True)
    embed.add_field(name="💾 Memory Usage", value=f"{mem_percent}% ({mem_used_gb:.0f}MB / {mem_total_gb:.0f}MB)", inline=True)
    embed.set_footer(text=f"{bot.user} • Status Update")
    return embed

# ===================== VERIFY VIEW =====================
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Verify Yourself", style=discord.ButtonStyle.success, custom_id="persistent_verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if not role:
            await interaction.response.send_message("❌ Member role not found.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("ℹ️ Already verified.", ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="Server verification")
        await interaction.response.send_message("🎉 You are now verified!", ephemeral=True)
        await send_embed(
            VERIFY_LOG_CHANNEL_ID,
            "✅ Member Verified",
            color=discord.Color.green(),
            fields=[
                ("👤 User", f"{interaction.user.mention}\n`{interaction.user.id}`", False),
                ("📅 Account Age", format_account_age(interaction.user.created_at), False),
                ("🏷️ Role", role.mention, False),
                ("🕒 Verified At", f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", False)
            ],
            thumbnail=interaction.user.display_avatar.url
        )

# ===================== TICKET VIEW =====================
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.primary, custom_id="persistent_ticket_button")
    async def ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        existing = discord.utils.get(guild.channels, name=f"ticket-{interaction.user.name}".lower())
        if existing:
            await interaction.response.send_message(f"❗ You already have an open ticket: {existing.mention}", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}".lower(),
            category=category,
            overwrites=overwrites
        )
        await interaction.response.send_message(f"🎫 Ticket created: {channel.mention}", ephemeral=True)
        await channel.send(f"Hello {interaction.user.mention}, please describe your issue. Our staff will respond soon!")

# ===================== COMMANDS =====================
@bot.tree.command(name="verify", description="Verify yourself to get access")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎉 Verify to Join",
        description="Click the button below to get the **Member** role.\n\n💡 **Note:** Only verified members can see most channels.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, view=VerifyView(), ephemeral=True)

@bot.tree.command(name="ticket", description="Open a support ticket")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Open a Ticket",
        description="Click the button below to open a support ticket.\n🛠️ Our staff will assist you as soon as possible!",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, view=TicketView(), ephemeral=True)

@bot.tree.command(name="8ball", description="Ask the magic 8 ball a question")
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(question="Your question for the magic 8 ball")
async def eightball(interaction: discord.Interaction, question: str):
    responses = ["Yes, definitely", "No, not at all", "Ask again later", "Absolutely", "Cannot predict now", "Don't count on it", "It is certain", "Very doubtful", "Outlook good", "Signs point to yes"]
    response = random.choice(responses)
    embed = discord.Embed(title="🎱 Magic 8 Ball", description=f"**Q:** {question}\n\n**A:** {response}", color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dice", description="Roll a dice")
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(sides="Number of sides (default: 6)")
async def dice(interaction: discord.Interaction, sides: int = 6):
    if sides < 2 or sides > 100:
        await interaction.response.send_message("❌ Dice must have 2-100 sides.", ephemeral=True)
        return
    roll = random.randint(1, sides)
    embed = discord.Embed(title="🎲 Dice Roll", description=f"You rolled a **d{sides}** and got **{roll}**!", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="Flip a coin")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    emoji = "🪙"
    embed = discord.Embed(title="Coin Flip", description=f"{emoji} **{result}**!", color=discord.Color.silver())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rps", description="Play rock, paper, scissors")
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(choice="Your choice: rock, paper, or scissors")
async def rps(interaction: discord.Interaction, choice: str):
    choices = ["rock", "paper", "scissors"]
    choice = choice.lower()
    if choice not in choices:
        await interaction.response.send_message("❌ Choose: rock, paper, or scissors", ephemeral=True)
        return
    bot_choice = random.choice(choices)
    outcomes = {
        ("rock", "scissors"): "🎉 You win!",
        ("scissors", "paper"): "🎉 You win!",
        ("paper", "rock"): "🎉 You win!",
        ("rock", "rock"): "🤝 It's a tie!",
        ("paper", "paper"): "🤝 It's a tie!",
        ("scissors", "scissors"): "🤝 It's a tie!"
    }
    result = outcomes.get((choice, bot_choice), "❌ Bot wins!")
    embed = discord.Embed(title="Rock, Paper, Scissors", description=f"You: **{choice.upper()}**\nBot: **{bot_choice.upper()}**\n\n{result}", color=discord.Color.blue())
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

# ===================== JOIN / LEAVE LOGS =====================
@bot.event
async def on_member_join(member):
    guild = member.guild
    inviter_name = "Unknown"
    try:
        invites_before = invite_tracker.copy()
        current_invites = await guild.invites()
        for inv in current_invites:
            uses_before = invites_before.get(inv.code, 0)
            if inv.uses > uses_before:
                inviter_name = inv.inviter.mention
                invite_tracker[inv.code] = inv.uses
                break
    except:
        pass
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    risk = "⚠️ High" if age_days < 7 else "✅ Low"
    await send_embed(
        JOIN_LOG_CHANNEL_ID,
        "🟢 Member Joined",
        color=discord.Color.green(),
        fields=[
            ("👤 User", f"{member.mention}\n`{member.id}`", False),
            ("📅 Account Created", f"<t:{int(member.created_at.timestamp())}:F>", False),
            ("📊 Risk Score", risk, False),
            ("🚨 Alt Detection", "✅" if age_days >= 7 else "❌ New account", False),
            ("📥 Invited By", inviter_name, False),
            ("💻 Account Age", format_account_age(member.created_at), False),
        ],
        thumbnail=member.display_avatar.url
    )

@bot.event
async def on_member_remove(member):
    guild = member.guild
    reason = "Left voluntarily"
    mod = None
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            reason = "Kicked"
            mod = entry.user.mention
            break
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
        if entry.target.id == member.id:
            reason = "Banned"
            mod = entry.user.mention
            break
    await send_embed(
        LEAVE_LOG_CHANNEL_ID,
        "🔴 Member Left",
        color=discord.Color.red(),
        fields=[
            ("👤 User", f"{member.mention}\n`{member.id}`", False),
            ("⚡ Left By", mod if mod else reason, False),
            ("💻 Account Age", format_account_age(member.created_at), False),
            ("📅 Account Created", f"<t:{int(member.created_at.timestamp())}:F>", False),
        ],
        thumbnail=member.display_avatar.url
    )

# ===================== ROLE LOGS =====================
@bot.event
async def on_member_update(before, after):
    guild = after.guild
    added_roles = [r for r in after.roles if r not in before.roles]
    removed_roles = [r for r in before.roles if r not in after.roles]
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
        if entry.target.id != after.id:
            continue
        for role in added_roles:
            await send_embed(
                SYSTEM_LOG_CHANNEL_ID,
                "➕ Role Added",
                color=discord.Color.green(),
                fields=[
                    ("👤 User", f"{after.mention}\n`{after.id}`", False),
                    ("🏷️ Role", role.mention, False),
                    ("🛡️ Added By", entry.user.mention, False),
                    ("🕒 Time", f"<t:{int(entry.created_at.timestamp())}:F>", False)
                ]
            )
        for role in removed_roles:
            await send_embed(
                SYSTEM_LOG_CHANNEL_ID,
                "➖ Role Removed",
                color=discord.Color.red(),
                fields=[
                    ("👤 User", f"{after.mention}\n`{after.id}`", False),
                    ("🏷️ Role", role.mention, False),
                    ("🛡️ Removed By", entry.user.mention, False),
                    ("🕒 Time", f"<t:{int(entry.created_at.timestamp())}:F>", False)
                ]
            )
        break

# ===================== VOICE LOGS =====================
@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel == after.channel:
        return
    if before.channel and before.channel.id in TRACKED_VOICE_CHANNELS:
        await send_embed(
            VOICE_LOG_CHANNEL_ID,
            "🔴 Voice Channel Left",
            color=discord.Color.red(),
            fields=[
                ("👤 User", f"{member.mention}\n`{member.id}`", False),
                ("🎙️ Channel Left", before.channel.mention, False),
                ("🕒 Time", f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", False)
            ],
            thumbnail=member.display_avatar.url
        )
    if after.channel and after.channel.id in TRACKED_VOICE_CHANNELS:
        await send_embed(
            VOICE_LOG_CHANNEL_ID,
            "🟢 Voice Channel Joined",
            color=discord.Color.green(),
            fields=[
                ("👤 User", f"{member.mention}\n`{member.id}`", False),
                ("🎙️ Channel Joined", after.channel.mention, False),
                ("🕒 Time", f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", False)
            ],
            thumbnail=member.display_avatar.url
        )

# ===================== MESSAGE LOGGING =====================
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    await send_embed(
        MESSAGE_LOG_CHANNEL_ID,
        "🗑️ Message Deleted",
        color=discord.Color.red(),
        fields=[
            ("👤 Author", f"{message.author.mention}\n`{message.author.id}`", False),
            ("💬 Content", message.content[:1024] if message.content else "(no text)", False),
            ("📍 Channel", message.channel.mention, False),
            ("🕒 Time", f"<t:{int(message.created_at.timestamp())}:F>", False)
        ],
        thumbnail=message.author.display_avatar.url
    )

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    await send_embed(
        MESSAGE_LOG_CHANNEL_ID,
        "✏️ Message Edited",
        color=discord.Color.orange(),
        fields=[
            ("👤 Author", f"{before.author.mention}\n`{before.author.id}`", False),
            ("📝 Before", before.content[:1024] if before.content else "(no text)", False),
            ("📝 After", after.content[:1024] if after.content else "(no text)", False),
            ("📍 Channel", before.channel.mention, False),
            ("🕒 Time", f"<t:{int(before.edited_at.timestamp() if before.edited_at else datetime.now(timezone.utc).timestamp())}:F>", False)
        ],
        thumbnail=before.author.display_avatar.url
    )

# ===================== MESSAGE TAG WARNING =====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    for user in message.mentions:
        if user.id in PROTECTED_IDS:
            try:
                await message.add_reaction("⚠️")
                await message.channel.send(f"❌ {message.author.mention}, please do not tag my higher-up staff!")
            except:
                pass
    await bot.process_commands(message)

# ===================== BOT STATUS =====================
@tasks.loop(seconds=10)
async def update_status():
    global status_message
    channel = get_channel_safe(BOT_STATUS_CHANNEL_ID)
    if not channel:
        return
    embed = await get_status_embed()
    try:
        if status_message is None:
            status_message = await channel.send(embed=embed)
        else:
            await status_message.edit(embed=embed)
    except Exception as e:
        print(f"❌ Failed to update status: {e}")

# ===================== RUN BOT =====================
bot.run(os.getenv("TOKEN"))
