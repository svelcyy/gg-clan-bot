"""/reminders, the monthly coin check reminder and the restart reminder."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

def ping_target(guild: Optional[discord.Guild]) -> tuple[str, discord.AllowedMentions]:
    """The mention text for REMINDER_PING, and permission to ping only that one user or role."""
    if not REMINDER_PING or not REMINDER_PING.isdigit():
        return "", discord.AllowedMentions.none()
    role = guild.get_role(int(REMINDER_PING)) if guild else None
    if role:
        return role.mention, discord.AllowedMentions(everyone=False, users=False, roles=[role])
    return f"<@{REMINDER_PING}>", discord.AllowedMentions(everyone=False, roles=False, users=[discord.Object(int(REMINDER_PING))])


async def send_reminder(embed: discord.Embed) -> bool:
    channel = bot.get_channel(int(REMINDER_CHANNEL_ID)) if REMINDER_CHANNEL_ID else None
    if channel is None:
        log.warning("REMINDER_CHANNEL_ID %s not found", REMINDER_CHANNEL_ID)
        return False
    text, allowed = ping_target(channel.guild)
    await channel.send(content=text or None, embed=embed, allowed_mentions=allowed)
    return True


def coin_reminder_embed() -> discord.Embed:
    now = dt.datetime.now(reminder_tz())
    last = store.latest_check_id()
    e = discord.Embed(title="🪙 Coin Check Time!", color=reports.AMBER,
                      description=f"It's the {now:%B} coin check. Grab everyone's **Contribution** numbers in game, "
                                  f"then run `/coins import label:{now:%b %Y}`.")
    e.add_field(name="Last Coin Check", value=store.check_label(last) if last else "None yet", inline=True)
    e.add_field(name="Minimum", value=f"{store.get_minimum():,} coins", inline=True)
    e.add_field(name="On the Roster", value=str(len(store.members())), inline=True)
    return e


def restart_reminder_embed() -> discord.Embed:
    up = dt.datetime.now(dt.timezone.utc) - STARTED_AT
    e = discord.Embed(title="🔄 Restart Needed Soon", color=0xE67E22,
                      description="The host stops the bot after "
                                  f"{RESTART_REMINDER_DAYS:g} days. Open the Wispbyte panel and press **Restart** "
                                  "(or renew the server if it asks) to keep the bot online. `/restart` may also work.")
    e.add_field(name="Online For", value=nice_duration(up.total_seconds()), inline=True)
    e.add_field(name="Stops In About", value=nice_duration(max(0, RESTART_REMINDER_DAYS * 86400 - up.total_seconds())), inline=True)
    return e


@tasks.loop(time=dt.time(hour=REMINDER_HOUR, tzinfo=reminder_tz()))
async def coin_reminder():
    if dt.datetime.now(reminder_tz()).day == COIN_REMINDER_DAY:
        await send_reminder(coin_reminder_embed())


_restart_reminded = False


@tasks.loop(minutes=30)
async def restart_reminder():
    global _restart_reminded
    up = (dt.datetime.now(dt.timezone.utc) - STARTED_AT).total_seconds()
    if not _restart_reminded and up >= (RESTART_REMINDER_DAYS * 24 - RESTART_REMINDER_HOURS_BEFORE) * 3600:
        _restart_reminded = await send_reminder(restart_reminder_embed())


coin_reminder.before_loop(wait_ready)
restart_reminder.before_loop(wait_ready)


@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@bot.tree.command(name="reminders", description="See the reminder settings and send a test ping")
@admin_only
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def reminders(interaction: discord.Interaction, public: bool = False):
    await interaction.response.defer(ephemeral=not public)
    tz = reminder_tz()
    now = dt.datetime.now(tz)
    nxt = now.replace(day=COIN_REMINDER_DAY, hour=REMINDER_HOUR, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt = (nxt.replace(day=1) + dt.timedelta(days=32)).replace(day=COIN_REMINDER_DAY)
    text, _ = ping_target(interaction.guild)
    restart = (f"{RESTART_REMINDER_HOURS_BEFORE:g} hours before {RESTART_REMINDER_DAYS:g} days online"
               if RESTART_REMINDER_DAYS > 0 else "Off · Not needed, Wispbyte doesn't stop the bot")
    e = update_embed("⏰ Reminders", "", reports.BLURPLE, fields=[
        ("Channel", f"<#{REMINDER_CHANNEL_ID}>" if REMINDER_CHANNEL_ID else "Not set (REMINDER_CHANNEL_ID)", True),
        ("Pings", text or "Nobody (set REMINDER_PING)", True),
        ("Coin Check Reminder", f"<t:{int(nxt.timestamp())}:F>" if COIN_REMINDER else "Off", True),
        ("Restart Reminder", restart, False),
    ])
    sent = await send_reminder(discord.Embed(title="🧪 Test Reminder", color=reports.BLURPLE,
                                             description="Reminders will show up here like this.")) \
        if REMINDER_CHANNEL_ID else False
    e.set_footer(text="Test ping sent" if sent else "Couldn't send a test (check the channel setting)")
    await interaction.followup.send(embed=e, ephemeral=not public)


BACKGROUND_TASKS.append((coin_reminder, lambda: bool(REMINDER_CHANNEL_ID and COIN_REMINDER)))
BACKGROUND_TASKS.append((restart_reminder, lambda: bool(REMINDER_CHANNEL_ID and RESTART_REMINDER_DAYS > 0)))
