"""/userinfo: someone's Discord profile plus their clan info."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

BADGES = [  # Discord's public profile badges
    ("staff", "Discord Staff"), ("partner", "Partnered Server Owner"),
    ("hypesquad", "HypeSquad Events"), ("hypesquad_bravery", "HypeSquad Bravery"),
    ("hypesquad_brilliance", "HypeSquad Brilliance"), ("hypesquad_balance", "HypeSquad Balance"),
    ("bug_hunter", "Bug Hunter"), ("bug_hunter_level_2", "Bug Hunter Gold"),
    ("early_supporter", "Early Supporter"), ("verified_bot_developer", "Early Verified Bot Developer"),
    ("discord_certified_moderator", "Moderator Programs Alumni"), ("active_developer", "Active Developer"),
]
STATUS_TEXT = {discord.Status.online: "🟢 Online", discord.Status.idle: "🌙 Idle",
               discord.Status.dnd: "⛔ Do Not Disturb", discord.Status.offline: "⚫ Offline"}


def when(t: dt.datetime) -> str:
    """A date that shows in each viewer's own time zone, plus how long ago."""
    ts = int(t.timestamp())
    return f"<t:{ts}:f> (<t:{ts}:R>)"


def userinfo_embed(member: discord.Member, full: discord.User | None, current: int | None) -> discord.Embed:
    color = member.color if member.color.value else discord.Color(reports.BLURPLE)
    nitro = bool((full and full.banner) or member.display_avatar.is_animated())
    e = discord.Embed(color=color, timestamp=dt.datetime.now(dt.timezone.utc))
    e.set_author(name=member.name, icon_url=member.display_avatar.url)
    e.set_thumbnail(url=member.display_avatar.url)

    user = [f"▸ Mention: {member.mention}", f"▸ ID: `{member.id}`"]
    if SHOW_STATUS:
        user.append(f"▸ Status: {STATUS_TEXT.get(member.status, '⚫ Offline')}")
    user.append(f"▸ Created: {when(member.created_at)}")
    e.description = f"**{'Nitro User' if nitro else 'User'}**\n" + "\n".join(user)

    perms, guild = member.guild_permissions, member.guild
    acks = []
    if guild.owner_id == member.id:
        acks.append("Server Owner")
    elif perms.administrator:
        acks.append("Server Admin")
    elif perms.manage_guild or perms.kick_members or perms.ban_members:
        acks.append("Server Moderator")
    if member.premium_since:
        acks.append("Server Booster")
    if member.bot:
        acks.append("Bot")
    badges = [label for flag, label in BADGES if getattr(member.public_flags, flag, False)]
    e.add_field(name="Acknowledgements", value="\n".join(acks) or "None", inline=True)
    e.add_field(name="Badges", value="\n".join(badges) or "None", inline=True)

    info = [f"▸ Nickname: {discord.utils.escape_markdown(member.nick) if member.nick else 'None'}",
            f"▸ Display Color: `{str(member.color) if member.color.value else 'Default'}`",
            f"▸ Roles: {len(member.roles) - 1}"]
    if member.top_role and not member.top_role.is_default():
        info.append(f"▸ Top Role: {member.top_role.mention}")
    if guild.chunked and member.joined_at:
        order = sorted((m for m in guild.members if m.joined_at), key=lambda m: m.joined_at)
        info.append(f"▸ Join Position: {order.index(member) + 1:,}" if member in order else "")
    if member.joined_at:
        info.append(f"▸ Joined: {when(member.joined_at)}")
    if member.premium_since:
        info.append(f"▸ Boosting Since: {when(member.premium_since)}")
    e.add_field(name="Member", value="\n".join(x for x in info if x), inline=False)

    m = store.member_by_discord(member.id)
    if m is None:
        e.add_field(name="[gg] Clan", value="▸ Not a clan member\n-# Want to join? See `/claninfo`.", inline=False)
    else:
        minimum = store.get_minimum()
        history = store.history(m.roblox_username)
        link = (f"[{esc(m.roblox_username)}](https://www.roblox.com/users/{m.roblox_id}/profile)" if m.roblox_id
                else esc(m.roblox_username))
        clan = [f"▸ Roblox: {link}",
                f"▸ Rank: {m.rank}" + (" · Exempt from coin checks" if m.exempt else "")]
        if history:
            label, total, _ = history[0]
            clan.append(f"▸ Contribution: **{total:,}**" + ("" if label == "Joined" else f" (as of {label})"))
        checks = [h for h in history if h[2] is not None]
        if checks and not m.exempt:
            label, _, gained = checks[0]
            clan.append(f"▸ Last Coin Check: {label} · +{gained:,} {'Passed ✅' if gained >= minimum else 'Failed ❌'}")
        elif not m.exempt:
            clan.append(f"▸ Last Coin Check: None yet · Minimum is {minimum:,} a month")
        if current is not None and history and not m.exempt:
            last = history[0][1]
            so_far = current - last if current >= last else current   # lower = Contribution was reset
            need = max(0, minimum - so_far)
            clan.append(f"▸ This Month So Far: +{so_far:,} · " + ("Minimum reached ✅" if need == 0 else f"{need:,} to go"))
        e.add_field(name="[gg] Clan", value="\n".join(clan), inline=False)

    if full and full.banner:
        e.set_image(url=full.banner.url)
    e.set_footer(text=f"ID: {member.id}")
    return e


@app_commands.describe(user="Whose info to show (leave empty for yourself)",
                       current="Optional: your Contribution in game right now, to see how much you still need",
                       public="Show the reply to everyone in the channel (default: only you)")
@bot.tree.command(name="userinfo", description="Someone's Discord info, plus their clan rank and coins")
@app_commands.guild_only()
async def userinfo(interaction: discord.Interaction, user: Optional[discord.Member] = None,
                   current: Optional[app_commands.Range[int, 0]] = None, public: bool = False):
    await interaction.response.defer(ephemeral=not public)
    member = user or interaction.user
    if not isinstance(member, discord.Member):
        member = interaction.guild.get_member(member.id) or await interaction.guild.fetch_member(member.id)
    try:
        full = await bot.fetch_user(member.id)   # the banner only comes with a full fetch
    except discord.HTTPException:
        full = None
    await interaction.followup.send(embed=userinfo_embed(member, full, current), ephemeral=not public)
