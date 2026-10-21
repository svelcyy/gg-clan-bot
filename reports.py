"""Turns data into leaderboard-style lists for the bot's embeds.

No Discord code in here, so it can be tested on its own.

A Board is one embed with several lists the viewer can switch between (a menu),
each list split into pages of 12 people:

    Page 1/7 • Showing 12 of 70 members
    -# Compared with 18 Oct 2026 · minimum 10,000

    🥇 **pramishp4** · +12,000 ✅
    -# 863,128 → 875,128 · Member
"""
from __future__ import annotations

from dataclasses import dataclass

from storage import Member, Result

PER_PAGE = 10
MEDALS = ["🥇", "🥈", "🥉"]

# embed colours
BLURPLE, GREEN, RED, AMBER, PURPLE, GREY = 0x5865F2, 0x2ECC71, 0xE74C3C, 0xF1C40F, 0x9B59B6, 0x95A5A6


def n(x: int | None) -> str:
    return "—" if x is None else f"{x:,}"


def esc(text: str) -> str:
    """Stop names like Roblox_King_4510 from turning into italics or other formatting."""
    for ch in "\\*_~`|>":
        text = text.replace(ch, "\\" + ch)
    return text


# Discord shows <@id> mentions as raw numbers for people the viewer's app hasn't loaded, so boards use
# plain @handles instead. The bot sets this to look handles up in the server (already escaped).
name_lookup = lambda discord_id: None   # noqa: E731


def dname(discord_id: int | None) -> str | None:
    """'@handle' for a linked Discord account, 'Not in the server' if they left, or None if not linked."""
    if not discord_id:
        return None
    try:
        name = name_lookup(int(discord_id))
    except Exception:
        name = None
    return f"@{name}" if name else "Not in the server"


def who(m: Member) -> str:
    """Bold display name for public boards: their Discord @handle, or their Roblox name if not linked."""
    d = dname(m.discord_id)
    return f"**{d}**" if d and d.startswith("@") else f"**{esc(m.roblox_username)}**"


def rank_tag(m: Member) -> str:
    """Only staff ranks are worth showing; everyone else is a Member."""
    return "" if m.rank == "Member" else m.rank


