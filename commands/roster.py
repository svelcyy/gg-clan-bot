"""/roster: add, remove, link, rank, note, start, exempt, sync, list and reset."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

roster_group = app_commands.Group(name="roster", description="Manage the clan roster",
                                  default_permissions=STAFF_ONLY, guild_only=True)


@roster_group.command(name="add", description="Add someone to the clan roster with their starting coins")
@app_commands.describe(roblox="Their Roblox username (the @ name)", discord_user="Their Discord account",
                       coins="Their Contribution number in game right now (their starting point). Leave empty for 0",
                       rank="Clan rank (default Member)", exempt="Skip them in coin checks?", notes="Optional note")
@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@app_commands.choices(rank=RANK_CHOICES)
async def roster_add(interaction: discord.Interaction, roblox: str, discord_user: Optional[discord.User] = None,
                     coins: Optional[app_commands.Range[int, 0]] = None,
                     rank: Optional[app_commands.Choice[str]] = None, exempt: bool = False, notes: str = "", public: bool = False):
    if not is_admin(interaction.user) and ((rank and rank.value != "Member") or exempt):
        await interaction.response.send_message(embed=simple(
            "Only the Clan Manager can add someone as staff or as exempt. "
            "Add them as a Member, and ask the Clan Manager to change their rank.", RED), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=not public)  # only the person who ran it sees the reply
    name, rid, notes_out = roblox.strip().lstrip("@"), None, []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            found = await rbx.lookup_usernames(s, [name])
        if name.lower() not in found:
            await interaction.followup.send(embed=simple(
                f"There's no Roblox account called **{esc(name)}**. Check the spelling, and use the @ username, "
                "not the display name.", RED, "❌ Not Added"), ephemeral=not public)
            return
        rid, name = found[name.lower()]
    except Exception:
        notes_out.append("Couldn't reach Roblox to double-check the username, so it was added as typed.")
    if discord_user and store.discord_id_owner(discord_user.id):
        notes_out.append(f"That Discord account is also linked to {', '.join(store.discord_id_owner(discord_user.id))}.")
    rank_name = rank.value if rank else "Member"
    exempt = exempt or rank_name != "Member"   # staff are always exempt from coin checks
    coins_given = coins is not None
    old_discord = store.former_discord_id(name, rid)   # were they on the roster before?
    if not coins_given:   # leaving the clan in game wipes Contribution, so everyone starts from 0
        coins = 0                                    # no number given: start from 0
    if discord_user is None and old_discord:
        try:
            discord_user = bot.get_user(old_discord) or await bot.fetch_user(old_discord)
        except discord.HTTPException:
            pass
    if not store.add_member(name, rid, discord_user.id if discord_user else None, rank_name, exempt, notes, coins):
        await interaction.followup.send(embed=simple(f"**{esc(name)}** is already on the roster.", AMBER),
                                        ephemeral=not public)
        return
    roles = await sync_roles(interaction.guild, discord_user.id if discord_user else None, rank_name)
    group = await sync_group(name, rid, rank_name)
    restored = bool(old_discord and discord_user and discord_user.id == old_discord)
    desc = ("Welcome back! Their Discord link was restored." if restored else "")
    info = [("Rank", rank_name + (" · Exempt" if exempt else ""), True),
            ("Discord", handle(discord_user) if discord_user else "Not linked", True),
            ("Starting Coins", f"{coins:,}", True)]
    footer = f"{len(store.members())} members on the roster"
    await interaction.followup.send(embed=update_embed(
        f"✅ Added {name}", desc, fields=info, discord_roles=roles, group=group, notes=notes_out, footer=footer),
        ephemeral=not public)
    alert = update_embed(f"🆕 New Clan Member: {name}", f"Added by {handle(interaction.user)}", fields=info,
                         footer=footer)
    await post_alert(alert, skip_channel_id=None)


@roster_group.command(name="start", description="Set or fix someone's starting coins")
@admin_only
@app_commands.describe(coins="Their Contribution number at the point they should be measured from")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_start(interaction: discord.Interaction, roblox: str, coins: app_commands.Range[int, 0]):
    ok = store.update_member(roblox, start_total=coins)
    await interaction.response.send_message(embed=simple(
        f"**{esc(roblox)}** now starts from **{coins:,}** coins." if ok else f"**{esc(roblox)}** isn't on the roster.",
        GREEN if ok else AMBER, "🏁 Starting Coins Updated" if ok else None), ephemeral=True)


@roster_group.command(name="reset", description="Delete the whole roster and every coin check (admins only)")
@admin_only
@app_commands.describe(confirm="Type RESET in capitals to confirm")
async def roster_reset(interaction: discord.Interaction, confirm: str):
    if confirm != "RESET":
        await interaction.response.send_message(embed=simple(
            "Nothing deleted. To wipe the roster and all coin checks, type `RESET` in capitals.", AMBER),
            ephemeral=True)
        return
    count = len(store.members())
    store.reset_all()
    await interaction.response.send_message(embed=simple(
        f"Removed {count} members and every coin check.\nAdd people with `/roster add`.", GREEN, "🧹 Fresh Start"))


@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@roster_group.command(name="remove", description="Remove someone from the roster and take their clan roles")
@app_commands.describe(keep_roles="Leave their Discord roles alone (default: take gg Member and rank roles away)")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_remove(interaction: discord.Interaction, roblox: str, keep_roles: bool = False, public: bool = False):
    m = store.get_member(roblox)
    if not m:
        await interaction.response.send_message(embed=not_on_roster(roblox),
                                                ephemeral=True)
        return
    if not is_admin(interaction.user):
        if m.discord_id == interaction.user.id:
            await interaction.response.send_message(embed=simple(
                "You can't remove yourself from the roster. If you're leaving or resigning, "
                "let the Clan Manager know and they'll take care of it.", RED), ephemeral=True)
            return
        level = {"Member": 0, "Officer": 1, "Admin": 2, "Leader": 3}
        me = store.member_by_discord(interaction.user.id)
        my_level = level.get(me.rank, 0) if me else 0
        if level.get(m.rank, 0) >= max(my_level, 1):   # only someone ranked above them can remove them
            await interaction.response.send_message(embed=simple(
                f"**{esc(m.roblox_username)}** is {m.rank}, the same rank as you or higher. "
                "Only someone ranked above them (or the Clan Manager) can remove them.", RED), ephemeral=True)
            return
    await interaction.response.defer(ephemeral=not public)  # only the person who ran it sees the reply
    store.remove_member(roblox)
    others = [o for o in store.discord_id_owner(m.discord_id)] if m.discord_id else []
    if keep_roles:
        roles, group = "Left as they were.", ""
    else:
        roles = (f"Kept, because that account is still on the roster as {', '.join(others)}." if others
                 else await sync_roles(interaction.guild, m.discord_id, None))
        group = await sync_group(m.roblox_username, m.roblox_id, None)
    footer = f"{len(store.members())} members on the roster"
    await interaction.followup.send(embed=update_embed(
        f"🗑️ Removed {m.roblox_username}", color=RED, discord_roles=roles, group=group,
        footer=footer), ephemeral=not public)
    alert = update_embed(f"👋 Left the Clan: {m.roblox_username}", f"Removed by {handle(interaction.user)}",
                         color=RED, fields=[("Rank", m.rank, True),
                                            ("Discord", reports.dname(m.discord_id) or "Not linked", True)],
                         footer=footer)
    await post_alert(alert)


@roster_group.command(name="link", description="Link a member's Discord account")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_link(interaction: discord.Interaction, roblox: str, discord_user: discord.User):
    if not store.get_member(roblox):
        await interaction.response.send_message(embed=simple(
            f"**{esc(roblox)}** isn't on the roster. Add them with `/roster add`.", AMBER), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    others = [o for o in store.discord_id_owner(discord_user.id) if o.lower() != roblox.lower()]
    store.update_member(roblox, discord_id=discord_user.id)
    m = store.get_member(roblox)
    roles = await sync_roles(interaction.guild, discord_user.id, m.rank)
    await interaction.followup.send(embed=update_embed(
        f"🔗 Linked {m.roblox_username}", f"Now linked to **{handle(discord_user)}**.",
        fields=[("Rank", m.rank, True)], discord_roles=roles,
        notes=[f"That Discord account is also linked to {', '.join(others)}."] if others else []), ephemeral=True)


@roster_group.command(name="exempt", description="Turn coin-check exemption on or off")
@admin_only
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_exempt(interaction: discord.Interaction, roblox: str, exempt: bool):
    ok = store.update_member(roblox, exempt=exempt)
    text = (f"**{esc(roblox)}** is now exempt from coin checks." if exempt
            else f"**{esc(roblox)}** is no longer exempt from coin checks.") \
        if ok else f"**{esc(roblox)}** isn't on the roster."
    await interaction.response.send_message(embed=simple(text, PURPLE if ok and exempt else GREEN if ok else AMBER),
                                            ephemeral=True)


@app_commands.describe(public="Show the reply to everyone in the channel (default: only you)")
@roster_group.command(name="rank", description="Change someone's clan rank")
@admin_only
@app_commands.autocomplete(roblox=roster_autocomplete)
@app_commands.choices(rank=RANK_CHOICES)
async def roster_rank(interaction: discord.Interaction, roblox: str, rank: app_commands.Choice[str], public: bool = False):
    before = store.get_member(roblox)
    if not before or not store.update_member(roblox, rank=rank.value):
        await interaction.response.send_message(embed=not_on_roster(roblox),
                                                ephemeral=True)
        return
    await interaction.response.defer(ephemeral=not public)  # only the person who ran it sees the reply
    m = store.get_member(roblox)
    roles = await sync_roles(interaction.guild, m.discord_id, rank.value)
    group = await sync_group(m.roblox_username, m.roblox_id, rank.value)
    await interaction.followup.send(embed=update_embed(
        f"🎖️ {m.roblox_username} is now {rank.value}", discord_roles=roles, group=group), ephemeral=not public)
    if before.rank != rank.value:
        old_i = RANKS.index(before.rank) if before.rank in RANKS else len(RANKS)
        promoted = RANKS.index(rank.value) < old_i   # RANKS goes Leader, Admin, Officer, Member
        alert = update_embed(f"{'⬆️ Promoted' if promoted else '⬇️ Demoted'}: {m.roblox_username}",
                             f"Changed by {handle(interaction.user)}", color=GREEN if promoted else AMBER,
                             fields=[("Rank", f"{before.rank} → **{rank.value}**", True),
                                     ("Discord", reports.dname(m.discord_id) or "Not linked", True)])
        await post_alert(alert)


@roster_group.command(name="note", description="Set a note on a member (leave empty to clear)")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_note(interaction: discord.Interaction, roblox: str, note: str = ""):
    ok = store.update_member(roblox, notes=note)
    text = ((f"Note saved for **{esc(roblox)}**." if note else f"Note cleared for **{esc(roblox)}**.") if ok
            else f"**{esc(roblox)}** isn't on the roster.")
    await interaction.response.send_message(embed=simple(text, GREEN if ok else AMBER), ephemeral=True)


def _outcome(text: str) -> str:
    """Sort a sync_roles / sync_group reply into: changed, problem or ok."""
    if not text:
        return "ok"
    if "➕" in text or "➖" in text:
        return "changed"
    if text.startswith("⚠️") or text.startswith("Not in the Roblox group"):
        return "problem"
    return "ok"


def _flat(text: str) -> str:
    return " · ".join(line.strip() for line in text.splitlines() if line.strip())


@roster_group.command(name="sync", description="Check everyone's Discord and Roblox group roles and fix any that are wrong")
@admin_only
@app_commands.describe(remove_extras="Also take clan roles away from people who aren't on the roster (default: just list them)")
async def roster_sync(interaction: discord.Interaction, remove_extras: bool = False):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    members = store.members()
    fixed, problems, unlinked = [], [], []

    async def progress(done: int):
        try:
            await interaction.edit_original_response(embed=simple(
                f"Checking roles… **{done}/{len(members)}**", BLURPLE, "🔄 Syncing the Roster"))
        except discord.HTTPException:
            pass

    for i, m in enumerate(members):
        if i % 10 == 0:
            await progress(i)
        if m.rank != "Member" and not m.exempt:
            store.update_member(m.roblox_username, exempt=True)   # staff are always exempt
        roles = await sync_roles(guild, m.discord_id, m.rank) if m.discord_id else ""
        if not m.discord_id:
            unlinked.append(m)
        group = await sync_group(m.roblox_username, m.roblox_id, m.rank)
        name = f"**{esc(m.roblox_username)}**"
        changes = []
        if _outcome(roles) == "changed":
            changes.append(f"Discord: {_flat(roles)}")
        if _outcome(group) == "changed":
            changes.append(f"Group: {_flat(group)}")
        issues = [_flat(t) for t in (roles, group) if _outcome(t) == "problem"]
        if changes:
            fixed.append(reports.Entry(name, " · ".join(changes)))
        if issues:
            problems.append(reports.Entry(name, " · ".join(issues)))
    await progress(len(members))

    # people holding clan roles who aren't on the roster
    extras: list[reports.Entry] = []
    roster_ids = {m.discord_id for m in store.members() if m.discord_id}
    member_role = find_role(guild, MEMBER_ROLE)
    managed = {r for r in [member_role] + [find_role(guild, n) for n in RANK_ROLES.values()] if r}
    try:
        async for mem in guild.fetch_members(limit=None):
            if mem.bot or mem.id in roster_ids:
                continue
            held = managed & set(mem.roles)
            if not held:
                continue
            if remove_extras:
                try:
                    await mem.remove_roles(*held, reason="[gg] not on the roster")
                    extras.append(reports.Entry(f"**@{esc(mem.name)}**", "➖ " + ", ".join(r.name for r in held)))
                except discord.Forbidden:
                    problems.append(reports.Entry(f"**@{esc(mem.name)}**", "⚠️ Couldn't remove their clan roles"))
            else:
                extras.append(reports.Entry(f"**@{esc(mem.name)}**", "Has " + ", ".join(r.name for r in held)))
    except discord.HTTPException:
        log.exception("Couldn't scan server members")
    if group_manager:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                holders = await rbx.clan_role_holders(s, ROBLOX_GROUP_ID, ROBLOX_MIN_RANK, ROBLOX_IGNORE_ROLES)
            roster_uids = {m.roblox_id for m in store.members() if m.roblox_id}
            for uid, (uname, role) in sorted(holders.items(), key=lambda kv: kv[1][0].lower()):
                if uid in roster_uids:
                    continue
                if remove_extras:
                    result = await sync_group(uname, uid, None)
                    entry = reports.Entry(f"**{esc(uname)}**", f"Group: {_flat(result)}")
                    (problems if _outcome(result) == "problem" else extras).append(entry)
                else:
                    extras.append(reports.Entry(f"**{esc(uname)}**", f"{role} in the group"))
        except Exception:
            log.exception("Couldn't check Roblox group extras")

    lists = [reports.ListView(f"Fixed ({len(fixed)})", fixed, empty="Everyone already had the right roles"),
             reports.ListView(f"Couldn't Fix ({len(problems)})", problems, empty="No problems"),
             reports.ListView(f"{'Removed' if remove_extras else 'Not on the Roster'} ({len(extras)})", extras,
                              empty="Nobody extra")]
    if unlinked:
        lists.append(reports.ListView(f"Not Linked ({len(unlinked)})",
                                      [reports.Entry(f"**{esc(m.roblox_username)}**", "Link with /roster link")
                                       for m in unlinked]))
    header = reports.joined(f"{len(members)} checked", f"{len(fixed)} fixed",
                            f"{len(problems)} couldn't fix" if problems else "",
                            f"{len(extras)} {'removed' if remove_extras else 'not on the roster'}" if extras else "")
    board = Board("🔄 Roster Sync", header, lists, AMBER if problems else GREEN, noun="people")
    view = BoardView(board, owner_id=interaction.user.id)
    await interaction.edit_original_response(embed=view.embed(), view=view if view.needed() else None)
    if fixed or (remove_extras and extras):
        alert = simple(f"{handle(interaction.user)} synced the roster: {header}.", BLURPLE, "🔄 Roster Synced")
        await post_alert(alert)


@roster_group.command(name="list", description="Browse the roster (and download it as a spreadsheet file)")
async def roster_list(interaction: discord.Interaction):
    await interaction.response.defer()
    await load_names()
    cid = store.latest_check_id()
    latest = {r.member.roblox_username: r for r in store.results(cid)} if cid else None
    await send_board(interaction, reports.roster_board(store.members(), latest, store.export_csv()))


GROUPS.append(roster_group)
