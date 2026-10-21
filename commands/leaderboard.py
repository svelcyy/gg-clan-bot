"""/leaderboard: everyone's coins and gains."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

@app_commands.describe(public="Show the reply to everyone in the channel (default: yes)")
@bot.tree.command(name="leaderboard", description="See the latest coin check: everyone's coins and gains")
@app_commands.guild_only()
async def leaderboard(interaction: discord.Interaction, public: bool = True):
    cid = store.latest_check_id()
    await interaction.response.defer(ephemeral=not public)
    await load_names()
    if not cid:   # no graded check yet: show everyone's current coins
        await send_board(interaction, reports.current_coins_board(store.members()), ephemeral=not public)
        return
    prev = store.previous_check_id(cid)
    board = reports.leaderboard_board(store.results(cid), store.check_label(cid),
                                      store.check_label(prev) if prev else None, store.get_minimum())
    await send_board(interaction, board, ephemeral=not public)
