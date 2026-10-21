"""/botinfo: uptime, ping, version and latest changes."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@bot.tree.command(name="botinfo", description="Bot stats: uptime, ping, version and latest changes")
@app_commands.guild_only()
async def botinfo(interaction: discord.Interaction, public: bool = False):
    lat = bot.latency
    ping = round(lat * 1000) if lat == lat and lat != float("inf") else None   # NaN right after startup
    ping_dot = "⚪" if ping is None else "🟢" if ping < 150 else "🟡" if ping < 400 else "🔴"
    members = store.members()
    latest = store.latest_check_id()
    e = discord.Embed(title="🤖 [gg] Bot", color=reports.BLURPLE,
                      description=f"-# Online since <t:{int(STARTED_AT.timestamp())}:f>")
    e.add_field(name="Version", value=f"v{RUNNING_VERSION}", inline=True)
    e.add_field(name="Uptime", value=nice_duration((dt.datetime.now(dt.timezone.utc) - STARTED_AT).total_seconds()),
                inline=True)
    e.add_field(name="Ping", value=f"{ping_dot} {ping} ms" if ping is not None else "⚪ Measuring…", inline=True)
    e.add_field(name="Roster", value=f"{len(members)} members", inline=True)
    e.add_field(name="Last Coin Check", value=store.check_label(latest) if latest else "None yet", inline=True)
    e.add_field(name="Memory", value=memory_mb(), inline=True)
    news = changes_since("0", RUNNING_VERSION)[:3]
    if news:
        e.add_field(name="Latest Changes", value="\n".join(f"**v{v}** · {t}" for v, t in news)[:1024], inline=False)
    if bot.user and bot.user.display_avatar:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    e.set_footer(text=f"[gg] bot v{RUNNING_VERSION}")
    await interaction.response.send_message(embed=e, ephemeral=not public)
