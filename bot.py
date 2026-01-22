import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
import traceback
import psutil
import asyncio

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

PROTECTED_ROLE_IDS = [1351310078887858299, 1386779868532047982]  # example protected IDs

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
invite_tracker = {}
tickets_active = {}  # user_id: channel_id

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

def member_risk_score(member: discord.Member) -> str:
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    if age_days < 7:
        return "🔥 High (new account)"
    elif age_days < 30:
        return "⚠️ Medium"
    else:
        return "✅ Low"

def get_invite_used(member: discord.Member) -> str:
    # basic placeholder (invite tracking requires more code)
    return "📥 Unknown"

# ===================== VIEWS =====================
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Verify to Get Member", style=discord.ButtonStyle.success, custom_id="persistent_verify_button")
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
        await send_embed(
            VERIFY_LOG_CHANNEL_ID,
            "✅ Member Verified",
            color=discord.Color.green(),
            fields=[
                ("👤 User", f"{interaction.user.mention}\n`{interaction.user.id}`", False),
                ("📅 Account Age", format_account_age(interaction.user.created_at), False),
                ("🏷️ Role", role.mention, False),
                ("📥 Invite Used", get_invite_used(interaction.user), False),
                ("📊 Risk Score", member_risk_score(interaction.user), False)
            ],
            thumbnail=interaction.user.display_avatar.url
        )

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.primary, custom_id="persistent_ticket_button")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in tickets_active:
            await interaction.response.send_message("❌ You already have an open ticket.", ephemeral=True)
            return
        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for role_id in PROTECTED_ROLE_IDS:
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}", category=category, overwrites=overwrites
        )
        tickets_active[interaction.user.id] = channel.id
        embed = discord.Embed(
            title="🎫 Ticket Created",
            description=f"Hello {interaction.user.mention}, please describe your issue here.\nAdmins will assist you shortly.",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="Ticket System")
        await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

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

@bot.event
async def on_error(event, *args, **kwargs):
    err = traceback.format_exc()
    await send_embed(SYSTEM_LOG_CHANNEL_ID, "⚠️ System Error", color=discord.Color.red(),
                     fields=[("", f"```{err}```", False)])
    print(err)

# ===================== MEMBER LOGS =====================
@bot.event
async def on_member_join(member: discord.Member):
    inviter_name = "Unknown"
    # invite tracking
    try:
        invites_before = invite_tracker.copy()
        current_invites = await member.guild.invites()
        for inv in current_invites:
            uses_before = invites_before.get(inv.code, 0)
            if inv.uses > uses_before:
                inviter_name = inv.inviter.mention
                invite_tracker[inv.code] = inv.uses
                break
    except Exception:
        pass
    embed = discord.Embed(
        title="🟢 Member Joined",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=False)
    embed.add_field(name="📝 Username#Discrim", value=f"{member}", inline=False)
    embed.add_field(name="📅 Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
    embed.add_field(name="📊 Risk Score", value=member_risk_score(member), inline=False)
    embed.add_field(name="📥 Invite Used", value=inviter_name, inline=False)
    embed.add_field(name="🕒 Join Date", value=f"<t:{int(member.joined_at.timestamp())}:F>" if member.joined_at else "Unknown", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    await send_embed(JOIN_LOG_CHANNEL_ID, "🟢 Member Joined", color=discord.Color.green(), thumbnail=member.display_avatar.url,
                     fields=[(f.name, f.value, f.inline) for f in embed.fields])

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    reason = "Left voluntarily"
    mod = None
    # Check kick
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            reason = "Kicked"
            mod = entry.user.mention
            break
    # Check ban
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
    embed.add_field(name="👤 User", value=f"{member.mention}\n`{member.id}`", inline=False)
    embed.add_field(name="📝 Username#Discrim", value=f"{member}", inline=False)
    embed.add_field(name="⚡ Left By", value=mod if mod else reason, inline=False)
    embed.add_field(name="📅 Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=False)
    embed.add_field(name="📊 Risk Score", value=member_risk_score(member), inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    await send_embed(LEAVE_LOG_CHANNEL_ID, "🔴 Member Left", color=discord.Color.red(), thumbnail=member.display_avatar.url,
                     fields=[(f.name, f.value, f.inline) for f in embed.fields])

# ===================== ROLE LOGS =====================
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild
    added_roles = [role for role in after.roles if role not in before.roles]
    removed_roles = [role for role in before.roles if role not in after.roles]

    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
        if entry.target.id != after.id:
            continue
        timestamp = f"<t:{int(entry.created_at.timestamp())}:F>"
        for role in added_roles:
            await send_embed(
                SYSTEM_LOG_CHANNEL_ID,
                "➕ Role Added",
                color=discord.Color.green(),
                fields=[
                    ("👤 User", f"{after.mention}\n`{after.id}`", False),
                    ("🏷️ Role", role.mention, False),
                    ("🛡️ Added By", entry.user.mention, False),
                    ("🕒 Time", timestamp, False)
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
                    ("🕒 Time", timestamp, False)
                ]
            )
        break

# ===================== BOT STATUS =====================
@tasks.loop(seconds=15)
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

# ===================== COMMANDS =====================
@bot.tree.command(name="rules", description="View the server rules")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def rules(interaction: discord.Interaction):
    rules_text = (
        "1️⃣ Be respectful\n2️⃣ No discrimination\n3️⃣ No spam\n3️⃣ No join/leave abuse\n"
        "5️⃣ Stay on topic\n6️⃣ No impersonation\n7️⃣ No self-promo\n8️⃣ Appropriate content\n9️⃣ No spoilers"
    )
    embed = discord.Embed(title="📜 Server Rules", description=rules_text, color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="verify", description="Verify yourself")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="✅ Verify to Get Member Role",
        description="Click the button below to verify and receive the **Member** role.\n\n"
                    "💡 **Note:** Only verified members can chat and access channels.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, view=VerifyView())

@bot.tree.command(name="message", description="Send a custom message via bot (admin only)")
@app_commands.describe(content="Message to send")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def message(interaction: discord.Interaction, content: str):
    if interaction.user.id not in ALLOWED_USER_IDS:
        await interaction.response.send_message("❌ You cannot use this command.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Sent message:\n{content}")
    await interaction.channel.send(content)

# ===================== RUN BOT =====================
bot.run(os.getenv("TOKEN"))
