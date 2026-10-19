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
from storage import RANKS, Store, match_totals, parse_totals_csv

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
ROSTER_LOG_CHANNEL_ID = env("ROSTER_LOG_CHANNEL_ID") or STAFF_CHANNEL_ID   # where "new member" alerts go
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
BOT_STATUS = env("BOT_STATUS", "Checking coins...")      # the text under the bot's name
MOBILE_STATUS = env("MOBILE_STATUS", "on").lower() in ("on", "yes", "true", "1")
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


async def post_alert(embed: discord.Embed, skip_channel_id: int | None = None):
    """Post a card to the roster log channel. Mentions in it never ping anyone."""
    if not ROSTER_LOG_CHANNEL_ID or int(ROSTER_LOG_CHANNEL_ID) == (skip_channel_id or 0):
        return
    channel = bot.get_channel(int(ROSTER_LOG_CHANNEL_ID))
    if channel is None:
        log.warning("ROSTER_LOG_CHANNEL_ID %s not found", ROSTER_LOG_CHANNEL_ID)
        return
    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.exception("Couldn't post to the roster log channel")


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
    """Set the Roblox group role to match the clan rank (rank=None: they left).
    Returns the text for the reply's "Roblox Group" field, or "" if group syncing isn't set up."""
    if not group_manager:
        return ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            if not roblox_id:
                found = await rbx.lookup_usernames(s, [roblox_username])
                if roblox_username.lower() not in found:
                    return "⚠️ Couldn't find that Roblox account."
                roblox_id = found[roblox_username.lower()][0]
                store.update_member(roblox_username, roblox_id=roblox_id)
            result = await group_manager.sync(s, roblox_id, rank)
        return result
    except rbx.CloudError as e:
        log.warning("Group sync failed for %s: %s", roblox_username, e)
        return f"⚠️ {e.friendly()}"
    except Exception as e:
        log.exception("Group sync failed")
        return f"⚠️ Couldn't update the group ({e})."


def find_role(guild: discord.Guild, name_or_id: str) -> discord.Role | None:
    if not name_or_id:
        return None
    if name_or_id.isdigit():
        return guild.get_role(int(name_or_id))
    return discord.utils.get(guild.roles, name=name_or_id)


async def sync_roles(guild: discord.Guild, discord_id: int | None, rank: str | None) -> str:
    """Give someone gg Member + their rank's role and take away other rank roles.
    rank=None means they left the clan: take all clan roles away. Returns the text for the "Discord Roles" field."""
    if not discord_id:
        return "Discord not linked, so no roles were changed."
    try:
        member = await guild.fetch_member(discord_id)
    except discord.NotFound:
        return "⚠️ They're not in this Discord server, so no roles were changed."
    except discord.HTTPException as e:
        return f"⚠️ Couldn't look them up in Discord ({e.status})."
    managed = {r for r in [find_role(guild, MEMBER_ROLE)] + [find_role(guild, n) for n in RANK_ROLES.values()] if r}
    wanted = set()
    if rank is not None:
        wanted = {r for r in (find_role(guild, MEMBER_ROLE), find_role(guild, RANK_ROLES.get(rank, ""))) if r}
    have = set(member.roles)
    add, remove = wanted - have, (managed - wanted) & have
    if not add and not remove:
        return "Already correct."
    try:
        if add:
            await member.add_roles(*add, reason="[gg] roster update")
        if remove:
            await member.remove_roles(*remove, reason="[gg] roster update")
    except discord.Forbidden:
        names = ", ".join(r.name for r in add | remove)
        return (f"⚠️ Couldn't change {names}. Give the bot **Manage Roles** and drag its role "
                f"above these roles in Server Settings › Roles.")
    parts = []
    if add:
        parts.append("➕ " + ", ".join(r.name for r in add))
    if remove:
        parts.append("➖ " + ", ".join(r.name for r in remove))
    return "\n".join(parts)


def update_embed(title: str, description: str = "", color: int = GREEN, fields: list[tuple[str, str, bool]] = (),
                 discord_roles: str | None = None, group: str = "", footer: str = "", notes: list[str] = ()) -> discord.Embed:
    """A tidy confirmation card: labelled fields, then role changes, then any notes."""
    e = discord.Embed(title=title, description=description or None, color=color)
    for name, value, inline in fields:
        e.add_field(name=name, value=value or "—", inline=inline)
    if discord_roles is not None:
        e.add_field(name="Discord Roles", value=discord_roles, inline=False)
    if group:
        e.add_field(name="Roblox Group", value=group, inline=False)
    if notes:
        e.add_field(name="⚠️ Note", value="\n".join(notes), inline=False)
    if footer:
        e.set_footer(text=footer)
    return e


