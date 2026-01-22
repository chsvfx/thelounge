import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
import psutil
import traceback
import asyncio

# ===================== CONFIG =====================
GUILD_ID = 1351310078849847358
MEMBER_ROLE_ID = 1386784222781505619

ALLOWED_USER_IDS = [1351310078887858299, 1386779868532047982]
PROTECTED_IDS = [1351310078887858299, 1386779868532047982]

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
status_message: discord.Message | None = None
invite_tracker = {}
persistent_views_added = False

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

    @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.success, custom_id="persistent_verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if not role:
            await interaction.response.send_message("❌ Member role not found.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("ℹ️ Already verified.", ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="Server verification")
        await interaction.response.send_message("✅ You are now verified!", ephemeral=True)
        # Send log
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

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.primary, custom_id="persistent_ticket_button")
    async def ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        channel = await interaction.guild.create_text_channel(
            f"ticket-{interaction.user.name}", category=category, overwrites=overwrites
        )
        await interaction.response.send_message(f"🎟️ Your ticket has been created: {channel.mention}", ephemeral=True)

# ===================== EVENTS =====================
@bot.event
async def on_ready():
    global persistent_views_added, invite_tracker, status_message
    if not persistent_views_added:
        bot.add_view(VerifyView())
        bot.add_view(TicketView())
        persistent_views_added = True

    guild = bot.get_guild(GUILD_ID)
    if guild:
        for invite in await guild.invites():
            invite_tracker[invite.code] = invite.uses

    # Sync commands
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"🟢 Logged in as {bot.user} | Commands synced")

    # Send status message if not exists
    channel = get_channel_safe(BOT_STATUS_CHANNEL_ID)
    if channel:
        try:
            messages = [m async for m in channel.history(limit=50)]
            status_message = next((m for m in messages if m.author == bot.user), None)
            if not status_message:
                status_message = await channel.send(embed=await get_status_embed())
        except Exception as e:
            print(f"❌ Failed to fetch/send status message: {e}")

# ===================== LOGGING =====================
def calculate_risk(member: discord.Member) -> str:
    # Simple risk example: new accounts under 7 days are risky
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    if age_days < 7:
        return "⚠️ High (New Account)"
    elif age_days < 30:
        return "⚠️ Medium"
    return "✅ Low"

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    inviter_name = "Unknown"
    invite_used = "Unknown"
    try:
        invites_before = invite_tracker.copy()
        current_invites = await guild.invites()
        for inv in current_invites:
            uses_before = invites_before.get(inv.code, 0)
            if inv.uses > uses_before:
                inviter_name = inv.inviter.mention
                invite_used = inv.code
                invite_tracker[inv.code] = inv.uses
                break
    except Exception:
        pass

    embed = discord.Embed(
        title="🟢 Member Joined",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=False)
    embed.add_field(name="📅 Account Age", value=format_account_age(member.created_at), inline=False)
    embed.add_field(name="📥 Invite Used", value=f"{invite_used}", inline=False)
    embed.add_field(name="⚡ Invited By", value=inviter_name, inline=False)
    embed.add_field(name="📊 Risk Score", value=calculate_risk(member), inline=False)
    embed.add_field(name="🕒 Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
    await send_embed(JOIN_LOG_CHANNEL_ID, embed.title, color=discord.Color.green(),
                     fields=[(f.name, f.value, f.inline) for f in embed.fields], thumbnail=member.display_avatar.url)

@bot.event
async def on_member_remove(member: discord.Member):
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

    embed = discord.Embed(
        title="🔴 Member Left",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=False)
    embed.add_field(name="⚡ Left By", value=mod if mod else reason, inline=False)
    embed.add_field(name="🕒 Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
    await send_embed(LEAVE_LOG_CHANNEL_ID, embed.title, color=discord.Color.red(),
                     fields=[(f.name, f.value, f.inline) for f in embed.fields], thumbnail=member.display_avatar.url)

# ===================== ROLE LOGGING =====================
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild
    added_roles = [role for role in after.roles if role not in before.roles]
    removed_roles = [role for role in before.roles if role not in after.roles]

    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
        if entry.target.id != after.id:
            continue

        for role in added_roles:
            embed = discord.Embed(title="➕ Role Added", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
            embed.add_field(name="👤 User", value=f"{after.mention}\n`{after.id}`", inline=False)
            embed.add_field(name="🏷️ Role", value=role.mention, inline=False)
            embed.add_field(name="🛡️ Added By", value=entry.user.mention, inline=False)
            embed.add_field(name="🕒 Time", value=f"<t:{int(entry.created_at.timestamp())}:F>", inline=False)
            await send_embed(SYSTEM_LOG_CHANNEL_ID, embed.title, color=discord.Color.green(),
                             fields=[(f.name, f.value, f.inline) for f in embed.fields])

        for role in removed_roles:
            embed = discord.Embed(title="➖ Role Removed", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
            embed.add_field(name="👤 User", value=f"{after.mention}\n`{after.id}`", inline=False)
            embed.add_field(name="🏷️ Role", value=role.mention, inline=False)
            embed.add_field(name="🛡️ Removed By", value=entry.user.mention, inline=False)
            embed.add_field(name="🕒 Time", value=f"<t:{int(entry.created_at.timestamp())}:F>", inline=False)
            await send_embed(SYSTEM_LOG_CHANNEL_ID, embed.title, color=discord.Color.red(),
                             fields=[(f.name, f.value, f.inline) for f in embed.fields])
        break

# ===================== BOT STATUS LOOP =====================
@tasks.loop(seconds=30)
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
    except discord.Forbidden:
        print("❌ Missing permissions in status channel")
    except Exception as e:
        print(f"❌ Failed to update status: {e}")

# ===================== MESSAGE COMMAND =====================
@bot.tree.command(name="message", description="Send a custom message via bot")
@app_commands.describe(content="Message content")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def message(interaction: discord.Interaction, content: str):
    if interaction.user.id not in ALLOWED_USER_IDS:
        await interaction.response.send_message("❌ You are not allowed to use this.", ephemeral=True)
        return
    await interaction.response.send_message(content)
