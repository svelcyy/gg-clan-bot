"""/restart: restart the bot from Discord."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@bot.tree.command(name="restart", description="Restart the bot (no website needed)")
@admin_only
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def restart(interaction: discord.Interaction, public: bool = False):
    up = (dt.datetime.now(dt.timezone.utc) - STARTED_AT).total_seconds()
    e = update_embed("🔄 Restarting", "The bot will be back in a few seconds.", reports.BLURPLE, fields=[
        ("Version", f"v{RUNNING_VERSION}", True),
        ("Was Online For", nice_duration(up), True),
    ])
    await interaction.response.send_message(embed=e, ephemeral=not public)
    log.info("Restart requested by %s", interaction.user)
    await asyncio.sleep(2)
    os.execv(sys.executable, [sys.executable, str(HERE / "main.py")])
