"""/coins: import, results, set, status, minimum and undo."""
from __future__ import annotations

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

coins_group = app_commands.Group(name="coins", description="Monthly coin checks",
                                 default_permissions=STAFF_ONLY, guild_only=True)


def coin_board(cid: int, unknown: list[str] | None = None) -> Board:
    prev = store.previous_check_id(cid)
    return reports.coin_board(store.results(cid), store.check_label(cid),
                              store.check_label(prev) if prev else None, store.get_minimum(), unknown,
                              csv_text=store.export_csv())


def names_list(names: list[str], limit: int = 15) -> str:
    shown = ", ".join(names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


async def prepare_import(text: str) -> dict | None:
    """Read the pasted/uploaded totals and match them to the roster, recognising renamed Roblox accounts."""
    totals = parse_totals_csv(text)
    if not totals:
        return None
    roster = store.members()
    ids: dict[str, int] = {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            need = [m.roblox_username for m in roster if not m.roblox_id]   # learn roster ids once
            if need:
                found = await rbx.lookup_usernames(s, need)
                for m in roster:
                    if m.roblox_username.lower() in found:
                        store.update_member(m.roblox_username, roblox_id=found[m.roblox_username.lower()][0])
                roster = store.members()
            on_roster = {m.roblox_username.lower() for m in roster}
            strangers = [n for n in totals if n.lower() not in on_roster]
            if strangers:
                ids = {k: v[0] for k, v in (await rbx.lookup_usernames(s, strangers)).items()}
    except Exception:
        log.exception("Roblox lookup during import failed")  # still works, just without rename detection
    matched, renames, unknown = match_totals(totals, roster, ids)
    imported = {m.roblox_username for m in roster if m.roblox_username in matched}
    missing = [m.roblox_username for m in roster if not m.exempt and m.roblox_username not in imported]
    return {"matched": matched, "renames": renames, "unknown": unknown, "missing": missing,
            "unknown_totals": {u: totals[u] for u in unknown}, "count": len(totals)}


def _match_fields(e: discord.Embed, p: dict, missing_note: str, unknown_note: str):
    """The renamed / missing / not-on-roster fields both previews share."""
    if p["renames"]:
        e.add_field(name=f"Changed Roblox Username ({len(p['renames'])})",
                    value=names_list([f"{o} → {n}" for o, n in p["renames"]]) +
                    "\nTheir roster entry, Discord link and history will move to the new name.", inline=False)
    if p["missing"]:
        e.add_field(name=f"Not in This Import ({len(p['missing'])})",
                    value=names_list(p["missing"]) + missing_note, inline=False)
    if p["unknown"]:
        e.add_field(name=f"Not on the Roster ({len(p['unknown'])})",
                    value=names_list(p["unknown"]) + unknown_note, inline=False)
    e.set_footer(text=f"{p['count']} lines read")
    return e


def preview_embed(label: str, p: dict) -> discord.Embed:
    results = store.preview(p["matched"])
    count = lambda status: sum(r.status == status for r in results)   # noqa: E731
    e = discord.Embed(title=f"🪙 Coin Check Preview · {label}", color=reports.AMBER,
                      description="Nothing is saved until you click **Save**.")
    e.add_field(name="Matched", value=f"{len(p['matched'])} of {len(store.members())} on the roster", inline=True)
    e.add_field(name="Would Pass", value=str(count("Pass")), inline=True)
    e.add_field(name="Would Fail", value=str(count("Fail")) + (f" · {count('Baseline')} new" if count("Baseline")
                                                                 else ""), inline=True)
    if not (p["renames"] or p["missing"] or p["unknown"]):
        e.add_field(name="Everything Matches", value="Every roster member is in this import.", inline=False)
    return _match_fields(e, p, "", "\nTheir numbers are kept in case you add them later.")


def start_preview_embed(p: dict) -> discord.Embed:
    members = {m.roblox_username: m for m in store.members()}
    from_zero = sum(1 for k in p["matched"] if not (members.get(k) and members[k].start_total))
    e = discord.Embed(title="🏁 Starting Coins Preview", color=reports.AMBER,
                      description="This sets each member's **starting coins** to these numbers. Nothing is graded, "
                                  "and no coin check is saved. The next coin check measures from here.\n"
                                  "Nothing is saved until you click **Save**.")
    e.add_field(name="Matched", value=f"{len(p['matched'])} of {len(members)} on the roster", inline=True)
    e.add_field(name="Currently at 0 or Blank", value=str(from_zero), inline=True)
    _match_fields(e, p, "\nTheir starting coins stay as they are.",
                  "\nSkipped. Add them with `/roster add` and their number.")
    checks = store.latest_check_id()
    if checks:
        e.add_field(name="Note", value=f"There's already a saved coin check (**{store.check_label(checks)}**). "
                    "The next check compares with that instead of these starting coins. "
                    "Use `/coins undo` to delete old test checks first.", inline=False)
    return e


class ImportConfirm(discord.ui.View):
    def __init__(self, owner_id: int, label: str, prepared: dict, starting: bool = False):
        super().__init__(timeout=900)
        self.owner_id, self.label, self.p, self.starting = owner_id, label, prepared, starting
        self.done = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("Only the person who started this import can save it.", ephemeral=True)
        return False

    @discord.ui.button(label="Save", style=discord.ButtonStyle.success)
    async def save(self, interaction: discord.Interaction, _):
        if self.done:
            return
        self.done = True
        renamed = []
        for old, new in self.p["renames"]:
            if store.rename_member(old, new):
                renamed.append(new)
        names = dict(self.p["renames"])
        totals = {names.get(k, k): v for k, v in self.p["matched"].items()}
        if self.starting:
            for name, total in totals.items():
                store.update_member(name, start_total=total)
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=simple(
                f"Set starting coins for **{len(totals)}** members." +
                (f" Updated {len(renamed)} renamed Roblox account(s)." if renamed else "") +
                " The next coin check measures from these numbers.", GREEN, "✅ Starting Coins Saved"), view=self)
            await post_alert(simple(f"{handle(interaction.user)} set starting coins for {len(totals)} members.",
                                    BLURPLE, "🏁 Starting Coins Updated"))
            return
        totals.update(self.p["unknown_totals"])
        cid, unknown = store.import_check(self.label, totals, str(interaction.user))
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=simple(f"Saved **{self.label}**." + (f" Updated {len(renamed)} renamed Roblox account(s)." if renamed
                         else ""), GREEN, "✅ Coin Check Saved"), view=self)
        await load_names()
        board = coin_board(cid, unknown)
        await send_board(interaction, board)           # posted in this channel for everyone
        await post_board_to_staff(board, skip_channel_id=interaction.channel_id)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _):
        self.done = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=simple("Nothing was saved.", AMBER, "❌ Import Cancelled"),
                                                view=self)


