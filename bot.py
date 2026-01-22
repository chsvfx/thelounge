# ============================================================
# 🤖 THE LOUNGE™ — MONSTER CORE BOT FILE (PART 1 / 2)
# ============================================================
# THIS FILE CONTAINS:
# - CONFIG
# - INTENTS
# - BOT SETUP
# - PERMISSIONS (ID BASED)
# - VERIFY SYSTEM
# - TICKET SYSTEM
# - MESSAGE COMMAND
# - TAG PROTECTION
# - EMBED STYLE (UNCHANGED)
#
# ⚠️ DO NOT OPTIMIZE
# ⚠️ DO NOT SHORTEN
# ⚠️ DO NOT CLEAN
# ============================================================

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
import traceback
import psutil

# ============================================================
# 🔧 CONFIGURATION — IDS & SETTINGS (VERBOSE ON PURPOSE)
# ============================================================

GUILD_ID = 1351310078849847358

MEMBER_ROLE_ID = 1386784222781505619

# ✅ ONLY THESE USERS CAN USE COMMANDS
ALLOWED_USER_IDS = [
    771432636563324929,
    1329386427460358188
]

# 🛡️ PROTECTED HIGHER-UP IDS (ADMIN / DEV / OWNER)
PROTECTED_IDS = [
    1351310078887858299,
    1386779868532047982
]

# 📁 CHANNEL IDS
SYSTEM_LOG_CHANNEL_ID = 1462412675295481971
VERIFY_LOG_CHANNEL_ID = 1462412645150752890
JOIN_LOG_CHANNEL_ID = 1462412615195164908
LEAVE_LOG_CHANNEL_ID = 1462412568747573422
BOT_STATUS_CHANNEL_ID = 1463660427413033093
VOICE_LOG_CHANNEL_ID = 1463842358448623822

# 🎫 TICKETS
TICKET_CATEGORY_ID = 1462421944170446869

# 🎙️ TRACKED VOICE CHANNELS
TRACKED_VOICE_CHANNELS = [
    1461424134906056846,
    1462421172519178313,
    1439274257585799198,
    1457046754661765245,
    1432491181006127268
]

# ============================================================
# 🧠 INTENTS — EXPLICIT & FULL
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.voice_states = True
intents.reactions = True
intents.presences = False

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ============================================================
# 🧠 MEMORY & STATE
# ============================================================

START_TIME = datetime.now(timezone.utc)

status_message: discord.Message | None = None

invite_tracker: dict[str, int] = {}

# ============================================================
# 🧩 PERMISSION CHECKS (ID BASED ONLY)
# ============================================================

def is_allowed_user(user: discord.abc.User) -> bool:
    return user.id in ALLOWED_USER_IDS

# ============================================================
# 🧰 HELPER FUNCTIONS (VERBOSE)
# ============================================================

def get_channel_safe(channel_id: int):
    channel = bot.get_channel(channel_id)
    return channel

def format_account_age(created_at: datetime) -> str:
    delta = datetime.now(timezone.utc) - created_at
    days = delta.days
    years = days // 365
    months = (days % 365) // 30
    remaining_days = (days % 365) % 30
    return f"{years}y {months}m {remaining_days}d"

def format_uptime() -> str:
    delta = datetime.now(timezone.utc) - START_TIME
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"

# ============================================================
# 🎨 EMBED BUILDER — EXACT STYLE, BIG, AESTHETIC
# ============================================================

async def send_big_embed(
    channel_id: int,
    title: str,
    description: str | None = None,
    color: discord.Color = discord.Color.blurple(),
    fields: list[tuple[str, str, bool]] | None = None,
    thumbnail: str | None = None,
    footer: str | None = None
):
    channel = get_channel_safe(channel_id)
    if not channel:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    if fields:
        for name, value, inline in fields:
            embed.add_field(
                name=name,
                value=value,
                inline=inline
            )

    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    if footer:
        embed.set_footer(text=footer)

    await channel.send(embed=embed)

