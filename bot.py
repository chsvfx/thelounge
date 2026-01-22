import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
import psutil
import traceback
import math

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
invite_tracker = {}  # track invites
tickets_messages = {}  # store ticket messages per guild

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

def calculate_risk(member: discord.Member) -> str:
    """Returns risk score based on account age and server join history."""
    delta_days = (datetime.now(timezone.utc) - member.created_at).days
    if delta_days < 7:
        return "⚠️ High Risk (New Account)"
    elif delta_days < 30:
        return "⚠️ Medium Risk"
    return "✅ Low Risk"

def is_alt(member: discord.Member) -> str:
    """Returns alt detection info"""
    return "🚨 Possible Alt" if (datetime.now(timezone.utc) - member.created_at).days < 7 else "✅ Legit Account"

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

# ===================== VIEWS =====================
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, custom_id="persistent_verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.bot:
            return
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if not role:
            await interaction.response.send_message("❌ Member role not found.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("ℹ️ Already verified.", ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="Server verification")
        await interaction.response.send_message("✅ You are now verified!", ephemeral=True)
        # log
        await send_embed(
            VERIFY_LOG_CHANNEL_ID,
            "✅ Member Verified",
            color=discord.Color.green(),
            fields=[
                ("👤 User", f"{interaction.user} (`{interaction.user.id}`)", False),
                ("📅 Account Age", format_account_age(interaction.user.created_at), False),
                ("🏷️ Role", role.mention, False)
            ],
            thumbnail=interaction.user.display_avatar.url
        )

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.blurple, custom_id="persistent_ticket_button")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ALLOWED_USER_IDS:
            await interaction.response.send_message("❌ You cannot use this command.", ephemeral=True)
            return
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not category:
            await interaction.response.send_message("❌ Ticket category not found.", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True)
        }
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", category=category, overwrites=overwrites)
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)
        await channel.send(f"👋 {interaction.user.mention}, welcome to your ticket!")
        tickets_messages[channel.id] = interaction.user.id

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="persistent_close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = interaction.channel.id
        if channel_id not in tickets_messages:
            await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
            return
        await interaction.response.send_message("🗑️ Ticket will be closed in 5s.", ephemeral=True)
        await asyncio.sleep(5)
        await interaction.channel.delete()
        del tickets_messages[channel_id]

# ===================== EVENTS =====================
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    # fetch invites
    guild = bot.get_guild(GUILD_ID)
    if guild:
        for inv in await guild.invites():
            invite_tracker[inv.code] = inv.uses
    update_status.start()
    print(f"🟢 Logged in as {bot.user}")

@bot.event
async def on_error(event, *args, **kwargs):
    err = traceback.format_exc()
    await send_embed(SYSTEM_LOG_CHANNEL_ID, "⚠️ System Error", color=discord.Color.red(), fields=[("", f"```{err}```", False)])
    print(err)

