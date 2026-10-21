"""/staffguide: the staff guide pages."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

def staff_guide_embed(key: str) -> discord.Embed:
    i = next(n for n, p in enumerate(staff_guide.PAGES) if p[0] == key)
    _, emoji, title, body = staff_guide.PAGES[i]
    e = discord.Embed(title=f"{emoji} {title}", description=body, color=reports.BLURPLE)
    e.set_author(name="[gg] Staff Guide")
    e.set_footer(text=f"Page {i + 1} of {len(staff_guide.PAGES)} · Pick a page from the menu")
    return e


class StaffGuideMenu(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Pick a page…", options=[
            discord.SelectOption(label=t, value=k, emoji=e, default=(n == 0))
            for n, (k, e, t, _) in enumerate(staff_guide.PAGES)])

    async def callback(self, interaction: discord.Interaction):
        for o in self.options:
            o.default = o.value == self.values[0]
        await interaction.response.edit_message(embed=staff_guide_embed(self.values[0]), view=self.view)


class StaffGuideView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900)
        self.add_item(StaffGuideMenu())


@app_commands.describe(public="Show the guide to everyone in the channel (default: only you)")
@bot.tree.command(name="staffguide", description="How staff use the bot: adding, ranking and removing members")
@app_commands.default_permissions(manage_roles=True)
@app_commands.guild_only()
async def staffguide(interaction: discord.Interaction, public: bool = False):
    await interaction.response.send_message(embed=staff_guide_embed(staff_guide.PAGES[0][0]),
                                            view=StaffGuideView(), ephemeral=not public)
