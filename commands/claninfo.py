"""/claninfo, and the reply when someone pings the bot."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

CLAN_STATS_IMAGE = HERE / "clan_stats.png"   # screenshot of the clan's in-game upgrades, shown at the bottom


def next_signups() -> dt.datetime:
    """Midnight on the 1st of next month (or today, if it's the 1st), in the clan's time zone."""
    now = dt.datetime.now(reminder_tz())
    if now.day == 1:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    first = (now.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return first.replace(hour=0, minute=0, second=0, microsecond=0)


def claninfo_message() -> tuple[discord.Embed, discord.File | None]:
    opens = int(next_signups().timestamp())
    members = [m for m in store.members() if m.roblox_username.lower() != "ggclanholder"]
    staff = sum(m.rank != "Member" for m in members)
    e = discord.Embed(title="🏰 About the [gg] Clan", color=reports.BLURPLE, description=(
        "Welcome to **[gg]**, a Roblox Bedwars clan owned by **chase**, an Anti-Cheat Manager. "
        "We're an active group that plays together, competes in clan wars and keeps building the clan up every month."))
    e.add_field(name="Next Signups (Estimate)",
                value=f"<t:{opens}:D> · <t:{opens}:R>\n-# Signups usually open on the 1st of each month.", inline=False)
    e.add_field(name="Requirements to Join", value=(
        "• Active in game: **Gold rank** or higher and **level 50+**\n"
        "• Good account standing: **no bans** on your account\n"
        "• Willing to take part in **clan events**, such as clan wars"), inline=False)
    e.add_field(name="Staying in the Clan", value=(
        f"Every member contributes at least **{store.get_minimum():,} coins** to the clan each month. "
        "Coin checks happen at the start of every month."), inline=False)
    e.add_field(name="Members", value=f"{len(members)}", inline=True)
    e.add_field(name="Staff", value=f"{staff}", inline=True)
    e.add_field(name="Clan Upgrades", value="-# Our current upgrades and clan bank:", inline=False)
    guild = bot.get_guild(GUILD_ID)
    if guild and guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    e.set_footer(text="Questions? Ask a staff member · /leaderboard shows everyone's coins")
    file = None
    if CLAN_STATS_IMAGE.exists():
        file = discord.File(CLAN_STATS_IMAGE, filename="clan_stats.png")
        e.set_image(url="attachment://clan_stats.png")
    return e, file


@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@bot.tree.command(name="claninfo", description="About the clan: requirements to join and when signups open")
@app_commands.guild_only()
async def claninfo(interaction: discord.Interaction, public: bool = False):
    embed, file = claninfo_message()
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(embed=embed, ephemeral=not public, **kwargs)


_mention_cooldown: dict[int, float] = {}


@bot.event
async def on_message(message: discord.Message):
    """Answer people who ping the bot (not replies to it, and at most once a minute per person)."""
    if message.author.bot or not message.guild or bot.user is None:
        return
    if f"<@{bot.user.id}>" not in message.content and f"<@!{bot.user.id}>" not in message.content:
        return
    now = asyncio.get_running_loop().time()
    if now - _mention_cooldown.get(message.author.id, -999) < 60:
        return
    _mention_cooldown[message.author.id] = now
    await message.reply("Hey there! Have any questions about the clan? Use my `/claninfo` command to see "
                        "everything there is to know about our amazing clan, as well as when the next signups are!",
                        mention_author=False, allowed_mentions=discord.AllowedMentions.none())
