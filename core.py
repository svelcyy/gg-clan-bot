"""Everything the command files share: settings, the bot itself, the database, and helpers for
embeds, role syncing and alerts. Commands live in the commands folder, one file each.
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

# Several of these imports aren't used here: command files get them through `from core import *`.
import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import reports
import roblox as rbx
from reports import AMBER, BLURPLE, GREEN, PURPLE, RED, Board, esc
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
# Booster custom roles: who can see and approve (role names or IDs, plus server admins) and where request channels go
CUSTOMROLE_APPROVERS = [r.strip() for r in env("CUSTOMROLE_APPROVERS", "Clan Officer,Clan Admin,Head Administrator").split(",")
                        if r.strip()]
CUSTOMROLE_CATEGORY_ID = env("CUSTOMROLE_CATEGORY_ID")
# Reminders: who to ping and where. REMINDER_PING is a user ID or a role ID (right-click > Copy ID).
REMINDER_CHANNEL_ID = env("REMINDER_CHANNEL_ID") or STAFF_CHANNEL_ID
REMINDER_PING = env("REMINDER_PING")
COIN_REMINDER = env("COIN_REMINDER", "on").lower() in ("on", "yes", "true", "1")
COIN_REMINDER_DAY = int(env("COIN_REMINDER_DAY", "1"))          # day of the month
REMINDER_HOUR = int(env("REMINDER_HOUR", "10"))                 # in REMINDER_TIMEZONE
REMINDER_TIMEZONE = env("REMINDER_TIMEZONE", "America/New_York")
RESTART_REMINDER_DAYS = float(env("RESTART_REMINDER_DAYS", "0"))  # 0 = off; e.g. 14 if the host stops the bot every 2 weeks
RESTART_REMINDER_HOURS_BEFORE = float(env("RESTART_REMINDER_HOURS_BEFORE", "12"))


def reminder_tz() -> dt.tzinfo:
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(REMINDER_TIMEZONE)
    except Exception:
        return dt.timezone(dt.timedelta(hours=-5))   # New York winter time if the time zone data is missing

def read_version() -> str:
    try:
        return (HERE / "VERSION").read_text().strip() or "?"
    except OSError:
        return "?"


def version_key(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))


def changes_since(old: str, new: str) -> list[tuple[str, str]]:
    """[(version, what changed)] for versions newer than old, up to new, newest first."""
    out = []
    try:
        lines = (HERE / "CHANGELOG.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        if "|" not in line or line.startswith("#"):
            continue
        v, text = (p.strip() for p in line.split("|", 1))
        if version_key(old) < version_key(v) <= version_key(new):
            out.append((v, text))
    return out


RUNNING_VERSION = read_version()   # the version this process started with
STARTED_AT = dt.datetime.now(dt.timezone.utc)


def nice_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = [f"{days}d"] if days else []
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def memory_mb() -> str:
    try:  # Linux hosts like Wispbyte
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS:"):
                return f"{int(line.split()[1]) / 1024:.0f} MB"
    except OSError:
        pass
    return "—"
BOT_STATUS = env("BOT_STATUS", "SIGNUPS OPEN!!")      # default text under the bot's name (/status changes it)
MOBILE_STATUS = env("MOBILE_STATUS", "off").lower() in ("on", "yes", "true", "1")
GITHUB_REPO = env("GITHUB_REPO", "svelcyy/gg-clan-bot")
GITHUB_BRANCH = env("GITHUB_BRANCH", "main")
GITHUB_TOKEN = env("GITHUB_TOKEN")          # only needed if the repository is private

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
STAFF_ONLY = discord.Permissions(manage_roles=True)


class NotAdmin(app_commands.CheckFailure):
    pass


def is_admin(user) -> bool:
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and perms.administrator)


def _is_admin(interaction: discord.Interaction) -> bool:
    if is_admin(interaction.user):
        return True
    raise NotAdmin()


admin_only = app_commands.check(_is_admin)   # Clan Manager commands: needs the Administrator permission

store = Store(DB_PATH)


# ================================================================ boards ===
# Leaderboard-style embed: a menu to switch lists, ◀ ▶ to change page,
# and a button that hands out the full list as a spreadsheet file.

def simple(text: str, color: int = GREEN, title: str | None = None) -> discord.Embed:
    return discord.Embed(title=title, description=text, color=color)


def not_on_roster(name: str, extra: str = "") -> discord.Embed:
    return simple(f"**{esc(name)}** isn't on the roster.{extra}", AMBER)


async def wait_ready():
    """Background tasks wait for the bot to log in before their first run."""
    await bot.wait_until_ready()


def csv_file(text: str, name: str) -> discord.File:
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=name)


def board_embed(board: Board, list_index: int = 0, page: int = 0) -> discord.Embed:
    e = discord.Embed(title=board.title, description=board.render(list_index, page)[:4096], color=board.color)
    e.set_footer(text=board.footer(list_index, page))
    return e


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
    """The person who ran the command (or staff) flips the shared pages; anyone else gets a private copy."""

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
        # Someone else clicked a shared board: give them their own private copy to browse.
        copy = BoardView(self.board, owner_id=interaction.user.id)
        copy.list_index, copy.page = self.list_index, self.page
        copy._sync()
        await interaction.response.send_message(embed=copy.embed(), view=copy, ephemeral=True)
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

    @discord.ui.button(label="Spreadsheet", style=discord.ButtonStyle.secondary, row=1)
    async def spreadsheet(self, interaction: discord.Interaction, _):
        name = "".join(ch if ch.isascii() and ch.isalnum() else "_" for ch in self.board.title)
        name = "_".join(p for p in name.split("_") if p)
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
        embed.timestamp = embed.timestamp or discord.utils.utcnow()
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.exception("Couldn't post to the roster log channel")


_last_alert: dict[str, float] = {}


async def staff_alert(key: str, title: str, text: str, every_hours: float = 6):
    """Tell staff something is broken, at most once every few hours per problem (so it never spams)."""
    now = asyncio.get_running_loop().time()
    if now - _last_alert.get(key, -1e9) < every_hours * 3600:
        return
    _last_alert[key] = now
    channel_id = STAFF_CHANNEL_ID or ROSTER_LOG_CHANNEL_ID
    channel = bot.get_channel(int(channel_id)) if channel_id else None
    if channel is None:
        log.warning("Alert (%s) but no staff channel: %s", title, text)
        return
    e = simple(text, RED, f"⚠️ {title}")
    e.set_footer(text="You won't get this alert again for a few hours")
    e.timestamp = discord.utils.utcnow()
    try:
        await channel.send(embed=e, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.exception("Couldn't post an alert")


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
        if e.status in (401, 403):
            await staff_alert("roblox-key", "Roblox Group Syncing Is Failing",
                              "The bot couldn't change Roblox group roles because Roblox refused its API key.\n\n"
                              "Usually this means the **Open Cloud API key expired** or Wispbyte's **IP address "
                              "changed**. Open the key on create.roblox.com, check it's active, has Groups read + "
                              "write for [gg] Clan, and that its IP list includes the server's address.\n\n"
                              "Discord roles still work. Run `/roster sync` once it's fixed to catch up.")
        return f"⚠️ {e.friendly()}"
    except Exception as e:
        log.exception("Group sync failed")
        await staff_alert("roblox-down", "Can't Reach Roblox",
                          f"The bot couldn't reach Roblox to update group roles ({e}). This is usually Roblox "
                          "having problems and fixes itself. Run `/roster sync` later to catch up.")
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
        await staff_alert("discord-roles", "Discord Roles Are Failing",
                          f"The bot isn't allowed to change **{names}**. In Server Settings › Roles, make sure "
                          "the bot has **Manage Roles** and drag its role **above** the clan roles.")
        return (f"⚠️ Couldn't change {names}. Give the bot **Manage Roles** and drag its role "
                f"above these roles in Server Settings › Roles.")
    parts = []
    if add:
        parts.append("➕ " + ", ".join(r.name for r in add))
    if remove:
        parts.append("➖ " + ", ".join(r.name for r in remove))
    return "\n".join(parts)


def handle(user: discord.abc.User) -> str:
    return f"@{esc(user.name)}"


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
        e.add_field(name="Note", value="\n".join(notes), inline=False)
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
SHOW_STATUS = env("PRESENCE_INTENT", "off").lower() in ("on", "yes", "true", "1")
intents.presences = SHOW_STATUS  # "Presence Intent" in the Developer Portal: only turn on after enabling it there


def status_activity() -> discord.CustomActivity | None:
    text = store.get_setting("status", BOT_STATUS)
    return discord.CustomActivity(name=text) if text else None


# Command files (in the commands folder) add themselves to these when they're imported.
GROUPS: list = []             # slash command groups like /roster and /coins
PERSISTENT_VIEWS: list = []   # button panels that must keep working after a restart
BACKGROUND_TASKS: list = []   # (task, function that says whether to start it)


class ClanBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents,
                         member_cache_flags=discord.MemberCacheFlags.none(),
                         chunk_guilds_at_startup=False,
                         allowed_mentions=discord.AllowedMentions.none(),  # never pings anyone
                         status=discord.Status.online,
                         activity=status_activity())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        for group in GROUPS:
            self.tree.add_command(group)
        for view in PERSISTENT_VIEWS:
            self.add_view(view())   # keeps buttons like Approve / Deny working after restarts
        # Commands are registered globally: that's what gives the bot Discord's "Supports Slash Commands"
        # badge. They're all server-only, so they still don't show up in DMs.
        guild = discord.Object(id=GUILD_ID)
        self.tree.clear_commands(guild=guild)   # remove the old server-only copies so nothing shows twice
        await self.tree.sync(guild=guild)
        await self.tree.sync()
        for task, should_run in BACKGROUND_TASKS:
            if should_run():
                task.start()

    async def on_ready(self):
        log.info("Logged in as %s — %d members on the roster", self.user, len(store.members()))
        await load_names()


bot = ClanBot()


def _server_name(discord_id: int) -> str | None:
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(discord_id) if guild else None
    return discord.utils.escape_markdown(member.name) if member else None   # their @handle, not display name


reports.name_lookup = _server_name


async def load_names():
    """Make sure the bot knows the roster's Discord names (it doesn't load the whole server at startup)."""
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    ids = [m.discord_id for m in store.members() if m.discord_id and guild.get_member(m.discord_id) is None]
    for i in range(0, len(ids), 100):
        try:
            await guild.query_members(user_ids=ids[i:i + 100], cache=True)
        except Exception:
            log.exception("Couldn't load Discord names")
            return


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, NotAdmin):
        text = "Only the Clan Manager (server admins) can use this command."
    elif isinstance(error, app_commands.CheckFailure):
        text = "You don't have permission to use this command."
    else:
        name = interaction.command.qualified_name if interaction.command else "?"
        log.error("Command /%s failed", name, exc_info=error)
        cause = getattr(error, "original", error)
        await staff_alert(f"cmd:{name}", f"/{name} Hit an Error",
                          f"Someone ran `/{name}` and it failed:\n`{type(cause).__name__}: {str(cause)[:300]}`\n\n"
                          "If this keeps happening, send this message to whoever looks after the bot.")
        text = "Something went wrong running that command. Try again, or tell the Clan Manager."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=simple(text, RED), ephemeral=True)
        else:
            await interaction.response.send_message(embed=simple(text, RED), ephemeral=True)
    except discord.HTTPException:
        pass
