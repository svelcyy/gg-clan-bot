"""/update: download the newest version and restart."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@bot.tree.command(name="update", description="Download the newest bot version and restart")
@admin_only
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def update(interaction: discord.Interaction, public: bool = False):
    await interaction.response.defer(ephemeral=not public, thinking=True)   # only you see this
    try:
        result = await asyncio.to_thread(updater.sync, GITHUB_REPO, GITHUB_BRANCH, GITHUB_TOKEN)
    except Exception as e:
        log.exception("Update failed")
        await interaction.followup.send(embed=simple(
            f"Couldn't download the update, so nothing changed and the bot keeps running.\n`{e}`",
            RED, "⚠️ Update Failed"), ephemeral=not public)
        return
    new_version = read_version()
    if not result.changed:
        await interaction.followup.send(embed=simple(
            f"You're on the newest version, **v{RUNNING_VERSION}**.", GREEN, "✅ Up to Date"), ephemeral=not public)
        return
    e = discord.Embed(title=f"⬆️ Updating to v{new_version}", color=GREEN,
                      description="Restarting now. Back in a few seconds.")
    e.add_field(name="Current", value=f"v{RUNNING_VERSION}", inline=True)
    e.add_field(name="New", value=f"v{new_version}", inline=True)
    news = changes_since(RUNNING_VERSION, new_version)
    if news:
        e.add_field(name="What's New", value="\n".join(f"**v{v}** · {t}" for v, t in news[:8])[:1024], inline=False)
    await interaction.followup.send(embed=e, ephemeral=not public)
    log.info("Updating v%s -> v%s, restarting", RUNNING_VERSION, new_version)
    await asyncio.sleep(2)
    os.execv(sys.executable, [sys.executable, str(HERE / "main.py")])
