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

import reports
import roblox as rbx
import updater
from reports import AMBER, GREEN, PURPLE, RED, Page
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
STAFF_CHANNEL_ID = env("STAFF_CHANNEL_ID") or env("REPORT_CHANNEL_ID")
ROBLOX_GROUP_ID = int(env("ROBLOX_GROUP_ID", "16909817"))
ROBLOX_MIN_RANK = int(env("ROBLOX_MIN_RANK", "75"))
ROBLOX_IGNORE_ROLES = {r.strip().lower() for r in env("ROBLOX_IGNORE_ROLES", "UGC").split(",") if r.strip()}
WEEKLY_CHECK = env("WEEKLY_CHECK", "on").lower() in ("on", "yes", "true", "1")
REPORT_WEEKDAY = env("REPORT_WEEKDAY", "sunday").lower()
REPORT_HOUR_UTC = int(env("REPORT_HOUR_UTC", "17"))
DB_PATH = env("DB_PATH", str(HERE / "clan.db"))
GITHUB_REPO = env("GITHUB_REPO")            # e.g. yourname/gg-clan-bot
GITHUB_BRANCH = env("GITHUB_BRANCH", "main")
GITHUB_TOKEN = env("GITHUB_TOKEN")          # only needed if the repository is private

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
STAFF_ONLY = discord.Permissions(manage_roles=True)

store = Store(DB_PATH)
if (HERE / "seed_roster.csv").exists():
    seeded = store.seed_if_empty(
        (HERE / "seed_roster.csv").read_text(encoding="utf-8"),
        (HERE / "seed_totals.csv").read_text(encoding="utf-8") if (HERE / "seed_totals.csv").exists() else None,
        "18 Oct 2026")
    if seeded:
        log.info("Loaded the starting roster and the 18 Oct 2026 totals")


# ============================================================ embeds/pages ===

def page_embed(page: Page, index: int = 0, count: int = 1) -> discord.Embed:
    desc = "\n".join(page.lines)
    if page.note:
        desc += f"\n\n*{page.note}*"
    e = discord.Embed(title=page.title, description=desc[:4096], color=page.color)
    for name, value, inline in page.fields:
        e.add_field(name=name, value=value[:1024] or "—", inline=inline)
    footer = page.section if count == 1 else f"{page.section} · page {index + 1} of {count}"
    e.set_footer(text=footer)
    return e


def simple(text: str, color: int = GREEN, title: str | None = None) -> discord.Embed:
    return discord.Embed(title=title, description=text, color=color)


class SectionMenu(discord.ui.Select):
    def __init__(self, paginator: "Paginator"):
        self.paginator = paginator
        seen, options = set(), []
        for i, p in enumerate(paginator.pages):
            if p.section not in seen and len(options) < 25:
                seen.add(p.section)
                options.append(discord.SelectOption(label=p.section[:100], value=str(i)))
        super().__init__(placeholder="Jump to a section…", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        self.paginator.index = int(self.values[0])
        await self.paginator.show(interaction)


class Paginator(discord.ui.View):
    """◀ ▶ buttons plus a section menu. Only the person who ran the command (or staff) can flip pages."""

    def __init__(self, pages: list[Page], owner_id: int | None = None, timeout: float = 900):
        super().__init__(timeout=timeout)
        self.pages, self.owner_id, self.index = pages, owner_id, 0
        self.message: discord.Message | None = None
        if len({p.section for p in pages}) > 1:
            self.add_item(SectionMenu(self))
        self._sync()

    def embed(self) -> discord.Embed:
        return page_embed(self.pages[self.index], self.index, len(self.pages))

    def _sync(self):
        last = len(self.pages) - 1
        self.first.disabled = self.prev.disabled = self.index == 0
        self.next.disabled = self.last.disabled = self.index == last
        self.counter.label = f"{self.index + 1} / {len(self.pages)}"

    async def show(self, interaction: discord.Interaction):
        self._sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        if self.owner_id in (None, interaction.user.id) or (perms and perms.manage_roles):
            return True
        await interaction.response.send_message("Run the command yourself to browse these pages.", ephemeral=True)
        return False

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def first(self, interaction: discord.Interaction, _):
        self.index = 0
        await self.show(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary, row=0)
    async def prev(self, interaction: discord.Interaction, _):
        self.index = max(0, self.index - 1)
        await self.show(interaction)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def counter(self, interaction: discord.Interaction, _):
        pass

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary, row=0)
    async def next(self, interaction: discord.Interaction, _):
        self.index = min(len(self.pages) - 1, self.index + 1)
        await self.show(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def last(self, interaction: discord.Interaction, _):
        self.index = len(self.pages) - 1
        await self.show(interaction)


def csv_file(text: str, name: str) -> discord.File:
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=name)