# ================================================================ the bot ===

if MOBILE_STATUS:
    # Shows the bot with the phone icon by telling Discord it's connecting from the iOS app.
    # Unofficial trick: if Discord ever stops allowing it, the bot simply shows as normal online.
    from discord.gateway import DiscordWebSocket

    _send_as_json = DiscordWebSocket.send_as_json

    async def _send_as_mobile(self, data, *args, **kwargs):
        if isinstance(data, dict) and data.get("op") == DiscordWebSocket.IDENTIFY:
            props = data.get("d", {}).get("properties")
            if isinstance(props, dict):
                props.update({"os": "iOS", "browser": "Discord iOS", "device": "iPhone"})
        return await _send_as_json(self, data, *args, **kwargs)

    DiscordWebSocket.send_as_json = _send_as_mobile

intents = discord.Intents.default()
intents.members = True  # "Server Members Intent" in the Developer Portal


class ClanBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents,
                         member_cache_flags=discord.MemberCacheFlags.none(),
                         chunk_guilds_at_startup=False,
                         allowed_mentions=discord.AllowedMentions.none(),  # never pings anyone
                         status=discord.Status.online,
                         activity=discord.CustomActivity(name=BOT_STATUS) if BOT_STATUS else None)
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
                       coins="Their Contribution number in game right now (their starting point). Leave empty for 0",
                       rank="Clan rank (default Member)", exempt="Skip them in coin checks?", notes="Optional note")
@app_commands.choices(rank=RANK_CHOICES)
async def roster_add(interaction: discord.Interaction, roblox: str, discord_user: Optional[discord.User] = None,
                     coins: Optional[app_commands.Range[int, 0]] = None,
                     rank: Optional[app_commands.Choice[str]] = None, exempt: bool = False, notes: str = ""):
    await interaction.response.defer(ephemeral=True)  # only the person who ran it sees the reply
    name, rid, notes_out = roblox.strip().lstrip("@"), None, []
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
        notes_out.append("Couldn't reach Roblox to double-check the username, so it was added as typed.")
    if discord_user and store.discord_id_owner(discord_user.id):
        notes_out.append(f"That Discord account is also linked to {', '.join(store.discord_id_owner(discord_user.id))}.")
    rank_name = rank.value if rank else "Member"
    coins_given = coins is not None
    coins = coins if coins_given else 0   # no number given: start from 0
    if not store.add_member(name, rid, discord_user.id if discord_user else None, rank_name, exempt, notes, coins):
        await interaction.followup.send(embed=simple(f"**{name}** is already on the roster.", AMBER))
        return
    roles = await sync_roles(interaction.guild, discord_user.id if discord_user else None, rank_name)
    group = await sync_group(name, rid, rank_name)
    desc = ("Their next coin check will measure from their starting coins." if coins_given else
            "No coins given, so they start from **0**. Change it any time with `/roster start`.")
    info = [("Rank", rank_name + (" · 🛡️ Exempt" if exempt else ""), True),
            ("Discord", discord_user.mention if discord_user else "Not linked", True),
            ("Starting Coins", f"{coins:,}" + ("" if coins_given else " (default)"), True)]
    footer = f"Roster: {len(store.members())}/100"
    await interaction.followup.send(embed=update_embed(
        f"✅ Added {name}", desc, fields=info, discord_roles=roles, group=group, notes=notes_out, footer=footer),
        ephemeral=True)
    alert = update_embed(f"🆕 New Clan Member: {name}", f"Added by {interaction.user.mention}.", fields=info,
                         footer=footer)
    alert.timestamp = discord.utils.utcnow()
    await post_alert(alert, skip_channel_id=None)


@roster_group.command(name="start", description="Set or fix someone's starting coins")
@app_commands.describe(coins="Their Contribution number at the point they should be measured from")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_start(interaction: discord.Interaction, roblox: str, coins: app_commands.Range[int, 0]):
    ok = store.update_member(roblox, start_total=coins)
    await interaction.response.send_message(embed=simple(
        f"**{roblox}**'s starting coins are now **{coins:,}**." if ok else f"**{roblox}** isn't on the roster.",
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
        f"Removed {count} members and every coin check.\nAdd people with `/roster add`.", GREEN, "🧹 Fresh Start"))


