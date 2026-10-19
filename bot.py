"""[gg] Clan bot v2 — the bot itself. Started by main.py (which updates the code first).

Staff commands (need the Manage Roles permission):
  /roster add | remove | link | exempt | rank | note | list
  /coins import | results | set | status | minimum | undo
  /check
  /update
Everyone:
  /mystatus

Results are shown as embeds with ◀ ▶ page buttons and a menu to jump between sections.
The bot keeps its own data in clan.db. Settings come from environment variables / .env.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import sys
import logging
import os
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import help_text
import reports
import roblox as rbx
import updater
from reports import AMBER, GREEN, PURPLE, RED, Board
from storage import RANKS, Store, parse_totals_csv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ggbot")
HERE = Path(__file__).parent


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.getenv(name, default)
    if required and not val:
        raise SystemExit(f"Missing setting {name}. Add it in Wispbyte's Environment page or your .env file.")
    return val


TOKEN = env("DISCORD_TOKEN", required=True)
GUILD_ID = int(env("GUILD_ID", required=True))
MEMBER_ROLE = env("DISCORD_MEMBER_ROLE", "gg Member")
# Discord role for each clan rank (name or role ID). Leave empty for "no extra role".
RANK_ROLES = {
    "Leader": env("ROLE_LEADER", ""),
    "Admin": env("ROLE_ADMIN", "Clan Admin"),
    "Officer": env("ROLE_OFFICER", "Clan Officer"),
    "Member": "",
}
STAFF_CHANNEL_ID = env("STAFF_CHANNEL_ID") or env("REPORT_CHANNEL_ID")
ROBLOX_GROUP_ID = int(env("ROBLOX_GROUP_ID", "16909817"))
ROBLOX_MIN_RANK = int(env("ROBLOX_MIN_RANK", "75"))
ROBLOX_IGNORE_ROLES = {r.strip().lower() for r in env("ROBLOX_IGNORE_ROLES", "UGC").split(",") if r.strip()}
ROBLOX_API_KEY = env("ROBLOX_API_KEY")       # Open Cloud key with Groups read + write (optional)
GROUP_ROLES = {                              # clan rank -> Roblox group role name ("" = no clan role)
    "Leader": env("ROBLOX_ROLE_LEADER", ""),
    "Admin": env("ROBLOX_ROLE_ADMIN", "Clan Admin"),
    "Officer": env("ROBLOX_ROLE_OFFICER", "Clan Officer"),
    "Member": env("ROBLOX_ROLE_MEMBER", "Clan Member"),
}
WEEKLY_CHECK = env("WEEKLY_CHECK", "on").lower() in ("on", "yes", "true", "1")
REPORT_WEEKDAY = env("REPORT_WEEKDAY", "sunday").lower()
REPORT_HOUR_UTC = int(env("REPORT_HOUR_UTC", "17"))
DB_PATH = env("DB_PATH", str(HERE / "clan.db"))
GITHUB_REPO = env("GITHUB_REPO", "svelcyy/gg-clan-bot")
GITHUB_BRANCH = env("GITHUB_BRANCH", "main")
GITHUB_TOKEN = env("GITHUB_TOKEN")          # only needed if the repository is private

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
STAFF_ONLY = discord.Permissions(manage_roles=True)

store = Store(DB_PATH)


# ================================================================ boards ===
# Leaderboard-style embed: a menu to switch lists, ◀ ▶ to change page,
# and a button that hands out the full list as a spreadsheet file.

def simple(text: str, color: int = GREEN, title: str | None = None) -> discord.Embed:
    return discord.Embed(title=title, description=text, color=color)


def csv_file(text: str, name: str) -> discord.File:
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=name)


def board_embed(board: Board, list_index: int = 0, page: int = 0) -> discord.Embed:
    return discord.Embed(title=board.title, description=board.render(list_index, page)[:4096], color=board.color)


class ListMenu(discord.ui.Select):
    def __init__(self, view: "BoardView"):
        self.board_view = view
        options = [discord.SelectOption(label=lv.label[:100], value=str(i), default=i == 0)
                   for i, lv in enumerate(view.board.lists[:25])]
        super().__init__(placeholder="Switch list…", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        v = self.board_view
        v.list_index, v.page = int(self.values[0]), 0
        for o in self.options:
            o.default = o.value == self.values[0]
        await v.show(interaction)


class BoardView(discord.ui.View):
    """Only the person who ran the command (or staff) can flip pages."""

    def __init__(self, board: Board, owner_id: int | None = None, timeout: float = 900):
        super().__init__(timeout=timeout)
        self.board, self.owner_id = board, owner_id
        self.list_index, self.page = 0, 0
        self.message: discord.Message | None = None
        if len(board.lists) > 1:
            self.add_item(ListMenu(self))
        if not board.csv_text:
            self.remove_item(self.spreadsheet)
        self._sync()

    def needed(self) -> bool:
        return len(self.board.lists) > 1 or self.board.page_count(0) > 1 or bool(self.board.csv_text)

    def embed(self) -> discord.Embed:
        return board_embed(self.board, self.list_index, self.page)

    def _sync(self):
        pages = self.board.page_count(self.list_index)
        self.page = min(self.page, pages - 1)
        self.prev.disabled = self.page == 0
        self.next.disabled = self.page >= pages - 1
        self.counter.label = f"{self.page + 1}/{pages}"

    async def show(self, interaction: discord.Interaction):
        self._sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        if self.owner_id in (None, interaction.user.id) or (perms and perms.manage_roles):
            return True
        await interaction.response.send_message("Run the command yourself to browse this list.", ephemeral=True)
        return False

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def prev(self, interaction: discord.Interaction, _):
        self.page -= 1
        await self.show(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def counter(self, interaction: discord.Interaction, _):
        pass

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction: discord.Interaction, _):
        self.page += 1
        await self.show(interaction)

    @discord.ui.button(label="Spreadsheet", emoji="📄", style=discord.ButtonStyle.secondary, row=1)
    async def spreadsheet(self, interaction: discord.Interaction, _):
        name = self.board.title.split("— ")[-1].strip().replace(" ", "_").replace("[", "").replace("]", "")
        await interaction.response.send_message("Here's the full list. It opens in Excel or Google Sheets.",
                                                file=csv_file(self.board.csv_text or "", f"{name or 'list'}.csv"),
                                                ephemeral=True)


async def send_board(interaction: discord.Interaction, board: Board, ephemeral: bool = False):
    """Reply to a deferred interaction with one tidy embed."""
    view = BoardView(board, owner_id=interaction.user.id)
    if view.needed():
        view.message = await interaction.followup.send(embed=view.embed(), view=view, ephemeral=ephemeral, wait=True)
    else:
        await interaction.followup.send(embed=view.embed(), ephemeral=ephemeral)


async def post_board_to_staff(board: Board, skip_channel_id: int | None = None):
    if not STAFF_CHANNEL_ID or int(STAFF_CHANNEL_ID) == skip_channel_id:
        return
    channel = bot.get_channel(int(STAFF_CHANNEL_ID))
    if channel is None:
        log.warning("STAFF_CHANNEL_ID %s not found", STAFF_CHANNEL_ID)
        return
    view = BoardView(board, owner_id=None, timeout=86400)  # staff can browse for a day
    view.message = await channel.send(embed=view.embed(), view=view if view.needed() else None)


async def roster_autocomplete(interaction: discord.Interaction, current: str):
    cur = current.lower()
    names = [m.roblox_username for m in store.members() if cur in m.roblox_username.lower()]
    return [app_commands.Choice(name=x, value=x) for x in names[:25]]


RANK_CHOICES = [app_commands.Choice(name=r, value=r) for r in RANKS]


# ================================================================== roles ===

group_manager = (rbx.GroupManager(ROBLOX_API_KEY, ROBLOX_GROUP_ID, GROUP_ROLES, ROBLOX_IGNORE_ROLES)
                 if ROBLOX_API_KEY else None)


async def sync_group(roblox_username: str, roblox_id: int | None, rank: str | None) -> str:
    """Set the Roblox group role to match the clan rank (rank=None: they left). One short line for the reply."""
    if not group_manager:
        return ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            if not roblox_id:
                found = await rbx.lookup_usernames(s, [roblox_username])
                if roblox_username.lower() not in found:
                    return "-# Roblox group: couldn't find that Roblox account"
                roblox_id = found[roblox_username.lower()][0]
                store.update_member(roblox_username, roblox_id=roblox_id)
            result = await group_manager.sync(s, roblox_id, rank)
        return f"-# Roblox group: {result}"
    except rbx.CloudError as e:
        log.warning("Group sync failed for %s: %s", roblox_username, e)
        return f"-# ⚠️ Roblox group: {e.friendly()}"
    except Exception as e:
        log.exception("Group sync failed")
        return f"-# ⚠️ Roblox group: couldn't update ({e})"


def find_role(guild: discord.Guild, name_or_id: str) -> discord.Role | None:
    if not name_or_id:
        return None
    if name_or_id.isdigit():
        return guild.get_role(int(name_or_id))
    return discord.utils.get(guild.roles, name=name_or_id)


async def sync_roles(guild: discord.Guild, discord_id: int | None, rank: str | None) -> str:
    """Give someone gg Member + their rank's role and take away other rank roles.
    rank=None means they left the clan: take all clan roles away. Returns one short line for the reply."""
    if not discord_id:
        return "-# Discord not linked, so no roles changed"
    try:
        member = await guild.fetch_member(discord_id)
    except discord.NotFound:
        return "-# ⚠️ They're not in this Discord server, so no roles changed"
    except discord.HTTPException as e:
        return f"-# ⚠️ Couldn't look them up in Discord ({e.status})"
    managed = {r for r in [find_role(guild, MEMBER_ROLE)] + [find_role(guild, n) for n in RANK_ROLES.values()] if r}
    wanted = set()
    if rank is not None:
        wanted = {r for r in (find_role(guild, MEMBER_ROLE), find_role(guild, RANK_ROLES.get(rank, ""))) if r}
    have = set(member.roles)
    add, remove = wanted - have, (managed - wanted) & have
    if not add and not remove:
        return "-# Discord roles already correct"
    try:
        if add:
            await member.add_roles(*add, reason="[gg] roster update")
        if remove:
            await member.remove_roles(*remove, reason="[gg] roster update")
    except discord.Forbidden:
        names = ", ".join(r.name for r in add | remove)
        return (f"-# ⚠️ Couldn't change roles ({names}). Give the bot **Manage Roles** and drag its role "
                f"above these roles in Server Settings › Roles.")
    parts = []
    if add:
        parts.append("➕ " + ", ".join(r.name for r in add))
    if remove:
        parts.append("➖ " + ", ".join(r.name for r in remove))
    return "-# Discord roles: " + " · ".join(parts)


# ================================================================ the bot ===

intents = discord.Intents.default()
intents.members = True  # "Server Members Intent" in the Developer Portal


class ClanBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents,
                         member_cache_flags=discord.MemberCacheFlags.none(),
                         chunk_guilds_at_startup=False,
                         allowed_mentions=discord.AllowedMentions.none())  # never pings anyone
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.add_command(roster_group)
        self.tree.add_command(coins_group)
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.tree.clear_commands(guild=None)  # remove old global copies so nothing shows twice
        await self.tree.sync()
        if STAFF_CHANNEL_ID and WEEKLY_CHECK:
            weekly_report.start()

    async def on_ready(self):
        log.info("Logged in as %s — %d members on the roster", self.user, len(store.members()))


bot = ClanBot()


# ================================================================ /roster ===

roster_group = app_commands.Group(name="roster", description="Manage the clan roster",
                                  default_permissions=STAFF_ONLY, guild_only=True)


@roster_group.command(name="add", description="Add someone to the clan roster with their starting coins")
@app_commands.describe(roblox="Their Roblox username (the @ name)", discord_user="Their Discord account",
                       coins="Their Contribution number in game right now (their starting point)",
                       rank="Clan rank (default Member)", exempt="Skip them in coin checks?", notes="Optional note")
@app_commands.choices(rank=RANK_CHOICES)
async def roster_add(interaction: discord.Interaction, roblox: str, discord_user: Optional[discord.User] = None,
                     coins: Optional[app_commands.Range[int, 0]] = None,
                     rank: Optional[app_commands.Choice[str]] = None, exempt: bool = False, notes: str = ""):
    await interaction.response.defer()
    name, rid, warn = roblox.strip().lstrip("@"), None, ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            found = await rbx.lookup_usernames(s, [name])
        if name.lower() not in found:
            await interaction.followup.send(embed=simple(
                f"There's no Roblox account called **{name}**. Check the spelling, and use the @ username, "
                "not the display name.", RED, "❌ Not added"))
            return
        rid, name = found[name.lower()]
    except Exception:
        warn = "\n⚠️ Couldn't reach Roblox to double-check the username, so it was added as typed."
    if discord_user and store.discord_id_owner(discord_user.id):
        warn += f"\n⚠️ That Discord account is also linked to {', '.join(store.discord_id_owner(discord_user.id))}."
    rank_name = rank.value if rank else "Member"
    if not store.add_member(name, rid, discord_user.id if discord_user else None, rank_name, exempt, notes, coins):
        await interaction.followup.send(embed=simple(f"**{name}** is already on the roster.", AMBER))
        return
    lines = [f"-# {rank_name}" + (" · 🛡️ exempt" if exempt else "") +
             f" · {discord_user.mention if discord_user else 'Discord not linked'}"]
    if coins is not None:
        lines.append(f"Starting coins: **{coins:,}**\n-# their next coin check measures from here")
    else:
        lines.append("No starting coins given.\n-# their first coin check becomes their starting point "
                     "(set it now with `/roster start`)")
    lines.append(await sync_roles(interaction.guild, discord_user.id if discord_user else None, rank_name))
    group_line = await sync_group(name, rid, rank_name)
    if group_line:
        lines.append(group_line)
    lines.append(f"-# roster {len(store.members())}/100")
    await interaction.followup.send(embed=simple("\n".join(lines) + warn, GREEN, f"✅ Added {name}"))


@roster_group.command(name="start", description="Set or fix someone's starting coins")
@app_commands.describe(coins="Their Contribution number at the point they should be measured from")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_start(interaction: discord.Interaction, roblox: str, coins: app_commands.Range[int, 0]):
    ok = store.update_member(roblox, start_total=coins)
    await interaction.response.send_message(embed=simple(
        f"**{roblox}** · starting coins set to **{coins:,}**" if ok else f"**{roblox}** isn't on the roster.",
        GREEN if ok else AMBER))


@roster_group.command(name="reset", description="Delete the whole roster and every coin check (admins only)")
@app_commands.describe(confirm="Type RESET in capitals to confirm")
async def roster_reset(interaction: discord.Interaction, confirm: str):
    perms = getattr(interaction.user, "guild_permissions", None)
    if not (perms and perms.administrator):
        await interaction.response.send_message(embed=simple(
            "Only server admins can reset the roster.", RED), ephemeral=True)
        return
    if confirm != "RESET":
        await interaction.response.send_message(embed=simple(
            "Nothing deleted. To wipe the roster and all coin checks, type `RESET` in capitals.", AMBER),
            ephemeral=True)
        return
    count = len(store.members())
    store.reset_all()
    await interaction.response.send_message(embed=simple(
        f"Removed {count} members and every coin check.\n-# Add people with `/roster add`", GREEN, "🧹 Fresh start"))


@roster_group.command(name="remove", description="Remove someone from the roster and take their clan roles")
@app_commands.describe(keep_roles="Leave their Discord roles alone (default: take gg Member and rank roles away)")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_remove(interaction: discord.Interaction, roblox: str, keep_roles: bool = False):
    m = store.get_member(roblox)
    if not m:
        await interaction.response.send_message(embed=simple(f"**{roblox}** isn't on the roster.", AMBER))
        return
    await interaction.response.defer()
    store.remove_member(roblox)
    others = [o for o in store.discord_id_owner(m.discord_id)] if m.discord_id else []
    if keep_roles:
        roles = "-# Discord roles left as they were"
    elif others:  # same Discord account still on the roster under another name
        roles = f"-# Discord roles kept: that account is still on the roster as {', '.join(others)}"
    else:
        roles = await sync_roles(interaction.guild, m.discord_id, None)
    if not keep_roles:
        group_line = await sync_group(m.roblox_username, m.roblox_id, None)
        if group_line:
            roles += "\n" + group_line
    await interaction.followup.send(embed=simple(
        f"{roles}\n-# roster {len(store.members())}/100 · coin history kept", GREEN, f"🗑️ Removed {m.roblox_username}"))


@roster_group.command(name="link", description="Link a member's Discord account")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_link(interaction: discord.Interaction, roblox: str, discord_user: discord.User):
    if not store.get_member(roblox):
        await interaction.response.send_message(embed=simple(
            f"**{roblox}** isn't on the roster. Add them with `/roster add`.", AMBER))
        return
    await interaction.response.defer()
    others = [o for o in store.discord_id_owner(discord_user.id) if o.lower() != roblox.lower()]
    store.update_member(roblox, discord_id=discord_user.id)
    m = store.get_member(roblox)
    text = f"🔗 **{m.roblox_username}** is now linked to {discord_user.mention}."
    if others:
        text += f"\n⚠️ That Discord account is also linked to {', '.join(others)}."
    text += "\n" + await sync_roles(interaction.guild, discord_user.id, m.rank)
    await interaction.followup.send(embed=simple(text))


@roster_group.command(name="exempt", description="Turn coin-check exemption on or off")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_exempt(interaction: discord.Interaction, roblox: str, exempt: bool):
    ok = store.update_member(roblox, exempt=exempt)
    text = (f"🛡️ **{roblox}** is now exempt." if exempt else f"**{roblox}** is no longer exempt.") \
        if ok else f"**{roblox}** isn't on the roster."
    await interaction.response.send_message(embed=simple(text, PURPLE if ok and exempt else GREEN if ok else AMBER))


@roster_group.command(name="rank", description="Change someone's clan rank")
@app_commands.autocomplete(roblox=roster_autocomplete)
@app_commands.choices(rank=RANK_CHOICES)
async def roster_rank(interaction: discord.Interaction, roblox: str, rank: app_commands.Choice[str]):
    if not store.update_member(roblox, rank=rank.value):
        await interaction.response.send_message(embed=simple(f"**{roblox}** isn't on the roster.", AMBER))
        return
    await interaction.response.defer()
    m = store.get_member(roblox)
    roles = await sync_roles(interaction.guild, m.discord_id, rank.value)
    group_line = await sync_group(m.roblox_username, m.roblox_id, rank.value)
    await interaction.followup.send(embed=simple(
        f"**{m.roblox_username}** is now **{rank.value}**.\n{roles}" + (f"\n{group_line}" if group_line else "")))


@roster_group.command(name="note", description="Set a note on a member (leave empty to clear)")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_note(interaction: discord.Interaction, roblox: str, note: str = ""):
    ok = store.update_member(roblox, notes=note)
    await interaction.response.send_message(embed=simple(
        "📝 Note saved." if ok else f"**{roblox}** isn't on the roster.", GREEN if ok else AMBER))


@roster_group.command(name="list", description="Browse the roster (and download it as a spreadsheet file)")
async def roster_list(interaction: discord.Interaction):
    await interaction.response.defer()
    cid = store.latest_check_id()
    latest = {r.member.roblox_username: r for r in store.results(cid)} if cid else None
    await send_board(interaction, reports.roster_board(store.members(), latest, store.export_csv()))


# ================================================================= /coins ===

coins_group = app_commands.Group(name="coins", description="Monthly coin checks",
                                 default_permissions=STAFF_ONLY, guild_only=True)


def coin_board(cid: int, unknown: list[str] | None = None) -> Board:
    prev = store.previous_check_id(cid)
    return reports.coin_board(store.results(cid), store.check_label(cid),
                              store.check_label(prev) if prev else None, store.get_minimum(), unknown,
                              csv_text=store.export_csv())


@coins_group.command(name="import", description="Import this month's totals (a .csv file: username,total)")
@app_commands.describe(file="CSV with one 'roblox_username,total' per line", label="Name for this check, e.g. 'Nov 2026'")
async def coins_import(interaction: discord.Interaction, file: discord.Attachment, label: Optional[str] = None):
    await interaction.response.defer()
    if file.size > 500_000:
        await interaction.followup.send(embed=simple("That file is too big. It should be a small .csv list.", RED))
        return
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    totals = parse_totals_csv(raw)
    if not totals:
        await interaction.followup.send(embed=simple("I couldn't find any `username,total` lines in that file.", RED))
        return
    label = label or dt.date.today().strftime("%d %b %Y")
    cid, unknown = store.import_check(label, totals, str(interaction.user))
    board = coin_board(cid, unknown)
    board.header += f" · imported {len(totals)}"
    await send_board(interaction, board)
    await post_board_to_staff(board, skip_channel_id=interaction.channel_id)


@coins_group.command(name="results", description="Show the latest coin check results")
async def coins_results(interaction: discord.Interaction):
    cid = store.latest_check_id()
    if not cid:
        await interaction.response.send_message(embed=simple("No coin checks yet. Use `/coins import`.", AMBER))
        return
    await interaction.response.defer()
    await send_board(interaction, coin_board(cid))


@coins_group.command(name="set", description="Fix one member's total in the latest check")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def coins_set(interaction: discord.Interaction, roblox: str, total: app_commands.Range[int, 0]):
    cid = store.latest_check_id()
    if not cid:
        await interaction.response.send_message(embed=simple("No coin checks yet. Use `/coins import`.", AMBER))
        return
    store.set_total(cid, roblox, total)
    r = next((r for r in store.results(cid) if r.member.roblox_username.lower() == roblox.lower()), None)
    if r:
        extra = f"Now **{r.status}**" + (f" (gained {reports.n(r.gained)})" if r.gained is not None else "")
        color = {"Pass": GREEN, "Fail": RED}.get(r.status, AMBER)
    else:
        extra, color = "They're not on the roster, so it won't count until they're added.", AMBER
    await interaction.response.send_message(embed=simple(
        f"✏️ **{roblox}**: total set to {total:,} for {store.check_label(cid)}.\n{extra}", color))


@coins_group.command(name="status", description="See one member's coin history")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def coins_status(interaction: discord.Interaction, roblox: str):
    m = store.get_member(roblox)
    if not m:
        await interaction.response.send_message(embed=simple(f"**{roblox}** isn't on the roster.", AMBER))
        return
    title, desc, color = reports.member_status(m, store.history(m.roblox_username), store.get_minimum())
    await interaction.response.send_message(embed=simple(desc, color, title))


@coins_group.command(name="minimum", description="Change the monthly minimum (default 10,000)")
async def coins_minimum(interaction: discord.Interaction, amount: app_commands.Range[int, 0]):
    store.set_minimum(amount)
    await interaction.response.send_message(embed=simple(
        f"Monthly minimum is now **{amount:,}**. Results use it straight away."))


@coins_group.command(name="undo", description="Delete the most recent coin check import")
@app_commands.describe(confirm="Type the check's name exactly to confirm")
async def coins_undo(interaction: discord.Interaction, confirm: str):
    cid = store.latest_check_id()
    if not cid:
        await interaction.response.send_message(embed=simple("There are no coin checks to undo.", AMBER))
        return
    label = store.check_label(cid)
    if confirm.strip() != label:
        await interaction.response.send_message(embed=simple(
            f"Nothing deleted. To delete the latest check, type its name exactly: `{label}`", AMBER))
        return
    store.delete_check(cid)
    await interaction.response.send_message(embed=simple(f"🗑️ Deleted the coin check **{label}**."))


# =================================================================== /help ===

class HelpMenu(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Overview", value="__overview", emoji="📖", default=True)]
        for c in help_text.COMMANDS[:24]:
            options.append(discord.SelectOption(
                label=c.name, value=c.name, description=c.short[:100],
                emoji=help_text.CATEGORY_EMOJI[c.category]))
        super().__init__(placeholder="Pick a command…", options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        for o in self.options:
            o.default = o.value == choice
        if choice == "__overview":
            embed = discord.Embed(title="📖 [gg] bot commands", description=help_text.overview(), color=reports.BLURPLE)
        else:
            embed = discord.Embed(title=choice, description=help_text.detail(choice), color=reports.BLURPLE)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.add_item(HelpMenu())


@bot.tree.command(name="help", description="See every command and how to use it")
@app_commands.guild_only()
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 [gg] bot commands", description=help_text.overview(), color=reports.BLURPLE)
    await interaction.response.send_message(embed=embed, view=HelpView(), ephemeral=True)


# ============================================================== /mystatus ===

@bot.tree.command(name="mystatus", description="See your coin check results, and how much you still need")
@app_commands.describe(current="Optional: your Contribution number in game right now, to see how much you still need")
@app_commands.guild_only()
async def mystatus(interaction: discord.Interaction, current: Optional[app_commands.Range[int, 0]] = None):
    m = store.member_by_discord(interaction.user.id)
    if not m:
        await interaction.response.send_message(embed=simple(
            "I can't find you on the clan roster. If you're in the clan, ask a staff member to link your "
            "Discord with `/roster link`.", AMBER), ephemeral=True)
        return
    title, desc, color = reports.member_status(m, store.history(m.roblox_username), store.get_minimum(), current)
    await interaction.response.send_message(embed=simple(desc, color, title), ephemeral=True)


# ================================================================= /update ===

@bot.tree.command(name="update", description="Download the newest bot code from GitHub and restart")
@app_commands.default_permissions(manage_roles=True)
@app_commands.guild_only()
async def update(interaction: discord.Interaction):
    if not GITHUB_REPO:
        await interaction.response.send_message(embed=simple(
            "Updates aren't set up yet. Add a `GITHUB_REPO` setting (like `yourname/gg-clan-bot`) "
            "on Wispbyte's Environment page.", AMBER), ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        result = await asyncio.to_thread(updater.sync, GITHUB_REPO, GITHUB_BRANCH, GITHUB_TOKEN)
    except Exception as e:
        log.exception("Update failed")
        await interaction.followup.send(embed=simple(
            f"Couldn't download the update, so nothing changed and the bot keeps running.\n`{e}`", RED, "⚠️ Update failed"))
        return
    if not result.changed:
        await interaction.followup.send(embed=simple(
            f"Already running the newest version (`{result.new_sha[:7]}`).", GREEN, "✅ Up to date"))
        return
    e = simple(f"**{result.message or 'New version'}**\n\nRestarting now, back in a few seconds.", GREEN, "⬆️ Updating")
    e.add_field(name="Changed files", value=", ".join(f"`{f}`" for f in result.changed)[:1024], inline=False)
    e.add_field(name="Version", value=f"`{result.old_sha[:7]}` → `{result.new_sha[:7]}`", inline=False)
    await interaction.followup.send(embed=e)
    log.info("Updated to %s, restarting", result.new_sha[:7])
    await asyncio.sleep(2)
    os.execv(sys.executable, [sys.executable, str(HERE / "main.py")])


# ================================================================== /check ===

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
    await send_board(interaction, await build_check(interaction.guild, what.value if what else "all"))


@tasks.loop(time=dt.time(hour=REPORT_HOUR_UTC, tzinfo=dt.timezone.utc))
async def weekly_report():
    if WEEKDAYS[dt.datetime.now(dt.timezone.utc).weekday()] != REPORT_WEEKDAY:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    board = await build_check(guild, "all")
    board.title = "📋 Weekly — " + board.title
    await post_board_to_staff(board)


@weekly_report.before_loop
async def _wait_ready():
    await bot.wait_until_ready()


def run():
    log.info("Starting bot, code version %s", updater.current_version()[:7])
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    run()