def joined(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


@dataclass
class Entry:
    main: str        # bold line, e.g. "**pramishp4** · +12,000 ✅"
    sub: str = ""    # small grey line underneath


@dataclass
class ListView:
    label: str                 # name in the menu, e.g. "Failed (3)"
    entries: list[Entry]
    ranked: bool = False       # medals for the top 3 instead of 1. 2. 3.
    medal_limit: int = 3       # only the first N entries can get a medal
    empty: str = "Nobody here."


@dataclass
class Board:
    title: str
    header: str                      # one small line under the list name
    lists: list[ListView]
    color: int = BLURPLE
    noun: str = "members"
    csv_text: str | None = None      # offered behind a "Spreadsheet" button

    def page_count(self, list_index: int) -> int:
        return max(1, -(-len(self.lists[list_index].entries) // PER_PAGE))

    def footer(self, list_index: int, page: int) -> str:
        total = len(self.lists[list_index].entries)
        pages = self.page_count(list_index)
        count = f"{total} {self.noun if total != 1 else self.noun.rstrip('s')}"
        return f"Page {min(page, pages - 1) + 1} of {pages} · {count}" if pages > 1 else count

    def render(self, list_index: int, page: int) -> str:
        lv = self.lists[list_index]
        pages = self.page_count(list_index)
        page = max(0, min(page, pages - 1))
        chunk = lv.entries[page * PER_PAGE:(page + 1) * PER_PAGE]
        lines = []
        if len(self.lists) > 1:
            lines.append(f"### {lv.label}")
        if self.header:
            lines.append(f"-# {self.header}")
        if lines:
            lines.append("")
        if not chunk:
            lines.append(lv.empty)
        for i, e in enumerate(chunk, start=page * PER_PAGE):
            prefix = MEDALS[i] if lv.ranked and i < min(3, lv.medal_limit) else f"{i + 1}."
            lines.append(f"{prefix} {e.main}")
            if e.sub:
                lines.append(f"-# {e.sub}")
            lines.append("")
        return "\n".join(lines).rstrip()


# ------------------------------------------------------------ coin checks ---

def coin_board(results: list[Result], label: str, prev_label: str | None, minimum: int,
               unknown_names: list[str] | None = None, csv_text: str | None = None) -> Board:
    """Staff view of a coin check."""
    by = {s: [r for r in results if r.status == s] for s in ("Pass", "Fail", "Baseline", "Missing", "Exempt", "New")}

    def entry(r: Result) -> Entry:
        m = r.member
        name = f"**{esc(m.roblox_username)}**"
        if r.status == "Pass":
            return Entry(f"{name} · +{r.gained:,} ✅", joined(f"{n(r.previous)} → {n(r.total)}", rank_tag(m)))
        if r.status == "Fail":
            return Entry(f"{name} · +{r.gained:,} ❌", joined(f"Short {r.short_by:,}", f"{n(r.previous)} → {n(r.total)}"))
        if r.status == "Baseline":
            return Entry(f"{name} · New", f"Total {n(r.total)} · Counts from the next check")
        if r.status == "New":
            return Entry(f"{name} · New", "Joined after this check")
        if r.status == "Missing":
            return Entry(f"{name} · Missing", f"Not in this import · Last total {n(r.previous)}")
        return Entry(f"{name} · Exempt", joined(rank_tag(m), f"+{r.gained:,}" if r.gained is not None else ""))

    checked = sorted(by["Pass"] + by["Fail"], key=lambda r: -(r.gained or 0))
    new = sorted(by["Baseline"], key=lambda r: -(r.total or 0)) + by["New"]
    everyone = checked + new + by["Missing"]
    lists = [ListView(f"Everyone ({len(everyone)})", [entry(r) for r in everyone],
                      ranked=bool(checked), medal_limit=len(checked))]
    lists.append(ListView(f"Failed ({len(by['Fail'])})",
                          [entry(r) for r in sorted(by["Fail"], key=lambda r: r.gained or 0)], empty="Nobody failed"))
    lists.append(ListView(f"Passed ({len(by['Pass'])})",
                          [entry(r) for r in sorted(by["Pass"], key=lambda r: -(r.gained or 0))], ranked=True,
                          empty="Nobody passed yet."))
    if by["Missing"]:
        lists.append(ListView(f"Missing ({len(by['Missing'])})", [entry(r) for r in by["Missing"]]))
    if new:
        lists.append(ListView(f"New ({len(new)})", [entry(r) for r in new]))
    if unknown_names:
        lists.append(ListView(f"Not on the Roster ({len(unknown_names)})",
                              [Entry(f"**{esc(u)}**", "In the import but not on the roster") for u in unknown_names]))
    if by["Exempt"]:
        lists.append(ListView(f"Exempt ({len(by['Exempt'])})", [entry(r) for r in by["Exempt"]]))

    header = joined(f"Since {prev_label}" if prev_label else "Since starting coins", f"Minimum {minimum:,}",
                    f"{len(by['Pass'])} passed · {len(by['Fail'])} failed" if checked else "")
    color = RED if by["Fail"] else (GREEN if by["Pass"] else BLURPLE)
    return Board(f"🪙 Coin Check · {label}", header, lists, color, csv_text=csv_text)


# ------------------------------------------------------ public leaderboard ---

def leaderboard_board(results: list[Result], label: str, prev_label: str | None, minimum: int) -> Board:
    """The member-facing view of the latest coin check. No staff details."""
    def entry(r: Result) -> Entry:
        m = r.member
        sub = joined(esc(m.roblox_username) if m.discord_id else "", f"Total {n(r.total)}" if r.total is not None else "")
        if r.status == "Pass":
            return Entry(f"{who(m)} · **+{r.gained:,}** ✅", sub)
        if r.status == "Fail":
            return Entry(f"{who(m)} · **+{r.gained:,}** ❌", joined(sub, f"Needs {r.short_by:,} more"))
        if r.status in ("Baseline", "New"):
            return Entry(f"{who(m)} · New", sub or "Joined recently")
        return Entry(f"{who(m)} · Missing", joined(esc(m.roblox_username) if m.discord_id else "", "Not in this check"))

    shown = [r for r in results if r.status != "Exempt"]
    checked = sorted([r for r in shown if r.status in ("Pass", "Fail")], key=lambda r: -(r.gained or 0))
    rest = sorted([r for r in shown if r.status in ("Baseline", "New")], key=lambda r: -(r.total or 0))
    missing = [r for r in shown if r.status == "Missing"]
    ranked = checked + rest + missing
    lists = [ListView("Top Gains", [entry(r) for r in ranked], ranked=bool(checked), medal_limit=len(checked)),
             ListView("A–Z", [entry(r) for r in sorted(shown, key=lambda r: r.member.roblox_username.lower())])]
    passed = sum(r.status == "Pass" for r in shown)
    header = joined(f"Since {prev_label}" if prev_label else "Since starting coins", f"Minimum {minimum:,}",
                    f"{passed} of {len(checked)} passed" if checked else "")
    return Board(f"🏆 Leaderboard · {label}", header, lists, GREEN if checked else BLURPLE)


def current_coins_board(members: list[Member]) -> Board:
    """Everyone's current Contribution, before the first graded coin check."""
    shown = [m for m in members if not m.exempt]

    def entry(m: Member) -> Entry:
        return Entry(f"{who(m)} · **{n(m.start_total or 0)}**",
                     joined(esc(m.roblox_username) if m.discord_id else "", rank_tag(m)))

    by_coins = sorted(shown, key=lambda m: -(m.start_total or 0))
    lists = [ListView("Most Coins", [entry(m) for m in by_coins], ranked=True),
             ListView("A–Z", [entry(m) for m in sorted(shown, key=lambda m: m.roblox_username.lower())])]
    total = sum(m.start_total or 0 for m in shown)
    return Board("🏆 Leaderboard", f"Clan total {n(total)}", lists, BLURPLE)


# ----------------------------------------------------------------- roster ---

def roster_board(members: list[Member], latest: dict[str, Result] | None = None,
                 csv_text: str | None = None) -> Board:
    latest = latest or {}

    def total(m: Member) -> int:
        r = latest.get(m.roblox_username)
        if r and r.total is not None:
            return r.total
        return m.start_total if m.start_total is not None else -1

    def entry(m: Member, show_total: bool = True) -> Entry:
        t = total(m)
        main = f"**{esc(m.roblox_username)}**" + (f" · {t:,}" if show_total and t >= 0 else "")
        return Entry(main, joined(rank_tag(m), "Exempt" if m.exempt else "", dname(m.discord_id) or "Not linked"))

    staff = [m for m in members if m.rank != "Member" or m.exempt]
    unlinked = [m for m in members if not m.discord_id]
    lists = [
        ListView(f"By Contribution ({len(members)})", [entry(m) for m in sorted(members, key=lambda m: -total(m))],
                 ranked=True),
        ListView("A–Z", [entry(m) for m in sorted(members, key=lambda m: m.roblox_username.lower())]),
    ]
    if staff:
        order = {"Leader": 0, "Admin": 1, "Officer": 2, "Member": 3}
        lists.append(ListView(f"Staff & Exempt ({len(staff)})",
                              [entry(m) for m in sorted(staff, key=lambda m: (order.get(m.rank, 9),
                                                                               m.roblox_username.lower()))]))
    if unlinked:
        lists.append(ListView(f"Not Linked ({len(unlinked)})", [entry(m, False) for m in unlinked]))
    header = joined(f"{len(members)} members", f"{len(staff)} staff & exempt",
                    f"{len(unlinked)} not linked" if unlinked else "")
    return Board("📋 [gg] Roster", header, lists, BLURPLE, csv_text=csv_text)


# ------------------------------------------------------------ role checks ---

def check_board(roster: list[Member],
                discord: tuple[set[int], set[int], dict[int, str], str] | None,
                roblox: tuple[dict[str, int], dict[int, tuple[str, str]]] | None,
                errors: list[str] | None = None) -> Board:
    """discord = (role holder ids, server member ids, id->name, role name)
    roblox  = (username->userId, userId->(username, role))"""
    lists: list[ListView] = []
    summary: list[str] = []
    problems = 0

    if discord:
        role_ids, server_ids, names, role_name = discord
        missing, gone, no_id, roster_ids = [], [], [], set()
        for m in roster:
            if m.discord_id is None:
                no_id.append(Entry(f"**{esc(m.roblox_username)}**", "Link them with /roster link"))
                continue
            roster_ids.add(m.discord_id)
            if m.discord_id not in server_ids:
                gone.append(Entry(f"**{esc(m.roblox_username)}**", "Their linked Discord account left the server"))
            elif m.discord_id not in role_ids:
                missing.append(Entry(f"**{esc(m.roblox_username)}**", joined(dname(m.discord_id), f"Needs {role_name}")))
        extra = [Entry(f"**@{esc(names.get(i, str(i)))}**", f"Has {role_name} but isn't on the roster")
                 for i in sorted(role_ids - roster_ids, key=lambda i: names.get(i, "").lower())]
        lists += [ListView(f"Needs {role_name} ({len(missing)})", missing, empty="Everyone has it"),
                  ListView(f"Remove {role_name} ({len(extra)})", extra, empty="Nobody extra")]
        if gone:
            lists.append(ListView(f"Left the Server ({len(gone)})", gone))
        if no_id:
            lists.append(ListView(f"Not Linked ({len(no_id)})", no_id))
        problems += len(missing) + len(extra) + len(gone)
        summary.append(f"Discord: {len(missing)} missing, {len(extra)} extra")

    if roblox:
        ids, holders = roblox
        missing, unknown, roster_uids = [], [], set()
        for m in roster:
            uid = m.roblox_id or ids.get(m.roblox_username.lower())
            if uid is None:
                unknown.append(Entry(f"**{esc(m.roblox_username)}**", "Roblox account not found · Check the spelling"))
                continue
            roster_uids.add(uid)
            if uid not in holders:
                missing.append(Entry(f"**{esc(m.roblox_username)}**", "Needs a clan role in the Roblox group"))
        extra = [Entry(f"**{esc(name)}**", f"{role} in the group but not on the roster")
                 for uid, (name, role) in sorted(holders.items(), key=lambda kv: kv[1][0].lower())
                 if uid not in roster_uids]
        lists += [ListView(f"Needs Group Role ({len(missing)})", missing, empty="Everyone has one"),
                  ListView(f"Remove Group Role ({len(extra)})", extra, empty="Nobody extra")]
        if unknown:
            lists.append(ListView(f"Roblox Account Not Found ({len(unknown)})", unknown))
        problems += len(missing) + len(extra) + len(unknown)
        summary.append(f"Roblox: {len(missing)} missing, {len(extra)} extra")

    for err in errors or []:
        summary.append(err)
    if not lists:
        lists = [ListView("Nothing checked", [])]
    return Board("🔎 Roster Check", joined(*summary), lists, AMBER if problems else GREEN, noun="people")


# ---------------------------------------------------------- member status ---

def member_status(m: Member, history: list[tuple[str, int, int | None]], minimum: int) -> tuple[str, str, int]:
    """(title, description, colour) for /coins status."""
    lines = [f"-# {joined(m.rank, 'Exempt' if m.exempt else '', f'Minimum {minimum:,}')}", ""]
    color = PURPLE if m.exempt else BLURPLE
    if not history:
        lines.append("No coins recorded yet.")
    for label, total, gained in history:
        if gained is None:
            lines += ["**Starting coins**" if label == "Joined" else f"**{esc(label)}** · New", f"-# Total {total:,}", ""]
        elif m.exempt:
            lines += [f"**{esc(label)}** · +{gained:,}", f"-# Total {total:,}", ""]
        else:
            ok = gained >= minimum
            lines += [f"**{esc(label)}** · +{gained:,} {'✅' if ok else '❌'}",
                      f"-# {joined(f'Total {total:,}', '' if ok else f'Short {minimum - gained:,}')}", ""]
    if history and history[0][2] is not None and not m.exempt:
        color = GREEN if history[0][2] >= minimum else RED
    return f"🪙 {m.roblox_username}", "\n".join(lines).rstrip(), color