@roster_group.command(name="remove", description="Remove someone from the roster and take their clan roles")
@app_commands.describe(keep_roles="Leave their Discord roles alone (default: take gg Member and rank roles away)")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_remove(interaction: discord.Interaction, roblox: str, keep_roles: bool = False):
    m = store.get_member(roblox)
    if not m:
        await interaction.response.send_message(embed=simple(f"**{roblox}** isn't on the roster.", AMBER),
                                                ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)  # only the person who ran it sees the reply
    store.remove_member(roblox)
    others = [o for o in store.discord_id_owner(m.discord_id)] if m.discord_id else []
    if keep_roles:
        roles, group = "Left as they were.", ""
    else:
        roles = (f"Kept, because that account is still on the roster as {', '.join(others)}." if others
                 else await sync_roles(interaction.guild, m.discord_id, None))
        group = await sync_group(m.roblox_username, m.roblox_id, None)
    footer = f"Roster: {len(store.members())}/100"
    await interaction.followup.send(embed=update_embed(
        f"🗑️ Removed {m.roblox_username}", "Their coin history is kept.", discord_roles=roles, group=group,
        footer=footer), ephemeral=True)
    alert = update_embed(f"👋 Left the Clan: {m.roblox_username}", f"Removed by {interaction.user.mention}.",
                         color=RED, fields=[("Rank", m.rank, True),
                                            ("Discord", f"<@{m.discord_id}>" if m.discord_id else "Not linked", True)],
                         footer=footer)
    alert.timestamp = discord.utils.utcnow()
    await post_alert(alert)


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
    roles = await sync_roles(interaction.guild, discord_user.id, m.rank)
    await interaction.followup.send(embed=update_embed(
        f"🔗 Linked {m.roblox_username}", f"Now linked to {discord_user.mention}.",
        fields=[("Rank", m.rank, True)], discord_roles=roles,
        notes=[f"That Discord account is also linked to {', '.join(others)}."] if others else []))


@roster_group.command(name="exempt", description="Turn coin-check exemption on or off")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_exempt(interaction: discord.Interaction, roblox: str, exempt: bool):
    ok = store.update_member(roblox, exempt=exempt)
    text = (f"🛡️ **{roblox}** is now exempt from coin checks." if exempt
            else f"**{roblox}** is no longer exempt from coin checks.") \
        if ok else f"**{roblox}** isn't on the roster."
    await interaction.response.send_message(embed=simple(text, PURPLE if ok and exempt else GREEN if ok else AMBER))


@roster_group.command(name="rank", description="Change someone's clan rank")
@app_commands.autocomplete(roblox=roster_autocomplete)
@app_commands.choices(rank=RANK_CHOICES)
async def roster_rank(interaction: discord.Interaction, roblox: str, rank: app_commands.Choice[str]):
    before = store.get_member(roblox)
    if not before or not store.update_member(roblox, rank=rank.value):
        await interaction.response.send_message(embed=simple(f"**{roblox}** isn't on the roster.", AMBER),
                                                ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)  # only the person who ran it sees the reply
    m = store.get_member(roblox)
    roles = await sync_roles(interaction.guild, m.discord_id, rank.value)
    group = await sync_group(m.roblox_username, m.roblox_id, rank.value)
    await interaction.followup.send(embed=update_embed(
        f"🎖️ {m.roblox_username} is now {rank.value}", discord_roles=roles, group=group), ephemeral=True)
    if before.rank != rank.value:
        old_i = RANKS.index(before.rank) if before.rank in RANKS else len(RANKS)
        promoted = RANKS.index(rank.value) < old_i   # RANKS goes Leader, Admin, Officer, Member
        alert = update_embed(f"{'⬆️ Promoted' if promoted else '⬇️ Demoted'}: {m.roblox_username}",
                             f"Changed by {interaction.user.mention}.", color=GREEN if promoted else AMBER,
                             fields=[("Rank", f"{before.rank} → **{rank.value}**", True),
                                     ("Discord", f"<@{m.discord_id}>" if m.discord_id else "Not linked", True)])
        alert.timestamp = discord.utils.utcnow()
        await post_alert(alert)


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