# ============================================================
# ✅ VERIFY VIEW — PERSISTENT BUTTON
# ============================================================

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ Verify Yourself",
        emoji="✨",
        style=discord.ButtonStyle.success,
        custom_id="persistent_verify_button"
    )
    async def verify_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_allowed_user(interaction.user):
            await interaction.response.send_message(
                "❌ You are not allowed to use verification.",
                ephemeral=True
            )
            return

        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if not role:
            await interaction.response.send_message(
                "❌ Member role not found.",
                ephemeral=True
            )
            return

        if role in interaction.user.roles:
            await interaction.response.send_message(
                "ℹ️ You are already verified.",
                ephemeral=True
            )
            return

        await interaction.user.add_roles(
            role,
            reason="Verification via verify button"
        )

        await interaction.response.send_message(
            "🎉 **Verification successful!** Welcome to the server.",
            ephemeral=True
        )

# ============================================================
# 🎫 TICKET VIEW — PERSISTENT BUTTON
# ============================================================

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Open Support Ticket",
        emoji="🛠️",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_ticket_button"
    )
    async def ticket_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_allowed_user(interaction.user):
            await interaction.response.send_message(
                "❌ You are not allowed to open tickets.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)

        ticket_name = f"ticket-{interaction.user.id}"

        existing = discord.utils.get(guild.text_channels, name=ticket_name)
        if existing:
            await interaction.response.send_message(
                f"❗ You already have an open ticket: {existing.mention}",
                ephemeral=True
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )
        }

        channel = await guild.create_text_channel(
            name=ticket_name,
            category=category,
            overwrites=overwrites
        )

        await interaction.response.send_message(
            f"🎫 Ticket created: {channel.mention}",
            ephemeral=True
        )

        await channel.send(
            f"👋 Hello {interaction.user.mention}\n\n"
            f"Please describe your issue in detail.\n"
            f"Our staff will assist you as soon as possible."
        )

# ============================================================
# 💬 /MESSAGE COMMAND — SEND AS BOT
# ============================================================

@bot.tree.command(
    name="message",
    description="Send a message as the bot"
)
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def message_command(
    interaction: discord.Interaction,
    text: str
):
    if not is_allowed_user(interaction.user):
        await interaction.response.send_message(
            "❌ You are not allowed to use this command.",
            ephemeral=True
        )
        return

    await interaction.channel.send(text)
    await interaction.response.send_message(
        "✅ Message sent successfully.",
        ephemeral=True
    )

# ============================================================
# 🏷️ TAG PROTECTION SYSTEM
# ============================================================

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    for mentioned_user in message.mentions:
        if mentioned_user.id in PROTECTED_IDS:
            try:
                await message.add_reaction("⚠️")
                await message.channel.send(
                    f"🚫 {message.author.mention}, "
                    f"please **do not tag higher-up staff**."
                )
            except:
                pass

    await bot.process_commands(message)

# ============================================================
# 🔄 READY EVENT — REGISTER PERSISTENT VIEWS
# ============================================================

@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    bot.add_view(TicketView())

    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

    print(f"🟢 Logged in as {bot.user}")

# ============================================================
# 🚀 BOT RUN
# ============================================================

# ============================================================
# 📜 THE LOUNGE™ — MONSTER LOGS & EVENTS FILE (PART 2 / 2)
# ============================================================
# THIS FILE CONTAINS:
# - on_ready EXTENSIONS
# - INVITE TRACKING
# - MEMBER JOIN LOGS (BIG)
# - MEMBER LEAVE LOGS (BIG)
# - ROLE ADD / REMOVE LOGS (BIG)
# - VOICE JOIN / LEAVE / MOVE LOGS
# - BOT STATUS SYSTEM (BIG EMBED)
# - ERROR SAFETY
#
# ⚠️ DESIGNED TO BE MERGED WITH FILE 1
# ⚠️ SAME BOT INSTANCE REQUIRED
# ============================================================

