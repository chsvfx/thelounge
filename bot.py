import os
import random
from datetime import datetime, timezone

import discord
import psutil
from discord import app_commands
from discord.ext import commands, tasks

# ===================== CONFIG =====================
GUILD_ID = 1351310078849847358
MEMBER_ROLE_ID = 1386784222781505619

VERIFY_LOG_CHANNEL_ID = 1462412645150752890
BOT_STATUS_CHANNEL_ID = 1463660427413033093
TICKET_CATEGORY_ID = 1462421944170446869

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


# ===================== HELPERS =====================
def get_channel_safe(cid: int) -> discord.TextChannel | None:
    channel = bot.get_channel(cid)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


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


async def build_big_embed(
    title: str,
    description: str,
    color: discord.Color,
    user: discord.abc.User | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"✨ {title}",
        description=f"## {description}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if user:
        embed.set_thumbnail(url=user.display_avatar.url)
    if bot.user:
        embed.set_footer(text=f"🤖 {bot.user.name} • Premium Automation")
    return embed


async def send_log_embed(
    channel_id: int,
    title: str,
    color: discord.Color,
    fields: list[tuple[str, str, bool]] | None = None,
    description: str | None = None,
    thumbnail: str | None = None,
) -> None:
    channel = get_channel_safe(channel_id)
    if channel is None:
        return

    embed = await build_big_embed(title, description or "Server event captured.", color)
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

    @discord.ui.button(
        label="✅ VERIFY NOW",
        style=discord.ButtonStyle.success,
        custom_id="persistent_verify_button",
    )
    async def verify_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.guild is None:
            return

        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                embed=await build_big_embed(
                    "Verification Error",
                    "❌ I couldn't find the member role. Please contact staff.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        if isinstance(interaction.user, discord.Member) and role in interaction.user.roles:
            await interaction.response.send_message(
                embed=await build_big_embed(
                    "Already Verified",
                    "ℹ️ You're already verified and ready to chat!",
                    discord.Color.orange(),
                    interaction.user,
                ),
                ephemeral=True,
            )
            return

        await interaction.user.add_roles(role)
        await interaction.response.send_message(
            embed=await build_big_embed(
                "Verification Complete",
                "🎉 Success! You now have full server access.",
                discord.Color.green(),
                interaction.user,
            ),
            ephemeral=True,
        )

        await send_log_embed(
            VERIFY_LOG_CHANNEL_ID,
            "Member Verified",
            discord.Color.green(),
            fields=[
                ("👤 User", f"{interaction.user.mention}\n`{interaction.user.id}`", False),
                ("📅 Account Age", format_account_age(interaction.user.created_at), True),
                ("🏷️ Role", role.mention, True),
                ("🕒 Time", f"<t:{int(datetime.now().timestamp())}:F>", False),
            ],
            description="✅ A user has passed verification.",
            thumbnail=interaction.user.display_avatar.url,
        )


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎟️ OPEN SUPPORT TICKET",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_ticket_button",
    )
    async def ticket_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name}".lower())

        if existing:
            await interaction.response.send_message(
                embed=await build_big_embed(
                    "Ticket Already Open",
                    f"⚠️ You already have one: {existing.mention}",
                    discord.Color.orange(),
                ),
                ephemeral=True,
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}".lower(),
            category=category,
            overwrites=overwrites,
        )

        await interaction.response.send_message(
            embed=await build_big_embed(
                "Ticket Created",
                f"✅ Your support ticket is ready: {ticket_channel.mention}",
                discord.Color.green(),
            ),
            ephemeral=True,
        )

        await ticket_channel.send(
            embed=await build_big_embed(
                "Support Ticket",
                f"👋 Hello {interaction.user.mention}! Please describe your issue in detail.",
                discord.Color.blurple(),
                interaction.user,
            )
        )


# ===================== COMMANDS =====================
@bot.tree.command(name="verify", description="Verify yourself to access all server channels.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def verify(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=await build_big_embed(
            "Server Verification",
            "✅ Click the button below to unlock the full server.",
            discord.Color.green(),
        ),
        view=VerifyView(),
        ephemeral=True,
    )