def preview_embed(label: str, p: dict) -> discord.Embed:
    results = store.preview(p["matched"])
    passed = sum(r.status == "Pass" for r in results)
    failed = sum(r.status == "Fail" for r in results)
    new = sum(r.status == "Baseline" for r in results)
    e = discord.Embed(title=f"🪙 Coin Check Preview — {label}", color=reports.AMBER,
                      description="Nothing is saved until you click **Save**.")
    e.add_field(name="Matched", value=f"{len(p['matched'])} of {len(store.members())} on the roster", inline=True)
    e.add_field(name="Would Pass", value=str(passed), inline=True)
    e.add_field(name="Would Fail", value=str(failed) + (f" · 🆕 {new}" if new else ""), inline=True)
    if p["renames"]:
        e.add_field(name=f"🔁 Changed Roblox Username ({len(p['renames'])})",
                    value=names_list([f"{o} → {n}" for o, n in p["renames"]]) +
                    "\nTheir roster entry, Discord link and history will move to the new name.", inline=False)
    if p["missing"]:
        e.add_field(name=f"❓ Not in This Import ({len(p['missing'])})", value=names_list(p["missing"]), inline=False)
    if p["unknown"]:
        e.add_field(name=f"⚠️ Not on the Roster ({len(p['unknown'])})", value=names_list(p["unknown"]) +
                    "\nTheir numbers are kept in case you add them later.", inline=False)
    if not (p["renames"] or p["missing"] or p["unknown"]):
        e.add_field(name="✅ Everything Matches", value="Every roster member is in this import.", inline=False)
    e.set_footer(text=f"{p['count']} lines read")
    return e


class ImportConfirm(discord.ui.View):
    def __init__(self, owner_id: int, label: str, prepared: dict):
        super().__init__(timeout=900)
        self.owner_id, self.label, self.p = owner_id, label, prepared
        self.done = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("Only the person who started this import can save it.", ephemeral=True)
        return False

    @discord.ui.button(label="Save", emoji="✅", style=discord.ButtonStyle.success)
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
        totals.update(self.p["unknown_totals"])
        cid, unknown = store.import_check(self.label, totals, str(interaction.user))
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=simple(f"Saved **{self.label}**." + (f" Updated {len(renamed)} renamed Roblox account(s)." if renamed
                         else ""), GREEN, "✅ Coin Check Saved"), view=self)
        board = coin_board(cid, unknown)
        board.header += f" · Imported {len(totals)}"
        await send_board(interaction, board)           # posted in this channel for everyone
        await post_board_to_staff(board, skip_channel_id=interaction.channel_id)

    @discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _):
        self.done = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=simple("Nothing was saved.", AMBER, "❌ Import Cancelled"),
                                                view=self)


async def show_preview(interaction: discord.Interaction, text: str, label: str | None):
    label = (label or "").strip() or dt.date.today().strftime("%d %b %Y")
    prepared = await prepare_import(text)
    if prepared is None:
        await interaction.followup.send(embed=simple(
            "I couldn't find any lines like `username 875128` in that. Put one person per line: their Roblox "
            "username, then their Contribution number.", RED), ephemeral=True)
        return
    await interaction.followup.send(embed=preview_embed(label, prepared),
                                    view=ImportConfirm(interaction.user.id, label, prepared), ephemeral=True)


class ImportModal(discord.ui.Modal, title="Import Coin Check"):
    label_input = discord.ui.TextInput(label="Name for this check", placeholder="e.g. Nov 2026", required=False,
                                       max_length=40)
    totals_input = discord.ui.TextInput(label="Paste totals: one per line", style=discord.TextStyle.paragraph,
                                        placeholder="pramishp4 875128\n2pfaltac 365000\n…", max_length=4000)

    def __init__(self, label: str | None):
        super().__init__()
        if label:
            self.label_input.default = label

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await show_preview(interaction, self.totals_input.value, self.label_input.value)


@coins_group.command(name="import", description="Import this month's totals: paste them, or attach a file")
@app_commands.describe(file="Optional .csv/.txt with one 'username total' per line. Leave empty to paste instead",
                       label="Name for this check, e.g. 'Nov 2026'")
async def coins_import(interaction: discord.Interaction, file: Optional[discord.Attachment] = None,
                       label: Optional[str] = None):
    if file is None:
        await interaction.response.send_modal(ImportModal(label))
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    if file.size > 500_000:
        await interaction.followup.send(embed=simple("That file is too big. It should be a small list.", RED),
                                        ephemeral=True)
        return
    await show_preview(interaction, (await file.read()).decode("utf-8-sig", errors="replace"), label)


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
