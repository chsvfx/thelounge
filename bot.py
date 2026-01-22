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

# ===================== INTENTS =====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===================== MEMORY =====================
START_TIME = datetime.now(timezone.utc)
invite_tracker = {}

# ===================== HELPERS =====================
def format_account_age(dt: datetime) -> str:
    delta_days = (datetime.now(timezone.utc) - dt).days
    years = delta_days // 365
    months = (delta_days % 365) // 30
    days = (delta_days % 365) % 30
    return f"{years}y {months}m {days}d"

def format_uptime() -> str:
    delta = datetime.now(timezone.utc) - START_TIME
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"

async def send_embed(channel_id: int, embed: discord.Embed):
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(embed=embed)

def calculate_risk_score(member: discord.Member) -> str:
    """Simple risk scoring based on account age, new accounts get warning."""
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    if age_days < 7:
        return "High ⚠️"
    elif age_days < 30:
        return "Medium ⚠️"
    else:
        return "Low ✅"

# ===================== EVENTS =====================
@bot.event
async def on_ready():
    print(f"🟢 Logged in as {bot.user}")
    # Track invites
    guild = bot.get_guild(GUILD_ID)
    if guild:
        for inv in await guild.invites():
            invite_tracker[inv.code] = inv.uses
    update_status.start()

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    account_age_days = (datetime.now(timezone.utc) - member.created_at).days

    # Track inviter
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

    # Risk score
    risk_score = calculate_risk_score(member)

    embed = discord.Embed(
        title="🟢 Member Joined",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{member.mention}\n**{member}**", inline=False)
    embed.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="🤖 Bot?", value="Yes" if member.bot else "No", inline=True)
    embed.add_field(name="📅 Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
    embed.add_field(name="⏳ Account Age", value=f"{account_age_days} days", inline=True)
    embed.add_field(name="👥 Member Count", value=str(guild.member_count), inline=True)
    embed.add_field(name="📊 Risk Score", value=risk_score, inline=False)
    embed.add_field(name="📥 Invited By", value=inviter_name, inline=True)

    await send_embed(JOIN_LOG_CHANNEL_ID, embed)

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    account_age_days = (datetime.now(timezone.utc) - member.created_at).days

    # Audit log for kick/ban
    reason = "Left voluntarily"
    moderator = None
    try:
        async for entry in guild.audit_logs(limit=5):
            if entry.target.id != member.id:
                continue
            if entry.action == discord.AuditLogAction.kick:
                reason = "Kicked"
                moderator = entry.user
                break
            elif entry.action == discord.AuditLogAction.ban:
                reason = "Banned"
                moderator = entry.user
                break
    except:
        pass

    risk_score = calculate_risk_score(member)

    embed = discord.Embed(
        title="🔴 Member Left",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 User", value=f"**{member}**\n`{member.id}`", inline=False)
    embed.add_field(name="🤖 Bot?", value="Yes" if member.bot else "No", inline=True)
    embed.add_field(name="📅 Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
    embed.add_field(name="⏳ Account Age", value=f"{account_age_days} days", inline=True)
    embed.add_field(name="⚠️ Leave Reason", value=reason, inline=True)
    if moderator:
        embed.add_field(name="🛡️ Action By", value=moderator.mention, inline=False)
    embed.add_field(name="📊 Risk Score", value=risk_score, inline=False)

    await send_embed(LEAVE_LOG_CHANNEL_ID, embed)

# ===================== BOT STATUS =====================
@tasks.loop(seconds=30)
async def update_status():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    total_members = sum(1 for m in guild.members if not m.bot)
    total_bots = sum(1 for m in guild.members if m.bot)

    cpu = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    mem_used_gb = memory.used / (1024**2)
    mem_total_gb = memory.total / (1024**2)

    embed = discord.Embed(
        title="🤖 Bot Status",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👥 Members", value=f"{total_members}", inline=True)
    embed.add_field(name="🤖 Bots", value=f"{total_bots}", inline=True)
    embed.add_field(name="⏱️ Uptime", value=format_uptime(), inline=True)
    embed.add_field(name="⚡ CPU Usage", value=f"{cpu}%", inline=True)
    embed.add_field(name="💾 Memory Usage", value=f"{memory.percent}% ({mem_used_gb:.0f}MB / {mem_total_gb:.0f}MB)", inline=True)
    embed.set_footer(text=f"{guild.name} • Status Update")

    channel = bot.get_channel(BOT_STATUS_CHANNEL_ID)
    if channel:
        async for msg in channel.history(limit=10):
            if msg.author == bot.user:
                await msg.edit(embed=embed)
                return
        await channel.send(embed=embed)

# ===================== RUN BOT =====================
bot.run(os.getenv("TOKEN"))