@bot.tree.command(name="ticket", description="Open a support ticket for staff help.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def ticket(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=await build_big_embed(
            "Support Center",
            "🎫 Need help? Open your private support ticket below.",
            discord.Color.orange(),
        ),
        view=TicketView(),
        ephemeral=True,
    )


@bot.tree.command(name="8ball", description="Ask the magic 8-ball a question.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def eightball(interaction: discord.Interaction, question: str):
    responses = [
        "✅ Yes",
        "❌ No",
        "🔮 Ask again later",
        "💯 Absolutely",
        "🤔 Unlikely",
        "🌟 Outlook good",
        "🌀 Cannot predict now",
    ]
    response = random.choice(responses)
    await interaction.response.send_message(
        embed=await build_big_embed(
            "Magic 8 Ball",
            f"🎱 **Question:** {question}\n\n### **Answer:** {response}",
            discord.Color.purple(),
        )
    )


@bot.tree.command(name="dice", description="Roll a dice with custom sides.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def dice(interaction: discord.Interaction, sides: app_commands.Range[int, 2, 100] = 6):
    roll = random.randint(1, sides)
    await interaction.response.send_message(
        embed=await build_big_embed(
            "Dice Roll",
            f"🎲 You rolled a **d{sides}**\n\n## Result: **{roll}**",
            discord.Color.gold(),
        )
    )


@bot.tree.command(name="coinflip", description="Flip a coin.")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["🪙 Heads", "🪙 Tails"])
    await interaction.response.send_message(
        embed=await build_big_embed(
            "Coin Flip",
            f"## Result: {result}",
            discord.Color.light_gray(),
        )
    )


@bot.tree.command(name="rps", description="Play Rock Paper Scissors.")
@app_commands.describe(choice="Choose: rock, paper, or scissors")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def rps(interaction: discord.Interaction, choice: str):
    normalized_choice = choice.lower().strip()
    options = ["rock", "paper", "scissors"]

    if normalized_choice not in options:
        await interaction.response.send_message(
            embed=await build_big_embed(
                "Invalid Choice",
                "❌ Use one of these: **rock**, **paper**, **scissors**.",
                discord.Color.red(),
            ),
            ephemeral=True,
        )
        return

    bot_choice = random.choice(options)
    if normalized_choice == bot_choice:
        result = "🤝 It's a tie!"
    elif (normalized_choice, bot_choice) in [
        ("rock", "scissors"),
        ("scissors", "paper"),
        ("paper", "rock"),
    ]:
        result = "🎉 You win!"
    else:
        result = "😈 Bot wins!"

    await interaction.response.send_message(
        embed=await build_big_embed(
            "Rock • Paper • Scissors",
            (
                f"🧍 **You:** {normalized_choice.title()}\n"
                f"🤖 **Bot:** {bot_choice.title()}\n\n"
                f"## {result}"
            ),
            discord.Color.blurple(),
        )
    )


# ===================== EVENTS =====================
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    bot.add_view(TicketView())
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

    if not update_status.is_running():
        update_status.start()

    print(f"🟢 Logged in as {bot.user}")


@tasks.loop(seconds=10)
async def update_status():
    global status_message

    channel = get_channel_safe(BOT_STATUS_CHANNEL_ID)
    guild = bot.get_guild(GUILD_ID)
    if channel is None or guild is None:
        return

    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    uptime = format_uptime()
    total = len(guild.members)
    bots = len([member for member in guild.members if member.bot])

    embed = discord.Embed(
        title="📊 BOT STATUS DASHBOARD",
        description="## Real-time health, uptime, and member analytics.",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="👥 Members", value=f"**{total - bots}**", inline=True)
    embed.add_field(name="🤖 Bots", value=f"**{bots}**", inline=True)
    embed.add_field(name="⚙️ CPU", value=f"**{cpu}%**", inline=True)
    embed.add_field(name="💾 Memory", value=f"**{mem.percent}% Used**", inline=True)
    embed.add_field(name="🕒 Uptime", value=f"**{uptime}**", inline=False)
    if bot.user:
        embed.set_footer(text=f"🤖 {bot.user.name} • System Monitor")

    try:
        if status_message is None:
            status_message = await channel.send(embed=embed)
        else:
            await status_message.edit(embed=embed)
    except discord.HTTPException:
        status_message = None


# ===================== RUN BOT =====================
bot.run(os.getenv("TOKEN"))
