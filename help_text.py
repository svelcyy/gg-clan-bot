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
    HelpEntry("/userinfo", "Everyone", False,
              "Someone's Discord info, plus their clan rank and coins",
              "/userinfo  ·  /userinfo user:@1TAP  ·  /userinfo current:15000",
              "Shows their Discord profile (account age, badges, roles, when they joined) and, for clan members, "
              "their Roblox account, rank, Contribution and last coin check. Leave **user** empty for yourself. "
              "Add **current** (your Contribution in game right now) to see how much more you need this month."),
    HelpEntry("/claninfo", "Everyone", False,
              "About the clan: requirements to join and when signups open",
              "/claninfo",
              "Shows who runs the clan, what you need to join, and when signups are expected to open next "
              "(the 1st of every month). Tip: pinging the bot points people here too."),
    HelpEntry("/leaderboard", "Everyone", False,
              "See the latest coin check: everyone's coins and gains",
              "/leaderboard",
              "Shows every member's Discord, Roblox name, total coins and how much they gained, best first. "
              "Switch to A–Z with the menu. Everyone in the channel sees it (set **public** to False for just you)."),
    HelpEntry("/botinfo", "Everyone", False,
              "Bot stats: uptime, ping, version and latest changes",
              "/botinfo",
              "Shows how long the bot has been online, its ping to Discord, the version it's running, "
              "the roster size, the last coin check and the three most recent changes. Only you see it."),
    HelpEntry("/help", "Everyone", False,
              "This menu",
              "/help",
              "Pick any command from the menu to see what it does and how to use it."),

    HelpEntry("/roster add", "Roster", True,
              "Add someone to the clan with rank, Discord and starting coins",
              "/roster add roblox:pramishp4 discord_user:@1TAP coins:863128 rank:Member",
              "Checks the Roblox name is real, saves their Discord account and starting coins, "
              "gives them **gg Member** plus their rank's role in Discord, and sets their **Roblox group** role "
              "(accepting their join request if they've sent one).\n"
              "**coins** is their Contribution number right now (leave it empty for 0). Their next coin check measures from it.\n"
              "Only you see the reply. A 🆕 New Clan Member card (no pings) goes to the roster log channel."),
    HelpEntry("/roster rank", "Roster", True,
              "Change someone's clan rank (and their Discord role)",
              "/roster rank roblox:zayn rank:Officer",
              "Updates the roster and swaps their Discord rank role and Roblox group role to match. "
              "Only you see the reply. A ⬆️ Promoted / ⬇️ Demoted card (no pings) goes to the roster log channel."),
    HelpEntry("/roster link", "Roster", True,
              "Link or change someone's Discord account",
              "/roster link roblox:pramishp4 discord_user:@1TAP",
              "Start typing their Discord name and pick them from the list, with no IDs needed. "
              "Their Discord roles are updated to match their rank."),
    HelpEntry("/roster remove", "Roster", True,
              "Take someone off the roster (and their clan roles)",
              "/roster remove roblox:pramishp4",
              "Removes them from the roster, takes away **gg Member** and their rank role in Discord, "
              "and drops them to the basic role in the Roblox group. "
              "Set **keep_roles** to True to leave their roles alone. Their coin history is kept. "
              "Only you see the reply. A 👋 Left the Clan card (no pings) goes to the roster log channel."),
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
              "Import this month's totals, check the preview, then save",
              "/coins import label:Nov 2026  (then paste)  ·  or attach a file",
              "Leave **file** empty and a box opens: paste one `username number` per line "
              "(Claude can make the list from your screenshots).\n"
              "You get a private **preview** first: who matched, who's missing, who isn't on the roster, "
              "and anyone who changed their Roblox username (spotted by their Roblox account, so their "
              "Discord link and history move with them). Nothing is saved until you click **✅ Save**. "
              "Then the results are posted here and in the staff channel. Roster and Discord data are never changed, "
              "except to update a renamed Roblox username.\n"
              "Pick **mode: Starting coins only** to set everyone's starting coins in one go instead "
              "(nothing graded, no check saved)."),
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

    HelpEntry("/staffguide", "Bot", True,
              "The staff guide: how to add, rank and remove members",
              "/staffguide",
              "A short guide with a page for each job. Pick a page from the menu. "
              "Set **public** to True to show it to the channel."),
    HelpEntry("/check", "Bot", True,
              "Compare the roster with Discord roles and the Roblox group",
              "/check  ·  /check what:Roblox group only",
              "Lists who needs **gg Member** or a Roblox clan role, and who has one but isn't on the roster."),
    HelpEntry("/reminders", "Bot", True,
              "See when the reminders go off and send a test ping",
              "/reminders",
              "On the 1st of every month the bot pings you to do the coin check. "
              "It can also warn you before the host needs a restart (if RESTART_REMINDER_DAYS is set)."),
    HelpEntry("/restart", "Bot", True,
              "Restart the bot without opening the website",
              "/restart",
              "Turns the bot off and on again in a few seconds. Handy if something seems stuck, "
              "or when the restart reminder pings you. Also picks up any new update."),
    HelpEntry("/update", "Bot", True,
              "Download the newest bot version and restart",
              "/update",
              "Run this after Claude says an update has been pushed. The bot is back in a few seconds."),
]

# Clan Manager commands: need the Administrator permission
ADMIN_ONLY = {"/roster rank", "/roster start", "/roster exempt", "/roster reset", "/coins import", "/coins set",
              "/coins minimum", "/coins undo", "/update", "/restart", "/reminders"}

CATEGORY_EMOJI = {"Everyone": "👋", "Roster": "📋", "Coin checks": "🪙", "Bot": "⚙️"}


def overview() -> str:
    lines = ["-# Pick a command from the menu below to see how to use it. 🔒 = staff only · 👑 = Clan Manager only",
             "-# Replies that only you see have a **public** option to show them to everyone.", ""]
    for cat in CATEGORY_EMOJI:
        lines.append(f"### {CATEGORY_EMOJI[cat]} {cat}")
        for c in (c for c in COMMANDS if c.category == cat and c.name != "/help"):
            mark = " 👑" if c.name in ADMIN_ONLY else " 🔒" if c.staff else ""
            lines.append(f"`{c.name}`{mark}\n-# {c.short}")
        lines.append("")
    return "\n".join(lines).strip()


def detail(name: str) -> str:
    c = next(c for c in COMMANDS if c.name == name)
    who = ("👑 Clan Manager only (needs Administrator)" if c.name in ADMIN_ONLY
           else "🔒 Staff only (needs Manage Roles)" if c.staff else "👋 Anyone can use this")
    return f"-# {CATEGORY_EMOJI[c.category]} {c.category} · {who}\n\n{c.details}\n\n**How to use it**\n`{c.how}`"
