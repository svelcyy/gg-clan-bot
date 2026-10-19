"""Turns data into pages for the bot's embeds. No Discord code, so it can be tested on its own.

Every report is a list of Page objects. The bot shows one page at a time with
◀ ▶ buttons and a menu to jump between sections.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from storage import Member, Result

PER_PAGE = 15

# embed colours
BLURPLE, GREEN, RED, AMBER, PURPLE, GREY = 0x5865F2, 0x2ECC71, 0xE74C3C, 0xF1C40F, 0x9B59B6, 0x95A5A6


@dataclass
class Page:
    title: str
    section: str
    lines: list[str] = field(default_factory=list)
    color: int = BLURPLE
    fields: list[tuple[str, str, bool]] = field(default_factory=list)  # (name, value, inline)
    note: str = ""  # small text shown under the list


def n(x: int | None) -> str:
    return "—" if x is None else f"{x:,}"


def section_pages(title: str, section: str, items: list[str], color: int, empty: str = "Nobody here.",
                  note: str = "") -> list[Page]:
    """Split a long list into pages of PER_PAGE lines."""
    head = f"{section} ({len(items)})"
    if not items:
        return [Page(title, head, [empty], color, note=note)]
    return [Page(title, head, items[i:i + PER_PAGE], color, note=note) for i in range(0, len(items), PER_PAGE)]


def total_chars(pages: list[Page]) -> int:
    return max(sum(len(l) + 1 for l in p.lines) + sum(len(a) + len(b) for a, b, _ in p.fields) for p in pages)


# ------------------------------------------------------------ coin checks ---

def coin_check_pages(results: list[Result], label: str, prev_label: str | None, minimum: int,
                     unknown_names: list[str] | None = None) -> list[Page]:
    by = {s: [r for r in results if r.status == s] for s in ("Pass", "Fail", "Baseline", "Missing", "Exempt")}
    title = f"🪙 Coin check — {label}"
    fails = sorted(by["Fail"], key=lambda r: r.gained or 0)
    passes = sorted(by["Pass"], key=lambda r: -(r.gained or 0))
    top = ", ".join(f"{r.member.roblox_username} (+{r.gained:,})" for r in passes[:3]) or "—"

    summary = Page(title, "Summary", [
        f"Compared with **{prev_label or 'nothing yet (first check)'}**",
        f"Monthly minimum: **{minimum:,}**",
    ], RED if fails else GREEN, fields=[
        ("✅ Passed", str(len(by["Pass"])), True),
        ("❌ Failed", str(len(fails)), True),
        ("❓ Missing", str(len(by["Missing"])), True),
        ("🆕 Baseline", str(len(by["Baseline"])), True),
        ("🛡️ Exempt", str(len(by["Exempt"])), True),
        ("⚠️ Not on roster", str(len(unknown_names or [])), True),
        ("🏆 Top gains", top, False),
    ], note="Use the buttons or the menu below to see each list.")

    pages = [summary]
    pages += section_pages(title, "❌ Failed", [
        f"**{r.member.roblox_username}** — gained {n(r.gained)} · short **{n(r.short_by)}**" for r in fails],
        RED, "Nobody failed this month 🎉")
    if by["Missing"]:
        pages += section_pages(title, "❓ Missing from this import", [r.member.roblox_username for r in by["Missing"]],
                               AMBER, note="On the roster but not in the file. Left the clan, or the name was misread?")
    if unknown_names:
        pages += section_pages(title, "⚠️ Not on the roster", unknown_names, AMBER,
                               note="Add them with /roster add, or fix a misspelling with /coins set.")
    if by["Baseline"]:
        pages += section_pages(title, "🆕 Baseline (first check)", [r.member.roblox_username for r in by["Baseline"]],
                               BLURPLE, note="No previous total yet. Their next check will count.")
    pages += section_pages(title, "✅ Passed", [
        f"{r.member.roblox_username} — +{r.gained:,}" for r in passes], GREEN, "Nobody passed yet.")
    pages += section_pages(title, "🛡️ Exempt", [
        f"{r.member.roblox_username} ({r.member.rank})" for r in by["Exempt"]], PURPLE)
    return pages


def member_status_page(m: Member, history: list[tuple[str, int, int | None]], minimum: int,
                       current: int | None = None) -> Page:
    title = f"🪙 {m.roblox_username}"
    lines = [f"Rank: **{m.rank}**" + (" · 🛡️ exempt from coin checks" if m.exempt else ""), ""]
    color = PURPLE if m.exempt else BLURPLE
    if not history:
        lines.append("No coin checks recorded yet.")
    else:
        lines.append("**Recent checks**")
        for label, total, gained in history:
            if gained is None:
                verdict = "starting point"
            elif m.exempt:
                verdict = f"+{gained:,}"
            else:
                verdict = f"+{gained:,} {'✅' if gained >= minimum else '❌'}"
            lines.append(f"`{label}` total {total:,} · {verdict}")
        last_gain = history[0][2]
        if last_gain is not None and not m.exempt:
            color = GREEN if last_gain >= minimum else RED
    fields = []
    if current is not None and not m.exempt:
        if history:
            so_far = current - history[0][1]
            need = max(0, minimum - so_far)
            fields.append(("This month so far",
                           f"Gained **{so_far:,}** since {history[0][0]}\n" +
                           ("✅ Minimum reached!" if need == 0 else f"Need **{need:,}** more to reach {minimum:,}"),
                           False))
            color = GREEN if need == 0 else AMBER
        else:
            fields.append(("This month so far", "No previous check to compare with yet.", False))
    return Page(title, "Status", lines, color, fields, note=f"Monthly minimum: {minimum:,}")


# ------------------------------------------------------------ role checks ---

def discord_check_pages(roster: list[Member], role_holder_ids: set[int], server_ids: set[int],
                        names: dict[int, str], role_name: str) -> list[Page]:
    missing, not_in_server, no_id, roster_ids, ok = [], [], [], set(), 0
    for m in roster:
        if m.discord_id is None:
            no_id.append(m.roblox_username)
            continue
        roster_ids.add(m.discord_id)
        if m.discord_id not in server_ids:
            not_in_server.append(f"{m.roblox_username} · ID {m.discord_id}")
        elif m.discord_id not in role_holder_ids:
            missing.append(f"**{m.roblox_username}** — <@{m.discord_id}> ({names.get(m.discord_id, '?')})")
        else:
            ok += 1
    extra = [f"<@{i}> ({names.get(i, '?')})" for i in sorted(role_holder_ids - roster_ids)]
    title = f"💬 Discord check — {role_name}"
    problems = len(missing) + len(extra) + len(not_in_server)
    pages = [Page(title, "Discord summary", [f"Comparing the roster with the **{role_name}** role."],
                  AMBER if problems else GREEN, fields=[
                      ("✅ Correct", str(ok), True), ("➕ Missing role", str(len(missing)), True),
                      ("➖ Shouldn't have it", str(len(extra)), True), ("🚪 Not in server", str(len(not_in_server)), True),
                      ("🔗 No Discord linked", str(len(no_id)), True)])]
    pages += section_pages(title, f"➕ Needs {role_name}", missing, AMBER, "Everyone on the roster has it 🎉")
    pages += section_pages(title, f"➖ Has {role_name}, not on roster", extra, AMBER, "Nobody extra 🎉")
    if not_in_server:
        pages += section_pages(title, "🚪 Not in the server", not_in_server, GREY)
    if no_id:
        pages += section_pages(title, "🔗 No Discord linked", no_id, GREY, note="Link them with /roster link.")
    return pages


def roblox_check_pages(roster: list[Member], ids: dict[str, int], holders: dict[int, tuple[str, str]]) -> list[Page]:
    missing, unknown, roster_uids, ok = [], [], set(), 0
    for m in roster:
        uid = m.roblox_id or ids.get(m.roblox_username.lower())
        if uid is None:
            unknown.append(m.roblox_username)
            continue
        roster_uids.add(uid)
        if uid in holders:
            ok += 1
        else:
            missing.append(m.roblox_username)
    extra = [f"{name} ({role})" for uid, (name, role) in sorted(holders.items(), key=lambda kv: kv[1][0].lower())
             if uid not in roster_uids]
    title = "🎮 Roblox group check"
    problems = len(missing) + len(extra) + len(unknown)
    pages = [Page(title, "Roblox summary", ["Comparing the roster with clan roles in the Roblox group."],
                  AMBER if problems else GREEN, fields=[
                      ("✅ Correct", str(ok), True), ("➕ Missing clan role", str(len(missing)), True),
                      ("➖ Shouldn't have it", str(len(extra)), True), ("❓ Name not found", str(len(unknown)), True)])]
    pages += section_pages(title, "➕ Needs a clan role", missing, AMBER, "Everyone has their role 🎉",
                           note="Search them in the group's Members page and set Clan Member.")
    pages += section_pages(title, "➖ Clan role, not on roster", extra, AMBER, "Nobody extra 🎉")
    if unknown:
        pages += section_pages(title, "❓ Roblox name not found", unknown, GREY, note="Check the spelling on the roster.")
    return pages


# ----------------------------------------------------------------- roster ---

def roster_pages(members: list[Member], latest: dict[str, Result] | None = None) -> list[Page]:
    title = f"📋 [gg] roster — {len(members)}/100"
    exempt = [m for m in members if m.exempt]
    regular = [m for m in members if not m.exempt]
    unlinked = [m.roblox_username for m in members if not m.discord_id]
    pages = [Page(title, "Overview", ["Full list attached as a spreadsheet file."], BLURPLE, fields=[
        ("👥 Members", str(len(members)), True), ("🛡️ Exempt", str(len(exempt)), True),
        ("🔗 Not linked", str(len(unlinked)), True), ("🪑 Open spots", str(max(0, 100 - len(members))), True)])]

    def line(m: Member) -> str:
        r = latest.get(m.roblox_username) if latest else None
        status = {"Pass": "✅", "Fail": "❌", "Baseline": "🆕", "Missing": "❓", "Exempt": "🛡️"}.get(r.status, "") if r else ""
        link = f"<@{m.discord_id}>" if m.discord_id else "*not linked*"
        return f"{status} **{m.roblox_username}** · {m.rank} · {link}".strip()

    pages += section_pages(title, "🛡️ Staff & exempt", [line(m) for m in exempt], PURPLE)
    pages += section_pages(title, "👥 Members", [line(m) for m in regular], BLURPLE)
    if unlinked:
        pages += section_pages(title, "🔗 Not linked to Discord", unlinked, GREY, note="Use /roster link.")
    return pages
