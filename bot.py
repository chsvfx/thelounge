import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os
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
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

START_TIME = datetime.now(timezone.utc)
status_message: discord.Message | None = None

# ===================== HELPERS =====================
def is_allowed(interaction: discord.Interaction) -> bool:
    return interaction.user.id in ALLOWED_USER_IDS

def format_uptime() -> str:
    delta = datetime.now(timezone.utc) - START_TIME
    h, r = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m}m {s}s"

# ===================== VERIFY VIEW =====================
class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="persistent_verify_button"
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if role in interaction.user.roles:
            await interaction.response.send_message("ℹ️ You are already verified.", ephemeral=True)
            return

        await interaction.user.add_roles(role)
        await interaction.response.send_message("🎉 You are now verified!", ephemeral=True)

# ===================== TICKET SYSTEM =====================
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Open Ticket", emoji="🎫", style=discord.ButtonStyle.primary)
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)

        for ch in category.text_channels:
            if ch.topic == str(interaction.user.id):
                await interaction.response.send_message(
                    "❌ You already have an open ticket.", ephemeral=True
                )
                return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True)
        }

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            topic=str(interaction.user.id),
            overwrites=overwrites
        )

        embed = discord.Embed(
            title="🎫 Ticket Created",
            description="A staff member will assist you shortly.\n\n🔒 **Click the button below to close this ticket.**",
            color=discord.Color.green()
        )

        await channel.send(embed=embed, view=CloseTicketView())
        await interaction.response.send_message("✅ Ticket created!", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Closing ticket...", ephemeral=True)
        await interaction.channel.delete()

# ===================== COMMANDS =====================
@bot.tree.command(name="ticket", description="Send the ticket panel")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction):
    if not is_allowed(interaction):
        await interaction.response.send_message("❌ You cannot use this command.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎫 Support Tickets",
        description="Click the button below to open a support ticket.",
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(embed=embed, view=TicketView())

# ===================== VOICE LOGS =====================
@bot.event
async def on_voice_state_update(member, before, after):
    def tracked(ch):
        return ch and ch.id in TRACKED_VOICE_CHANNELS

    if not tracked(before.channel) and not tracked(after.channel):
        return

    channel = bot.get_channel(VOICE_LOG_CHANNEL_ID)
    if not channel:
        return

    if before.channel is None:
        action = "🔊 Joined"
        target = after.channel.name
    elif after.channel is None:
        action = "🔇 Left"
        target = before.channel.name
    else:
        action = "🔁 Moved"
        target = f"{before.channel.name} → {after.channel.name}"

    embed = discord.Embed(
        title="🎙️ Voice Activity",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 User", value=member.mention, inline=False)
    embed.add_field(name="⚡ Action", value=action, inline=False)
    embed.add_field(name="🔊 Channel", value=target, inline=False)

    await channel.send(embed=embed)

# ===================== BOT STATUS (BIG & CLEAN) =====================
@tasks.loop(seconds=0)
async def update_status():
    global status_message
    channel = bot.get_channel(BOT_STATUS_CHANNEL_ID)
    if not channel:
        return

    guild = bot.get_guild(GUILD_ID)
    members = len([m for m in guild.members if not m.bot])
    bots = len([m for m in guild.members if m.bot])

    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    used_mb = mem.used // (1024 * 1024)
    total_mb = mem.total // (1024 * 1024)

    embed = discord.Embed(
        title="🤖 Bot Status",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(name="👥 Members", value=f"**{members}**", inline=True)
    embed.add_field(name="🤖 Bots", value=f"**{bots}**", inline=True)
    embed.add_field(name="⏱️ Uptime", value=f"**{format_uptime()}**", inline=False)
    embed.add_field(name="⚡ CPU Usage", value=f"**{cpu}%**", inline=True)
    embed.add_field(
        name="💾 Memory Usage",
        value=f"**{mem.percent}%** ({used_mb}MB / {total_mb}MB)",
        inline=False
    )

    embed.set_footer(text=f"{bot.user} • Status Update")

    try:
        if status_message is None:
            status_message = await channel.send(embed=embed)
        else:
            await status_message.edit(embed=embed)
    except:
        pass

# ===================== READY =====================
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    update_status.start()
    print(f"🟢 Logged in as {bot.user}")

# ===================== RUN =====================
bot.run(os.getenv("TOKEN"))
