"""/check: compare the roster with Discord and the Roblox group, plus the weekly report."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

async def build_check(guild: discord.Guild, which: str) -> Board:
    roster = store.members()
    discord_data = roblox_data = None
    errors: list[str] = []
    if which in ("all", "discord"):
        role = (guild.get_role(int(MEMBER_ROLE)) if MEMBER_ROLE.isdigit()
                else discord.utils.get(guild.roles, name=MEMBER_ROLE))
        if role is None:
            errors.append(f"Couldn't find a Discord role called {MEMBER_ROLE}")
        else:
            server_ids, role_ids, names = set(), set(), {}
            async for mem in guild.fetch_members(limit=None):
                if mem.bot:
                    continue
                server_ids.add(mem.id)
                names[mem.id] = mem.name
                if any(r.id == role.id for r in mem.roles):
                    role_ids.add(mem.id)
            discord_data = (role_ids, server_ids, names, role.name)
    if which in ("all", "roblox"):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                need = [m.roblox_username for m in roster if not m.roblox_id]
                found = await rbx.lookup_usernames(s, need) if need else {}
                for m in roster:  # remember IDs so renamed accounts still match next time
                    if not m.roblox_id and m.roblox_username.lower() in found:
                        store.update_member(m.roblox_username, roblox_id=found[m.roblox_username.lower()][0])
                holders = await rbx.clan_role_holders(s, ROBLOX_GROUP_ID, ROBLOX_MIN_RANK, ROBLOX_IGNORE_ROLES)
            roster = store.members()
            roblox_data = ({k: v[0] for k, v in found.items()}, holders)
        except Exception as e:
            log.exception("Roblox check failed")
            errors.append(f"Roblox check failed: {e}")
    return reports.check_board(roster, discord_data, roblox_data, errors)


@bot.tree.command(name="check", description="Compare the roster with Discord roles and the Roblox group")
@app_commands.choices(what=[
    app_commands.Choice(name="everything", value="all"),
    app_commands.Choice(name="Discord role only", value="discord"),
    app_commands.Choice(name="Roblox group only", value="roblox"),
])
@app_commands.default_permissions(manage_roles=True)
@app_commands.guild_only()
async def check(interaction: discord.Interaction, what: Optional[app_commands.Choice[str]] = None):
    await interaction.response.defer(thinking=True)
    await load_names()
    await send_board(interaction, await build_check(interaction.guild, what.value if what else "all"))


@tasks.loop(time=dt.time(hour=REPORT_HOUR_UTC, tzinfo=dt.timezone.utc))
async def weekly_report():
    if WEEKDAYS[dt.datetime.now(dt.timezone.utc).weekday()] != REPORT_WEEKDAY:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    await load_names()
    board = await build_check(guild, "all")
    board.title = "📋 Weekly Roster Check"
    await post_board_to_staff(board)


weekly_report.before_loop(wait_ready)


BACKGROUND_TASKS.append((weekly_report, lambda: bool(STAFF_CHANNEL_ID and WEEKLY_CHECK)))