# ============================================================
# 📥 INVITE TRACKING INITIALIZATION
# ============================================================

@bot.event
async def on_ready():
    guild = bot.get_guild(GUILD_ID)
    if guild:
        try:
            invites = await guild.invites()
            for invite in invites:
                invite_tracker[invite.code] = invite.uses
        except Exception:
            pass

    update_bot_status.start()

    print("📜 LOG SYSTEM READY")
    print("🎙️ VOICE LOGS ENABLED")
    print("👥 MEMBER LOGS ENABLED")

# ============================================================
# 👥 MEMBER JOIN — HUGE AESTHETIC EMBED
# ============================================================

@bot.event
async def on_member_join(member: discord.Member):
    inviter_display = "❓ Unknown"
    invite_code = "Unknown"

    try:
        invites_after = await member.guild.invites()
        for invite in invites_after:
            previous_uses = invite_tracker.get(invite.code, 0)
            if invite.uses > previous_uses:
                inviter_display = invite.inviter.mention
                invite_code = invite.code
                invite_tracker[invite.code] = invite.uses
                break
    except Exception:
        pass

    account_age_days = (datetime.now(timezone.utc) - member.created_at).days

    risk_score = (
        "🚨 VERY HIGH RISK" if account_age_days < 3 else
        "⚠️ MEDIUM RISK" if account_age_days < 14 else
        "✅ LOW RISK"
    )

    alt_detection = (
        "❌ Possible Alt Account"
        if account_age_days < 7 else
        "✅ Account Looks Safe"
    )

    fields = [
        ("👤 User", f"{member.mention}\n`{member.id}`", False),
        ("📅 Account Created", f"<t:{int(member.created_at.timestamp())}:F>", False),
        ("💻 Account Age", format_account_age(member.created_at), False),
        ("📊 Risk Score", risk_score, False),
        ("🚨 Alt Detection", alt_detection, False),
        ("📥 Invite Used", inviter_display, False),
        ("🔗 Invite Code", invite_code, False),
        ("🕒 Joined At", f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", False),
    ]

    await send_big_embed(
        JOIN_LOG_CHANNEL_ID,
        title="🟢 Member Joined",
        description="A new member has joined the server.\nBelow is **all available information**.",
        color=discord.Color.green(),
        fields=fields,
        thumbnail=member.display_avatar.url,
        footer="The Lounge™ • Member Join Log"
    )

# ============================================================
# 👤 MEMBER LEAVE — HUGE AESTHETIC EMBED
# ============================================================

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    action = "🚪 Left Voluntarily"
    moderator = "N/A"

    try:
        async for entry in guild.audit_logs(limit=5):
            if entry.target and entry.target.id == member.id:
                if entry.action == discord.AuditLogAction.kick:
                    action = "👢 Kicked"
                    moderator = entry.user.mention
                    break
                if entry.action == discord.AuditLogAction.ban:
                    action = "🔨 Banned"
                    moderator = entry.user.mention
                    break
    except Exception:
        pass

    fields = [
        ("👤 User", f"{member.mention}\n`{member.id}`", False),
        ("⚡ Leave Type", action, False),
        ("🛡️ Moderator", moderator, False),
        ("📅 Account Created", f"<t:{int(member.created_at.timestamp())}:F>", False),
        ("💻 Account Age", format_account_age(member.created_at), False),
        ("🕒 Left At", f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", False),
    ]

    await send_big_embed(
        LEAVE_LOG_CHANNEL_ID,
        title="🔴 Member Left",
        description="A member has left the server.\nFull details are logged below.",
        color=discord.Color.red(),
        fields=fields,
        thumbnail=member.display_avatar.url,
        footer="The Lounge™ • Member Leave Log"
    )

# ============================================================
# 🏷️ ROLE ADD / REMOVE LOGS — BIG
# ============================================================

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    added_roles = [r for r in after.roles if r not in before.roles]
    removed_roles = [r for r in before.roles if r not in after.roles]

    if not added_roles and not removed_roles:
        return

    try:
        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
            if entry.target.id != after.id:
                continue

            for role in added_roles:
                await send_big_embed(
                    SYSTEM_LOG_CHANNEL_ID,
                    title="➕ Role Added",
                    description="A role has been **added** to a user.",
                    color=discord.Color.green(),
                    fields=[
                        ("👤 User", f"{after.mention}\n`{after.id}`", False),
                        ("🏷️ Role", role.mention, False),
                        ("🛡️ Added By", entry.user.mention, False),
                        ("🕒 Time", f"<t:{int(entry.created_at.timestamp())}:F>", False),
                    ],
                    thumbnail=after.display_avatar.url,
                    footer="The Lounge™ • Role Update Log"
                )

            for role in removed_roles:
                await send_big_embed(
                    SYSTEM_LOG_CHANNEL_ID,
                    title="➖ Role Removed",
                    description="A role has been **removed** from a user.",
                    color=discord.Color.red(),
                    fields=[
                        ("👤 User", f"{after.mention}\n`{after.id}`", False),
                        ("🏷️ Role", role.mention, False),
                        ("🛡️ Removed By", entry.user.mention, False),
                        ("🕒 Time", f"<t:{int(entry.created_at.timestamp())}:F>", False),
                    ],
                    thumbnail=after.display_avatar.url,
                    footer="The Lounge™ • Role Update Log"
                )
            break
    except Exception:
        pass

# ============================================================
# 🎙️ VOICE LOGS — JOIN / LEAVE / MOVE
# ============================================================

@bot.event
async def on_voice_state_update(member, before, after):
    now = f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>"

    if before.channel and not after.channel:
        if before.channel.id in TRACKED_VOICE_CHANNELS:
            await send_big_embed(
                VOICE_LOG_CHANNEL_ID,
                "🔴 Voice Channel Left",
                color=discord.Color.red(),
                fields=[
                    ("👤 User", f"{member.mention}\n`{member.id}`", False),
                    ("🎙️ Channel", before.channel.mention, False),
                    ("🕒 Time", now, False),
                ],
                thumbnail=member.display_avatar.url,
                footer="The Lounge™ • Voice Log"
            )

    if after.channel and not before.channel:
        if after.channel.id in TRACKED_VOICE_CHANNELS:
            await send_big_embed(
                VOICE_LOG_CHANNEL_ID,
                "🟢 Voice Channel Joined",
                color=discord.Color.green(),
                fields=[
                    ("👤 User", f"{member.mention}\n`{member.id}`", False),
                    ("🎙️ Channel", after.channel.mention, False),
                    ("🕒 Time", now, False),
                ],
                thumbnail=member.display_avatar.url,
                footer="The Lounge™ • Voice Log"
            )

# ============================================================
# 🤖 BOT STATUS — BIG LIVE EMBED
# ============================================================

@tasks.loop(seconds=15)
async def update_bot_status():
    global status_message

    channel = get_channel_safe(BOT_STATUS_CHANNEL_ID)
    if not channel:
        return

    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()

    embed = discord.Embed(
        title="🤖 Bot Status",
        description="Live system statistics for **The Lounge™ Bot**",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(name="👥 Members", value=str(len(channel.guild.members)), inline=True)
    embed.add_field(name="⏱️ Uptime", value=format_uptime(), inline=True)
    embed.add_field(name="⚡ CPU Usage", value=f"{cpu}%", inline=True)
    embed.add_field(
        name="💾 Memory Usage",
        value=f"{mem.percent}% ({mem.used // 1024 // 1024}MB / {mem.total // 1024 // 1024}MB)",
        inline=False
    )

    embed.set_footer(text="The Lounge™ • Live Bot Status")

    if status_message is None:
        status_message = await channel.send(embed=embed)
    else:
        await status_message.edit(embed=embed)

# ============================================================
# 🧨 END OF FILE 2
# ============================================================

bot.run(os.getenv("TOKEN"))