async def send_pages(interaction: discord.Interaction, pages: list[Page], file: discord.File | None = None,
                     ephemeral: bool = False):
    """Reply to a deferred interaction with paged embeds (one message)."""
    kwargs = {"ephemeral": ephemeral, "wait": True}
    if file:
        kwargs["file"] = file
    if len(pages) == 1:
        await interaction.followup.send(embed=page_embed(pages[0]), **kwargs)
        return
    view = Paginator(pages, owner_id=interaction.user.id)
    view.message = await interaction.followup.send(embed=view.embed(), view=view, **kwargs)


async def post_pages_to_staff(pages: list[Page], file_text: str | None = None, file_name: str = "results.csv",
                              skip_channel_id: int | None = None):
    if not STAFF_CHANNEL_ID or int(STAFF_CHANNEL_ID) == skip_channel_id:
        return
    channel = bot.get_channel(int(STAFF_CHANNEL_ID))
    if channel is None:
        log.warning("STAFF_CHANNEL_ID %s not found", STAFF_CHANNEL_ID)
        return
    view = Paginator(pages, owner_id=None, timeout=86400)  # staff can browse for a day
    kwargs = {"embed": view.embed()}
    if len(pages) > 1:
        kwargs["view"] = view
    if file_text:
        kwargs["file"] = csv_file(file_text, file_name)
    msg = await channel.send(**kwargs)
    view.message = msg


async def roster_autocomplete(interaction: discord.Interaction, current: str):
    cur = current.lower()
    names = [m.roblox_username for m in store.members() if cur in m.roblox_username.lower()]
    return [app_commands.Choice(name=x, value=x) for x in names[:25]]


RANK_CHOICES = [app_commands.Choice(name=r, value=r) for r in RANKS]


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


@roster_group.command(name="add", description="Add a new clan member")
@app_commands.describe(roblox="Their Roblox username (the @ name)", discord_user="Their Discord account",
                       rank="Clan rank (default Member)", exempt="Skip them in coin checks?", notes="Optional note")
