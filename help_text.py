"""Text for /help. Kept separate so it's easy to edit and test."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HelpEntry:
    name: str        # e.g. "/roster add"
    category: str    # Everyone, Roster, Coin checks, Bot
    staff: bool
    short: str       # one line for the overview and the dropdown
    how: str         # what to type
    details: str     # a few lines of explanation


COMMANDS: list[HelpEntry] = [
    HelpEntry("/mystatus", "Everyone", False,
              "See your own coin checks and how much you still need",
              "/mystatus  ·  /mystatus current:15000",
              "Only you can see the answer. Add **current** (your Contribution number in game right now) "
              "and it tells you how much more you need this month."),
    HelpEntry("/help", "Everyone", False,
              "This menu",
              "/help",
              "Pick any command from the menu to see what it does and how to use it."),

    HelpEntry("/roster add", "Roster", True,
              "Add someone to the clan with rank, Discord and starting coins",
              "/roster add roblox:pramishp4 discord_user:@1TAP coins:863128 rank:Member",
              "Checks the Roblox name is real, saves their Discord account and starting coins, "
              "and gives them **gg Member** plus their rank's role in Discord.\n"
              "**coins** is their Contribution number right now. Their next coin check measures from it."),
    HelpEntry("/roster rank", "Roster", True,
              "Change someone's clan rank (and their Discord role)",
              "/roster rank roblox:zayn rank:Officer",
              "Updates the roster and swaps their Discord rank role to match."),
    HelpEntry("/roster link", "Roster", True,
              "Link or change someone's Discord account",
              "/roster link roblox:pramishp4 discord_user:@1TAP",
              "Start typing their Discord name and pick them from the list, with no IDs needed. "
              "Their Discord roles are updated to match their rank."),
    HelpEntry("/roster remove", "Roster", True,
              "Take someone off the roster (and their clan roles)",
              "/roster remove roblox:pramishp4",
              "Removes them from the roster and takes away **gg Member** and their rank role. "
              "Set **keep_roles** to True to leave their Discord roles alone. Their coin history is kept."),
    HelpEntry("/roster start", "Roster", True,
              "Set or fix someone's starting coins",
              "/roster start roblox:pramishp4 coins:863128",
              "Use this if you got their starting number wrong, or added them without one."),
    HelpEntry("/roster exempt", "Roster", True,
              "Make someone exempt from coin checks (or not)",
              "/roster exempt roblox:zayn exempt:True",
              "Exempt members show in a separate list and never pass or fail."),
    HelpEntry("/roster note", "Roster", True,
              "Add a note to someone",
              "/roster note roblox:pramishp4 note:on vacation until Dec",
              "Leave the note empty to clear it."),
    HelpEntry("/roster list", "Roster", True,
              "Browse the roster",
              "/roster list",
              "Switch between by contribution, A–Z, staff & exempt and not linked. "
              "**📄 Spreadsheet** gives you the full list as a file."),
    HelpEntry("/roster reset", "Roster", True,
              "Wipe the whole roster and every coin check (admins only)",
              "/roster reset confirm:RESET",
              "Can't be undone. Server admins only, and you have to type RESET in capitals."),

    HelpEntry("/coins import", "Coin checks", True,
              "Import this month's totals and see who passed",
              "/coins import file:(attach .csv) label:Nov 2026",
              "The file has one `robloxusername,total` per line (Claude can make it from your screenshots). "
              "Results are posted here and in the staff channel."),
    HelpEntry("/coins results", "Coin checks", True,
              "Show the latest coin check again",
              "/coins results",
              "Use the menu to see Everyone, Failed, Passed, Missing, New or Exempt."),
    HelpEntry("/coins status", "Coin checks", True,
              "See one member's coin history",
              "/coins status roblox:pramishp4",
              "Shows their starting coins and every check since."),
    HelpEntry("/coins set", "Coin checks", True,
              "Fix one member's number in the latest check",
              "/coins set roblox:pramishp4 total:875128",
              "Use this when a number was read wrong. Their result updates straight away."),
    HelpEntry("/coins minimum", "Coin checks", True,
              "Change the monthly minimum (default 10,000)",
              "/coins minimum amount:10000",
              "Results use the new minimum straight away."),
    HelpEntry("/coins undo", "Coin checks", True,
              "Delete the latest import",
              "/coins undo confirm:Nov 2026",
              "Type the check's name exactly to confirm."),

    HelpEntry("/check", "Bot", True,
              "Compare the roster with Discord roles and the Roblox group",
              "/check  ·  /check what:Roblox group only",
              "Lists who needs **gg Member** or a Roblox clan role, and who has one but isn't on the roster."),
    HelpEntry("/update", "Bot", True,
              "Download the newest bot version and restart",
              "/update",
              "Run this after Claude says an update has been pushed. The bot is back in a few seconds."),
]

CATEGORY_EMOJI = {"Everyone": "👋", "Roster": "📋", "Coin checks": "🪙", "Bot": "⚙️"}


def overview() -> str:
    lines = ["-# Pick a command from the menu below to see how to use it. 🔒 = staff only", ""]
    for cat in CATEGORY_EMOJI:
        lines.append(f"**{CATEGORY_EMOJI[cat]} {cat}**")
        for c in (c for c in COMMANDS if c.category == cat):
            lines.append(f"`{c.name}`{' 🔒' if c.staff else ''} · {c.short}")
        lines.append("")
    return "\n".join(lines).strip()


def detail(name: str) -> str:
    c = next(c for c in COMMANDS if c.name == name)
    who = "🔒 Staff only (needs Manage Roles)" if c.staff else "👋 Anyone can use this"
    return f"-# {CATEGORY_EMOJI[c.category]} {c.category} · {who}\n\n{c.details}\n\n**How to use it**\n`{c.how}`"