async def show_preview(interaction: discord.Interaction, text: str, label: str | None, starting: bool = False):
    label = (label or "").strip() or dt.date.today().strftime("%d %b %Y")
    prepared = await prepare_import(text)
    if prepared is None:
        await interaction.followup.send(embed=simple(
            "I couldn't find any lines like `username 875128` in that. Put one person per line: their Roblox "
            "username, then their Contribution number.", RED), ephemeral=True)
        return
    await interaction.followup.send(embed=start_preview_embed(prepared) if starting else preview_embed(label, prepared),
                                    view=ImportConfirm(interaction.user.id, label, prepared, starting), ephemeral=True)


class ImportModal(discord.ui.Modal, title="Import Coin Check"):
    label_input = discord.ui.TextInput(label="Name for this check", placeholder="e.g. Nov 2026", required=False,
                                       max_length=40)
    totals_input = discord.ui.TextInput(label="Paste totals: one per line", style=discord.TextStyle.paragraph,
                                        placeholder="pramishp4 875128\n2pfaltac 365000\n…", max_length=4000)

    def __init__(self, label: str | None, starting: bool = False):
        super().__init__(title="Set Starting Coins" if starting else "Import Coin Check")
        self.starting = starting
        if label:
            self.label_input.default = label
        if starting:
            self.remove_item(self.label_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await show_preview(interaction, self.totals_input.value, self.label_input.value, self.starting)


@coins_group.command(name="import", description="Import this month's totals: paste them, or attach a file")
@admin_only
@app_commands.describe(file="Optional .csv/.txt with one 'username total' per line. Leave empty to paste instead",
                       label="Name for this check, e.g. 'Nov 2026'",
                       mode="Coin check (graded), or just set everyone's starting coins")
@app_commands.choices(mode=[app_commands.Choice(name="Coin check (graded)", value="check"),
                            app_commands.Choice(name="Starting coins only (not graded)", value="start")])
async def coins_import(interaction: discord.Interaction, file: Optional[discord.Attachment] = None,
                       label: Optional[str] = None, mode: Optional[app_commands.Choice[str]] = None):
    starting = bool(mode and mode.value == "start")
    if file is None:
        await interaction.response.send_modal(ImportModal(label, starting))
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    if file.size > 500_000:
        await interaction.followup.send(embed=simple("That file is too big. It should be a small list.", RED),
                                        ephemeral=True)
        return
    await show_preview(interaction, (await file.read()).decode("utf-8-sig", errors="replace"), label, starting)


@coins_group.command(name="results", description="Show the latest coin check results")
async def coins_results(interaction: discord.Interaction):
    cid = store.latest_check_id()
    if not cid:
        await interaction.response.send_message(embed=simple("No coin checks yet.", AMBER), ephemeral=True)
        return
    await interaction.response.defer()
    await load_names()
    await send_board(interaction, coin_board(cid))


@coins_group.command(name="set", description="Fix one member's total in the latest check")
@admin_only
@app_commands.autocomplete(roblox=roster_autocomplete)
async def coins_set(interaction: discord.Interaction, roblox: str, total: app_commands.Range[int, 0]):
    cid = store.latest_check_id()
    if not cid:
        await interaction.response.send_message(embed=simple("No coin checks yet.", AMBER), ephemeral=True)
        return
    store.set_total(cid, roblox, total)
    r = next((r for r in store.results(cid) if r.member.roblox_username.lower() == roblox.lower()), None)
    if r:
        extra = f"Now **{r.status}**" + (f" (gained {reports.n(r.gained)})" if r.gained is not None else "")
        color = {"Pass": GREEN, "Fail": RED}.get(r.status, AMBER)
    else:
        extra, color = "They're not on the roster, so it won't count until they're added.", AMBER
    await interaction.response.send_message(embed=simple(
        f"**{esc(roblox)}**: total set to {total:,} for {store.check_label(cid)}.\n{extra}", color), ephemeral=True)


@coins_group.command(name="status", description="See one member's coin history")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def coins_status(interaction: discord.Interaction, roblox: str):
    m = store.get_member(roblox)
    if not m:
        await interaction.response.send_message(embed=not_on_roster(roblox),
                                                ephemeral=True)
        return
    title, desc, color = reports.member_status(m, store.history(m.roblox_username), store.get_minimum())
    await interaction.response.send_message(embed=simple(desc, color, title), ephemeral=True)


@coins_group.command(name="minimum", description="Change the monthly minimum (default 10,000)")
@admin_only
async def coins_minimum(interaction: discord.Interaction, amount: app_commands.Range[int, 0]):
    store.set_minimum(amount)
    await interaction.response.send_message(embed=simple(
        f"Monthly minimum is now **{amount:,}** coins. Results use it straight away."), ephemeral=True)


@coins_group.command(name="undo", description="Delete the most recent coin check import")
@admin_only
@app_commands.describe(confirm="Type the check's name exactly to confirm")
async def coins_undo(interaction: discord.Interaction, confirm: str):
    cid = store.latest_check_id()
    if not cid:
        await interaction.response.send_message(embed=simple("There are no coin checks to undo.", AMBER),
                                                ephemeral=True)
        return
    label = store.check_label(cid)
    if confirm.strip() != label:
        await interaction.response.send_message(embed=simple(
            f"Nothing deleted. To delete the latest check, type its name exactly: `{label}`", AMBER), ephemeral=True)
        return
    store.delete_check(cid)
    await interaction.response.send_message(embed=simple(f"Deleted the coin check **{label}**."), ephemeral=True)


GROUPS.append(coins_group)
