import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
import traceback
import psutil

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
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.invites = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===================== MEMORY =====================
START_TIME = datetime.now(timezone.utc)
status_message: discord.Message | None = None
invite_tracker = {}  # Track who invited whom

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

def get_time_string(dt: datetime) -> str:
    return dt.strftime("%H:%M • %d/%m/%Y")

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

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.primary, custom_id="persistent_ticket_button")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        existing = discord.utils.get(guild.channels, name=f"ticket-{interaction.user.id}")
        if existing:
            await interaction.response.send_message("❌ You already have a ticket open!", ephemeral=True)
            return
        category = guild.get_channel(TICKET_CATEGORY_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True)
        }
        channel = await guild.create_text_channel(f"ticket-{interaction.user.id}", category=category, overwrites=overwrites, reason="Ticket created")
        await interaction.response.send_message(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)
        embed = discord.Embed(
            title="🎫 Ticket Support",
            description=(
                f"👋 Hello {interaction.user.mention}!\n\n"
                "Please describe your issue clearly. Staff will respond shortly.\n\n"
                "🔹 Be respectful\n🔹 Do not spam\n🔹 Tickets are private"
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        await channel.send(embed=embed, view=CloseTicketView())

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="persistent_close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

# ===================== COMMANDS =====================
def is_allowed(interaction: discord.Interaction) -> bool:
    return interaction.user.id in ALLOWED_USER_IDS

@bot.tree.command(name="verify", description="Verify yourself")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎉 Verify to Join",
        description="Click the button below to receive the **Member** role.\n\n"
                    "✅ Gives access to server channels\n"
                    "🛡️ Safe verification\n"
                    "🔹 Only one click needed",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, view=VerifyView())

@bot.tree.command(name="ticket", description="Open a support ticket")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticket_cmd(interaction: discord.Interaction):
    if not is_allowed(interaction):
        await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
        return
    embed = discord.Embed(
        title="🎫 Need Help? Open a Ticket!",
        description=(
            "👋 Welcome! Use the button below to open a **private support ticket**.\n\n"
            "🔹 Ask questions or report issues\n"
            "🔹 Staff will respond here\n"
            "🔹 Your ticket is private and visible only to you and staff\n\n"
            "⚠️ Make sure to explain your issue clearly so we can help you faster!\n"
            "✅ You can close the ticket anytime with the button inside."
        ),
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"{interaction.guild.name} • Ticket Panel")
    await interaction.response.send_message(embed=embed, view=TicketView(), ephemeral=False)

# ===================== EVENTS =====================
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

    guild = bot.get_guild(GUILD_ID)
    if guild:
        for invite in await guild.invites():
            invite_tracker[invite.code] = invite.uses
    print(f"🟢 Logged in as {bot.user}")
    update_status.start()

@bot.event
async def on_error(event, *args, **kwargs):
    err = traceback.format_exc()
    await send_embed(SYSTEM_LOG_CHANNEL_ID, "⚠️ System Error", color=discord.Color.red(),
                     fields=[("", f"```{err}```", False)])
    print(err)

# ===================== JOIN / LEAVE LOGS =====================
@bot.event
async def on_member_join(member: discord.Member):
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
    except Exception:
        pass

    risk_score = "Low" if (datetime.now(timezone.utc) - member.created_at).days > 7 else "High"
    alt_detected = "Yes" if (datetime.now(timezone.utc) - member.created_at).days < 7 else "No"

    embed = discord.Embed(title="🟢 Member Joined", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
    embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=False)
    embed.add_field(name="📅 Account Age", value=format_account_age(member.created_at), inline=True)
    embed.add_field(name="🔐 Risk Score", value=risk_score, inline=True)
    embed.add_field(name="🚨 Alt Detection", value=alt_detected, inline=True)
    embed.add_field(name="📥 Invite Used", value=inviter_name, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    await send_embed(JOIN_LOG_CHANNEL_ID, embed.title, color=discord.Color.green(), fields=[
        ("👤 User", f"{member.mention}\n`{member.id}`", False),
        ("📅 Account Age", format_account_age(member.created_at), True),
        ("🔐 Risk Score", risk_score, True),
        ("🚨 Alt Detection", alt_detected, True),
        ("📥 Invite Used", inviter_name, True)
    ], thumbnail=member.display_avatar.url)

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

    risk_score = "Unknown"
    alt_detected = "Unknown"

    embed = discord.Embed(title="🔴 Member Left", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
    embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=False)
    embed.add_field(name="⚡ Left By", value=mod if mod else reason, inline=True)
    embed.add_field(name="🔐 Risk Score", value=risk_score, inline=True)
    embed.add_field(name="🚨 Alt Detection", value=alt_detected, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    await send_embed(LEAVE_LOG_CHANNEL_ID, embed.title, color=discord.Color.red(), fields=[
        ("👤 User", f"{member.mention}\n`{member.id}`", False),
        ("⚡ Left By", mod if mod else reason, True),
        ("🔐 Risk Score", risk_score, True),
        ("🚨 Alt Detection", alt_detected, True)
    ], thumbnail=member.display_avatar.url)

# ===================== ROLE LOGGING =====================
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild
    added_roles = [role for role in after.roles if role not in before.roles]
    removed_roles = [role for role in before.roles if role not in after.roles]

    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
        if entry.target.id != after.id:
            continue

        time_str = get_time_string(datetime.now(timezone.utc))

        for role in added_roles:
            await send_embed(
                SYSTEM_LOG_CHANNEL_ID,
                "➕ Role Added",
                color=discord.Color.green(),
                fields=[
                    ("👤 User", f"{after.mention}\n`{after.id}`", False),
                    ("🏷️ Role", role.mention, False),
                    ("🛡️ Added By", entry.user.mention, False),
                    ("⏰ Time", time_str, False)
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
                    ("⏰ Time", time_str, False)
                ]
            )
        break

# ===================== VOICE LOGGING =====================
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    if before.channel == after.channel:
        return
    if (before.channel and before.channel.id in TRACKED_VOICE_CHANNELS) or (after.channel and after.channel.id in TRACKED_VOICE_CHANNELS):
        time_str = get_time_string(datetime.now(timezone.utc))
        if before.channel is None and after.channel:
            # Joined voice
            await send_embed(VOICE_LOG_CHANNEL_ID, "🔊 Voice Joined", color=discord.Color.green(), fields=[
                ("👤 User", f"{member.mention}\n`{member.id}`", False),
                ("🎤 Channel", after.channel.mention, False),
                ("⏰ Time", time_str, False)
            ])
        elif before.channel and after.channel is None:
            # Left voice
            await send_embed(VOICE_LOG_CHANNEL_ID, "🔈 Voice Left", color=discord.Color.red(), fields=[
                ("👤 User", f"{member.mention}\n`{member.id}`", False),
                ("🎤 Channel", before.channel.mention, False),
                ("⏰ Time", time_str, False)
            ])
        elif before.channel and after.channel and before.channel.id != after.channel.id:
            # Moved voice
            await send_embed(VOICE_LOG_CHANNEL_ID, "🔀 Voice Moved", color=discord.Color.orange(), fields=[
                ("👤 User", f"{member.mention}\n`{member.id}`", False),
                ("🎤 From", before.channel.mention, True),
                ("🎤 To", after.channel.mention, True),
                ("⏰ Time", time_str, False)
            ])

# ===================== BOT STATUS =====================
@tasks.loop(seconds=60)
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

# ===================== RUN BOT =====================
bot.run(os.getenv("TOKEN"))