# ===================== JOIN / LEAVE LOGGING =====================
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    inviter = "Unknown"
    try:
        invites_before = invite_tracker.copy()
        current_invites = await guild.invites()
        for inv in current_invites:
            uses_before = invites_before.get(inv.code, 0)
            if inv.uses > uses_before:
                inviter = inv.inviter.mention
                invite_tracker[inv.code] = inv.uses
                break
    except Exception:
        pass

    embed = discord.Embed(title="🟢 Member Joined", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{member} (`{member.id}`)", inline=False)
    embed.add_field(name="📅 Account Age", value=format_account_age(member.created_at), inline=True)
    embed.add_field(name="📥 Invite Used", value=inviter, inline=True)
    embed.add_field(name="📊 Risk Score", value=calculate_risk(member), inline=True)
    embed.add_field(name="🚨 Alt Detection", value=is_alt(member), inline=True)
    embed.add_field(name="🕒 Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="🤖 Bot?", value="Yes" if member.bot else "No", inline=True)
    await send_embed(JOIN_LOG_CHANNEL_ID, "🟢 Member Joined", fields=[(f.name, f.value, f.inline) for f in embed.fields], thumbnail=member.display_avatar.url)

@bot.event
async def on_member_remove(member: discord.Member):
    reason = "Left"
    mod = None
    guild = member.guild
    # check kick
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            reason = "Kicked"
            mod = entry.user.mention
            break
    # check ban
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
        if entry.target.id == member.id:
            reason = "Banned"
            mod = entry.user.mention
            break

    embed = discord.Embed(title="🔴 Member Left", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{member} (`{member.id}`)", inline=False)
    embed.add_field(name="⚡ Left By", value=mod if mod else reason, inline=False)
    embed.add_field(name="📅 Account Age", value=format_account_age(member.created_at), inline=True)
    embed.add_field(name="📊 Risk Score", value=calculate_risk(member), inline=True)
    embed.add_field(name="🚨 Alt Detection", value=is_alt(member), inline=True)
    embed.add_field(name="🕒 Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="🤖 Bot?", value="Yes" if member.bot else "No", inline=True)
    await send_embed(LEAVE_LOG_CHANNEL_ID, "🔴 Member Left", fields=[(f.name, f.value, f.inline) for f in embed.fields], thumbnail=member.display_avatar.url)

# ===================== VOICE LOGGING =====================
@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        if before.channel and before.channel.id in TRACKED_VOICE_CHANNELS:
            await send_embed(VOICE_LOG_CHANNEL_ID, "🔊 Voice Left",
                             fields=[("👤 User", f"{member} (`{member.id}`)", False),
                                     ("📁 Channel", f"{before.channel.name}", True),
                                     ("🕒 Time", f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", True)])
        if after.channel and after.channel.id in TRACKED_VOICE_CHANNELS:
            await send_embed(VOICE_LOG_CHANNEL_ID, "🔊 Voice Joined",
                             fields=[("👤 User", f"{member} (`{member.id}`)", False),
                                     ("📁 Channel", f"{after.channel.name}", True),
                                     ("🕒 Time", f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", True)])

# ===================== BOT STATUS =====================
@tasks.loop(seconds=30)
async def update_status():
    global status_message
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    total_members = sum(1 for m in guild.members if not m.bot)
    total_bots = sum(1 for m in guild.members if m.bot)
    cpu = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    mem_used_gb = memory.used / (1024**2)
    mem_total_gb = memory.total / (1024**2)

    embed = discord.Embed(title="🤖 Bot Status", color=discord.Color.blurple(),
                          timestamp=datetime.now(timezone.utc))
    embed.add_field(name="👥 Members", value=f"{total_members}", inline=True)
    embed.add_field(name="🤖 Bots", value=f"{total_bots}", inline=True)
    embed.add_field(name="⏱️ Uptime", value=format_uptime(), inline=True)
    embed.add_field(name="⚡ CPU Usage", value=f"{cpu}%", inline=True)
    embed.add_field(name="💾 Memory Usage", value=f"{memory.percent}% ({mem_used_gb:.0f}MB / {mem_total_gb:.0f}MB)", inline=True)
    embed.set_footer(text=f"{guild.name} • Status Update")
    channel = get_channel_safe(BOT_STATUS_CHANNEL_ID)
    if channel:
        try:
            if status_message is None:
                status_message = await channel.send(embed=embed)
            else:
                await status_message.edit(embed=embed)
        except Exception as e:
            print(f"❌ Status update failed: {e}")

# ===================== COMMANDS =====================
@bot.tree.command(name="rules", description="View the server rules")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def rules(interaction: discord.Interaction):
    rules_text = (
        "1️⃣ Be respectful\n2️⃣ No discrimination\n3️⃣ No spam\n4️⃣ No join/leave abuse\n"
        "5️⃣ Stay on topic\n6️⃣ No impersonation\n7️⃣ No self-promo\n8️⃣ Appropriate content\n9️⃣ No spoilers"
    )
    embed = discord.Embed(title="📜 Server Rules", description=rules_text, color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="verify", description="Verify yourself")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    embed = discord.Embed(title="🎉 Verify to Join",
                          description="Click the button below to receive the **Member** role.",
                          color=discord.Color.green())
    await interaction.response.send_message(embed=embed, view=VerifyView())

# ===================== RUN BOT =====================
bot.run(os.getenv("TOKEN"))
