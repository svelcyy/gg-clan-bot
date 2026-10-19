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

from dataclasses import dataclass, field

from storage import Member, Result

PER_PAGE = 12
MEDALS = ["🥇", "🥈", "🥉"]

# embed colours
BLURPLE, GREEN, RED, AMBER, PURPLE, GREY = 0x5865F2, 0x2ECC71, 0xE74C3C, 0xF1C40F, 0x9B59B6, 0x95A5A6


def n(x: int | None) -> str:
    return "—" if x is None else f"{x:,}"


@dataclass
class Entry:
    main: str        # bold line, e.g. "**pramishp4** · +12,000 ✅"
    sub: str = ""    # small grey line underneath


@dataclass
class ListView:
    label: str                 # name in the menu, e.g. "❌ Failed"
    entries: list[Entry]
    ranked: bool = False       # medals for the top 3 instead of 1. 2. 3.
    medal_limit: int = 3       # only the first N entries can get a medal
    empty: str = "Nobody here 🎉"


@dataclass
class Board:
    title: str
    header: str                      # one small line under the page counter
    lists: list[ListView]
    color: int = BLURPLE
    noun: str = "members"
    csv_text: str | None = None      # offered behind a "Spreadsheet" button

    def page_count(self, list_index: int) -> int:
        return max(1, -(-len(self.lists[list_index].entries) // PER_PAGE))

    def render(self, list_index: int, page: int) -> str:
        lv = self.lists[list_index]
        total = len(lv.entries)
        pages = self.page_count(list_index)
        page = max(0, min(page, pages - 1))
        chunk = lv.entries[page * PER_PAGE:(page + 1) * PER_PAGE]
        top = f"Page {page + 1}/{pages} • Showing {len(chunk)} of {total} {self.noun}"
        if len(self.lists) > 1:
            top = f"**{lv.label}**\n" + top
        lines = [top]
        if self.header:
            lines.append(f"-# {self.header}")
        lines.append("")
        if not chunk:
            lines.append(lv.empty)
        for i, e in enumerate(chunk, start=page * PER_PAGE):
            prefix = MEDALS[i] if lv.ranked and i < min(3, lv.medal_limit) else f"{i + 1}."
            lines.append(f"{prefix} {e.main}")
            if e.sub:
                lines.append(f"-# {e.sub}")
        return "\n".join(lines)


# ------------------------------------------------------------ coin checks ---

def coin_board(results: list[Result], label: str, prev_label: str | None, minimum: int,
               unknown_names: list[str] | None = None, csv_text: str | None = None) -> Board:
    by = {s: [r for r in results if r.status == s] for s in ("Pass", "Fail", "Baseline", "Missing", "Exempt", "New")}

    def entry(r: Result) -> Entry:
        name = f"**{r.member.roblox_username}**"
        if r.status == "Pass":
            return Entry(f"{name} · +{r.gained:,} ✅", f"{n(r.previous)} → {n(r.total)} · {r.member.rank}")
        if r.status == "Fail":
            return Entry(f"{name} · +{r.gained:,} ❌", f"Short {r.short_by:,} · {n(r.previous)} → {n(r.total)}")
        if r.status == "Baseline":
            return Entry(f"{name} · 🆕", f"Total {n(r.total)} · Counts from the next check")
        if r.status == "New":
            start = f" · Started at {r.member.start_total:,}" if r.member.start_total is not None else ""
            return Entry(f"{name} · 🆕", f"Joined after this check{start}")
        if r.status == "Missing":
            return Entry(f"{name} · ❓ Not in this import", f"Last total {n(r.previous)}")
        gained = f" · +{r.gained:,}" if r.gained is not None else ""
        return Entry(f"{name} · 🛡️ Exempt", f"{r.member.rank}{gained}")

    checked = sorted(by["Pass"] + by["Fail"], key=lambda r: -(r.gained or 0))
    baseline = sorted(by["Baseline"], key=lambda r: -(r.total or 0)) + by["New"]
    everyone = checked + baseline + by["Missing"]
    lists = [ListView("📊 Everyone", [entry(r) for r in everyone], ranked=bool(checked), medal_limit=len(checked))]
    lists.append(ListView(f"❌ Failed ({len(by['Fail'])})",
                          [entry(r) for r in sorted(by["Fail"], key=lambda r: r.gained or 0)],
                          empty="Nobody failed 🎉"))
    lists.append(ListView(f"✅ Passed ({len(by['Pass'])})",
                          [entry(r) for r in sorted(by["Pass"], key=lambda r: -(r.gained or 0))], ranked=True,
                          empty="Nobody passed yet."))
    if by["Missing"]:
        lists.append(ListView(f"❓ Missing ({len(by['Missing'])})", [entry(r) for r in by["Missing"]]))
    if by["Baseline"]:
        lists.append(ListView(f"🆕 New ({len(baseline)})", [entry(r) for r in baseline]))
    if unknown_names:
        lists.append(ListView(f"⚠️ Not on roster ({len(unknown_names)})",
                              [Entry(f"**{u}**", "In the import but not on the roster · Use /roster add or /coins set")
                               for u in unknown_names]))
    lists.append(ListView(f"🛡️ Exempt ({len(by['Exempt'])})", [entry(r) for r in by["Exempt"]]))

    parts = [f"Compared with {prev_label}" if prev_label else "Compared with starting coins",
             f"Minimum {minimum:,}"]
    if by["Pass"] or by["Fail"]:
        parts.append(f"✅ {len(by['Pass'])} · ❌ {len(by['Fail'])}")
    if by["Missing"]:
        parts.append(f"❓ {len(by['Missing'])}")
    color = RED if by["Fail"] else (GREEN if by["Pass"] else BLURPLE)
    return Board(f"🪙 Coin Check — {label}", " · ".join(parts), lists, color, csv_text=csv_text)


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
        main = f"**{m.roblox_username}**" + (f" · {t:,}" if show_total and t >= 0 else "")
        bits = [m.rank]
        if m.exempt:
            bits.append("🛡️ Exempt")
        bits.append(f"<@{m.discord_id}>" if m.discord_id else "Not linked")
        return Entry(main, " · ".join(bits))

    lists = [
        ListView("🏆 By contribution", [entry(m) for m in sorted(members, key=lambda m: -total(m))], ranked=True),
        ListView("🔤 A–Z", [entry(m) for m in sorted(members, key=lambda m: m.roblox_username.lower())]),
        ListView(f"🛡️ Staff & exempt ({sum(m.exempt for m in members)})",
                 [entry(m) for m in members if m.exempt]),
    ]
    unlinked = [m for m in members if not m.discord_id]
    if unlinked:
        lists.append(ListView(f"🔗 Not linked ({len(unlinked)})", [entry(m, False) for m in unlinked]))
    header = f"{len(members)}/100 members · {sum(m.exempt for m in members)} exempt · {len(unlinked)} not linked"
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
                no_id.append(Entry(f"**{m.roblox_username}**", "No Discord linked · Use /roster link"))
                continue
            roster_ids.add(m.discord_id)
            who = names.get(m.discord_id, str(m.discord_id))
            if m.discord_id not in server_ids:
                gone.append(Entry(f"**{m.roblox_username}**", f"{who} · Not in the server"))
            elif m.discord_id not in role_ids:
                missing.append(Entry(f"**{m.roblox_username}**", f"<@{m.discord_id}> · Needs {role_name}"))
        extra = [Entry(f"<@{i}>", f"{names.get(i, '?')} · Has {role_name} but isn't on the roster")
                 for i in sorted(role_ids - roster_ids, key=lambda i: names.get(i, "").lower())]
        lists += [ListView(f"➕ Needs {role_name} ({len(missing)})", missing),
                  ListView(f"➖ Remove {role_name} ({len(extra)})", extra)]
        if gone:
            lists.append(ListView(f"🚪 Not in server ({len(gone)})", gone))
        if no_id:
            lists.append(ListView(f"🔗 No Discord linked ({len(no_id)})", no_id))
        problems += len(missing) + len(extra) + len(gone)
        summary.append(f"Discord: {len(missing)} need the role, {len(extra)} extra")

    if roblox:
        ids, holders = roblox
        missing, unknown, roster_uids = [], [], set()
        for m in roster:
            uid = m.roblox_id or ids.get(m.roblox_username.lower())
            if uid is None:
                unknown.append(Entry(f"**{m.roblox_username}**", "Roblox name not found · Check the spelling"))
                continue
            roster_uids.add(uid)
            if uid not in holders:
                missing.append(Entry(f"**{m.roblox_username}**", "Needs Clan Member in the Roblox group"))
        extra = [Entry(f"**{name}**", f"{role} in the group but not on the roster")
                 for uid, (name, role) in sorted(holders.items(), key=lambda kv: kv[1][0].lower())
                 if uid not in roster_uids]
        lists += [ListView(f"🎮 Needs clan role ({len(missing)})", missing),
                  ListView(f"🎮 Remove clan role ({len(extra)})", extra)]
        if unknown:
            lists.append(ListView(f"❓ Roblox name not found ({len(unknown)})", unknown))
        problems += len(missing) + len(extra) + len(unknown)
        summary.append(f"Roblox: {len(missing)} need a role, {len(extra)} extra")

    for err in errors or []:
        summary.append(f"⚠️ {err}")
    if not lists:
        lists = [ListView("Nothing checked", [])]
    return Board("🔎 Roster Check", " · ".join(summary), lists, AMBER if problems else GREEN, noun="people")


# ---------------------------------------------------------- member status ---

def member_status(m: Member, history: list[tuple[str, int, int | None]], minimum: int,
                  current: int | None = None) -> tuple[str, str, int]:
    """(title, description, colour) for /mystatus and /coins status."""
    lines = [f"-# {m.rank}" + (" · 🛡️ Exempt from coin checks" if m.exempt else "") + f" · Minimum {minimum:,}", ""]
    color = PURPLE if m.exempt else BLURPLE
    if not history:
        lines.append("No coin checks recorded yet.")
    for label, total, gained in history:
        if gained is None:
            lines += [f"**{label}** · 🆕", f"-# Total {total:,}"]
        elif m.exempt:
            lines += [f"**{label}** · +{gained:,}", f"-# Total {total:,}"]
        else:
            ok = gained >= minimum
            lines += [f"**{label}** · +{gained:,} {'✅' if ok else '❌'}",
                      f"-# Total {total:,}" + ("" if ok else f" · Short {minimum - gained:,}")]
    if history and history[0][2] is not None and not m.exempt:
        color = GREEN if history[0][2] >= minimum else RED
    if current is not None and not m.exempt:
        lines.append("")
        if history:
            so_far = current - history[0][1]
            need = max(0, minimum - so_far)
            lines.append(f"**This month so far:** +{so_far:,}")
            lines.append("-# ✅ Minimum reached!" if need == 0 else f"-# Need {need:,} more to reach {minimum:,}")
            color = GREEN if need == 0 else AMBER
        else:
            lines.append("-# No previous check to compare with yet.")
    return f"🪙 {m.roblox_username}", "\n".join(lines), color
