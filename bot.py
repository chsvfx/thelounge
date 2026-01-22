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

PROTECTED_ROLES = ["Admin", "Owner", "Dev", "Developer"]  # Roles that cannot be tagged

# ===================== INTENTS =====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===================== MEMORY =====================
RECENT_LEAVES = {}
START_TIME = datetime.now(timezone.utc)
status_message: discord.Message | None = None
invite_tracker = {}  # Track invites

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
        await interaction.response.send_message("🎉 You are now verified and have access to the server!", ephemeral=True)
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

# ===================== EVENTS =====================
@bot.event
async def on_ready():
    bot.add_view(VerifyView())  # Persistent verify button
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    update_status.start()
    # Fetch invites for tracking
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

# ===================== PREVENT TAGGING STAFF =====================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Check if any protected role is mentioned
    tagged_roles = [role for role in message.role_mentions if role.name in PROTECTED_ROLES]
    if tagged_roles:
        try:
            await message.add_reaction("⚠️")
            await message.reply("⚠️ Don’t tag higher-ups, please!", mention_author=True)
        except discord.Forbidden:
            print("❌ Missing permission to react or reply in channel")
    await bot.process_commands(message)

# ===================== ROLE ADD/REMOVE LOGS =====================
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    added_roles = [role for role in after.roles if role not in before.roles]
    removed_roles = [role for role in before.roles if role not in after.roles]

    async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
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
                    ("⏰ Time", f"<t:{int(entry.created_at.timestamp())}:F>", False)
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
                    ("⏰ Time", f"<t:{int(entry.created_at.timestamp())}:F>", False)
                ]
            )
        break

# ===================== BOT STATUS =====================
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
        print("❌ Missing permissions to update status")

# ===================== RUN BOT =====================
bot.run(os.getenv("TOKEN"))
