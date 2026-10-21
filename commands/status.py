"""/status: the text under the bot's name."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

@bot.tree.command(name="status", description="Change the text under the bot's name")
@admin_only
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
@app_commands.describe(text="New status, e.g. SIGNUPS OPEN!! (leave empty to clear it)")
async def status_command(interaction: discord.Interaction, text: Optional[app_commands.Range[str, 1, 128]] = None):
    store.set_setting("status", text or "")
    await bot.change_presence(status=discord.Status.online, activity=status_activity())
    await interaction.response.send_message(embed=simple(
        f"Status is now **{discord.utils.escape_markdown(text)}**." if text else "Status cleared.",
        GREEN, "🟢 Status Updated"), ephemeral=True)
