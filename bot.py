import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
import psutil
import traceback

# ===================== CONFIG =====================
GUILD_ID = 1351310078849847358
MEMBER_ROLE_ID = 1386784222781505619

ALLOWED_USER_IDS = [1351310078887858299, 1386779868532047982]

SYSTEM_LOG_CHANNEL_ID = 1462412675295481971
VERIFY_LOG_CHANNEL_ID = 1462412645150752890
JOIN_LOG_CHANNEL_ID = 1462412615195164908
LEAVE_LOG_CHANNEL_ID = 1462412568747573422
BOT_STATUS_CHANNEL_ID = 1463660427413033093

VOICE_LOG_CHANNEL_ID = 1463842358448623822
TICKET_CATEGORY_ID = 1462421944170446869

TRACKED_VOICE_CHANNELS = [
    1461424134906056846,
    1462421172519178313,
    1439274257585799198,
    1457046754661765245,
    1432491181006127268
]

PROTECTED_IDS = ALLOWED_USER_IDS  # IDs that cannot be tagged

# ===================== INTENTS =====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===================== MEMORY =====================
START_TIME = datetime.now(timezone.utc)
status_message: discord.Message | None = None
invite_tracker = {}
tickets_open = {}

# ===================== HELPERS =====================
def get_channel(cid: int) -> discord.TextChannel | None:
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

async def send_embed(channel_id: int, title: str, color=discord.Color.green(),
                     fields: list[tuple[str,str,bool]] | None=None, thumbnail: str | None=None):
    channel = get_channel(channel_id)
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
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👥 Members", value=f"{total_members}", inline=True)
    embed.add_field(name="🤖 Bots", value=f"{total_bots}", inline=True)
    embed.add_field(name="⏱️ Uptime", value=format_uptime(), inline=True)
    embed.add_field(name="⚡ CPU Usage", value=f"{cpu}%", inline=True)
    embed.add_field(name="💾 Memory Usage", value=f"{mem_percent}% ({mem_used_gb:.0f}MB / {mem_total_gb:.0f}MB)", inline=True)
    embed.set_footer(text=f"{bot.user} • Status Update")
    return embed

# ===================== VIEWS =====================
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Verify Me", style=discord.ButtonStyle.green, custom_id="persistent_verify_button")
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
                ("🏷️ Role", role.mention, False)
            ],
            thumbnail=interaction.user.display_avatar.url
        )

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.blurple, custom_id="persistent_ticket_button")
    async def ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        category = guild.get_channel(TICKET_CATEGORY_ID)
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", category=category, overwrites=overwrites)
        tickets_open[interaction.user.id] = channel.id
        await channel.send(f"🎫 {interaction.user.mention}, your ticket has been created!")
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

# ===================== COMMANDS =====================
@bot.tree.command(name="verify", description="Verify yourself")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎉 Verify to Access",
        description="Click ✅ to get the **Member** role!\n💡 Ensure your account is not new.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, view=VerifyView())

@bot.tree.command(name="ticket", description="Open a support ticket")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Open a Support Ticket",
        description="Click the button below to open a **ticket**.\nStaff will assist you soon!",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=TicketView(), ephemeral=False)

@bot.tree.command(name="clear", description="Clear messages")
@app_commands.describe(amount="Number of messages")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def clear(interaction: discord.Interaction, amount: int):
    if interaction.user.id not in ALLOWED_USER_IDS:
        await interaction.response.send_message("❌ You cannot use this command.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

@bot.tree.command(name="message", description="Bot sends a custom message")
@app_commands.describe(content="Message content")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def message(interaction: discord.Interaction, content: str):
    if interaction.user.id not in ALLOWED_USER_IDS:
        await interaction.response.send_message("❌ You cannot use this command.", ephemeral=True)
        return
    await interaction.channel.send(content)
    await interaction.response.send_message("✅ Message sent.", ephemeral=True)

@bot.tree.command(name="test", description="Test all commands")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def test(interaction: discord.Interaction):
    if interaction.user.id not in ALLOWED_USER_IDS:
        await interaction.response.send_message("❌ You cannot use this command.", ephemeral=True)
        return
    # Trigger verify
    await verify(interaction)
    # Trigger ticket
    await ticket(interaction)
    # Trigger message
    await message(interaction, "This is a test message from /test")
    # Trigger clear
    await clear(interaction, 1)
    await interaction.response.send_message("✅ All commands triggered successfully!", ephemeral=True)

# ===================== EVENTS =====================
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    bot.add_view(TicketView())
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    update_status.start()
    # Fetch invites
    guild = bot.get_guild(GUILD_ID)
    if guild:
        for invite in await guild.invites():
            invite_tracker[invite.code] = invite.uses
    print(f"🟢 Logged in as {bot.user}")

# ===================== STATUS LOOP =====================
@tasks.loop(seconds=15)
async def update_status():
    global status_message
    channel = get_channel(BOT_STATUS_CHANNEL_ID)
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
