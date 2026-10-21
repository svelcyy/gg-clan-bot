"""/help: the category menu."""
from __future__ import annotations

import help_text

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

def help_embed(user: discord.abc.User, page: str = "home") -> discord.Embed:
    """page: 'home', a category name, or a command name."""
    if page == "home":
        desc, fields = help_text.home()
        e = discord.Embed(description=desc, color=reports.BLURPLE)
        for name, value, inline in fields:
            e.add_field(name=name, value=value, inline=inline)
    elif page in help_text.CATEGORY_EMOJI:
        e = discord.Embed(title=f"{help_text.CATEGORY_EMOJI[page]} {page}", description=help_text.category_page(page),
                          color=reports.BLURPLE)
    else:
        e = discord.Embed(title=page, description=help_text.detail(page), color=reports.BLURPLE)
    icon = bot.user.display_avatar.url if bot.user else None
    e.set_author(name="[gg] Bot Menu", icon_url=icon)
    e.set_footer(text=f"Requested by {user.name}", icon_url=user.display_avatar.url)
    return e


class HelpCategoryMenu(discord.ui.Select):
    def __init__(self, current: str = "home"):
        options = [discord.SelectOption(label="Home", value="home", emoji="🏠", description="Back to the main menu",
                                        default=current == "home")]
        options += [discord.SelectOption(label=n, value=n, emoji=e, description=d, default=current == n)
                    for n, e, d in help_text.CATEGORIES]
        super().__init__(placeholder="Choose a category…", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=help_embed(interaction.user, self.values[0]),
                                                view=HelpView(self.values[0]))


class HelpCommandMenu(discord.ui.Select):
    def __init__(self, category: str, current: str | None = None):
        options = [discord.SelectOption(label=c.name, value=c.name, description=c.short[:100],
                                        emoji="👑" if c.name in help_text.ADMIN_ONLY else "🔒" if c.staff else "▫️",
                                        default=c.name == current)
                   for c in help_text.in_category(category)][:25]
        super().__init__(placeholder="Choose a command for details…", options=options, row=1)
        self.category = category

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=help_embed(interaction.user, self.values[0]),
                                                view=HelpView(self.category, self.values[0]))


class HelpView(discord.ui.View):
    def __init__(self, category: str = "home", command: str | None = None):
        super().__init__(timeout=600)
        self.add_item(HelpCategoryMenu(category))
        if category != "home":
            self.add_item(HelpCommandMenu(category, command))


@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@bot.tree.command(name="help", description="See every command and how to use it")
@app_commands.guild_only()
async def help_command(interaction: discord.Interaction, public: bool = False):
    await interaction.response.send_message(embed=help_embed(interaction.user), view=HelpView(),
                                            ephemeral=not public)