@app_commands.choices(rank=RANK_CHOICES)
async def roster_add(interaction: discord.Interaction, roblox: str, discord_user: Optional[discord.User] = None,
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
    if not store.add_member(name, rid, discord_user.id if discord_user else None, rank_name, exempt, notes):
        await interaction.followup.send(embed=simple(f"**{name}** is already on the roster.", AMBER))
        return
    e = simple("Their first coin check will be their starting point (Baseline)." + warn, GREEN, f"✅ Added {name}")
    e.add_field(name="Discord", value=discord_user.mention if discord_user else "*not linked yet*", inline=True)
    e.add_field(name="Rank", value=rank_name + (" · 🛡️ exempt" if exempt else ""), inline=True)
    e.add_field(name="Roster", value=f"{len(store.members())}/100", inline=True)
    await interaction.followup.send(embed=e)


@roster_group.command(name="remove", description="Remove someone from the roster (their coin history is kept)")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_remove(interaction: discord.Interaction, roblox: str):
    ok = store.remove_member(roblox)
    await interaction.response.send_message(embed=simple(
        f"🗑️ Removed **{roblox}**. Roster: {len(store.members())}/100." if ok else f"**{roblox}** isn't on the roster.",
        GREEN if ok else AMBER))


@roster_group.command(name="link", description="Link a member's Discord account")
@app_commands.autocomplete(roblox=roster_autocomplete)
async def roster_link(interaction: discord.Interaction, roblox: str, discord_user: discord.User):
    if not store.get_member(roblox):
        await interaction.response.send_message(embed=simple(
            f"**{roblox}** isn't on the roster. Add them with `/roster add`.", AMBER))
        return
    others = [o for o in store.discord_id_owner(discord_user.id) if o.lower() != roblox.lower()]
    store.update_member(roblox, discord_id=discord_user.id)
    text = f"🔗 **{roblox}** is now linked to {discord_user.mention}."
    if others:
        text += f"\n⚠️ That Discord account is also linked to {', '.join(others)}."
    await interaction.response.send_message(embed=simple(text))


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
    ok = store.update_member(roblox, rank=rank.value)
    await interaction.response.send_message(embed=simple(
        f"**{roblox}** is now {rank.value}." if ok else f"**{roblox}** isn't on the roster.", GREEN if ok else AMBER))


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
    await send_pages(interaction, reports.roster_pages(store.members(), latest),
                     csv_file(store.export_csv(), "gg_roster.csv"))


# ================================================================= /coins ===

coins_group = app_commands.Group(name="coins", description="Monthly coin checks",
                                 default_permissions=STAFF_ONLY, guild_only=True)


def check_pages(cid: int, unknown: list[str] | None = None) -> list[Page]:
    prev = store.previous_check_id(cid)
    return reports.coin_check_pages(store.results(cid), store.check_label(cid),
                                    store.check_label(prev) if prev else None, store.get_minimum(), unknown)


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
    pages = check_pages(cid, unknown)
    pages[0].note = (f"Imported {len(totals)} totals. Wrong number? /coins set · Wrong file? /coins undo")
    fname = f"coin_check_{label.replace(' ', '_')}.csv"
    export = store.export_csv()
    await send_pages(interaction, pages, csv_file(export, fname))
    await post_pages_to_staff(pages, export, fname, skip_channel_id=interaction.channel_id)


@coins_group.command(name="results", description="Show the latest coin check results")
async def coins_results(interaction: discord.Interaction):
    cid = store.latest_check_id()
    if not cid:
        await interaction.response.send_message(embed=simple("No coin checks yet. Use `/coins import`.", AMBER))
        return
    await interaction.response.defer()
    await send_pages(interaction, check_pages(cid), csv_file(store.export_csv(), "coin_check_latest.csv"))


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
    page = reports.member_status_page(m, store.history(m.roblox_username), store.get_minimum())
    await interaction.response.send_message(embed=page_embed(page))


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
    page = reports.member_status_page(m, store.history(m.roblox_username), store.get_minimum(), current)
    await interaction.response.send_message(embed=page_embed(page), ephemeral=True)


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

async def build_check(guild: discord.Guild, which: str) -> list[Page]:
    roster = store.members()
    pages: list[Page] = []
    if which in ("all", "discord"):
        role = (guild.get_role(int(MEMBER_ROLE)) if MEMBER_ROLE.isdigit()
                else discord.utils.get(guild.roles, name=MEMBER_ROLE))
        if role is None:
            pages.append(Page("💬 Discord check", "Discord summary",
                              [f"⚠️ Couldn't find a Discord role called **{MEMBER_ROLE}**."], RED))
        else:
            server_ids, role_ids, names = set(), set(), {}
            async for mem in guild.fetch_members(limit=None):
                if mem.bot:
                    continue
                server_ids.add(mem.id)
                names[mem.id] = mem.name
                if any(r.id == role.id for r in mem.roles):
                    role_ids.add(mem.id)
            pages += reports.discord_check_pages(roster, role_ids, server_ids, names, role.name)
    if which in ("all", "roblox"):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                need = [m.roblox_username for m in roster if not m.roblox_id]
                found = await rbx.lookup_usernames(s, need) if need else {}
                for m in roster:  # remember IDs so renamed accounts still match next time
                    if not m.roblox_id and m.roblox_username.lower() in found:
                        store.update_member(m.roblox_username, roblox_id=found[m.roblox_username.lower()][0])
                holders = await rbx.clan_role_holders(s, ROBLOX_GROUP_ID, ROBLOX_MIN_RANK, ROBLOX_IGNORE_ROLES)
            pages += reports.roblox_check_pages(store.members(), {k: v[0] for k, v in found.items()}, holders)
        except Exception as e:
            log.exception("Roblox check failed")
            pages.append(Page("🎮 Roblox group check", "Roblox summary", [f"⚠️ Roblox check failed: {e}"], RED))
    return pages


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
    await send_pages(interaction, await build_check(interaction.guild, what.value if what else "all"))


@tasks.loop(time=dt.time(hour=REPORT_HOUR_UTC, tzinfo=dt.timezone.utc))
async def weekly_report():
    if WEEKDAYS[dt.datetime.now(dt.timezone.utc).weekday()] != REPORT_WEEKDAY:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    pages = await build_check(guild, "all")
    for p in pages:
        p.title = "📋 Weekly — " + p.title
    await post_pages_to_staff(pages)


@weekly_report.before_loop
async def _wait_ready():
    await bot.wait_until_ready()


def run():
    log.info("Starting bot, code version %s", updater.current_version()[:7])
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    run()
