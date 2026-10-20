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
    HelpEntry("/userinfo", "General", False,
              "Someone's Discord info, plus their clan rank and coins",
              "/userinfo  ·  /userinfo user:@1TAP  ·  /userinfo current:15000",
              "Shows their Discord profile (account age, badges, roles, when they joined) and, for clan members, "
              "their Roblox account, rank, Contribution and last coin check. Leave **user** empty for yourself. "
              "Add **current** (your Contribution in game right now) to see how much more you need this month."),
    HelpEntry("/claninfo", "General", False,
              "About the clan: requirements to join and when signups open",
              "/claninfo",
              "Shows who runs the clan, what you need to join, and when signups are expected to open next "
              "(the 1st of every month). Tip: pinging the bot points people here too."),
    HelpEntry("/leaderboard", "General", False,
              "See the latest coin check: everyone's coins and gains",
              "/leaderboard",
              "Shows every member's Discord, Roblox name, total coins and how much they gained, best first. "
              "Switch to A–Z with the menu. Everyone in the channel sees it (set **public** to False for just you)."),
    HelpEntry("/customrole", "Boosters", False,
              "Request your own custom role color (solid or gradient)",
              "/customrole color:#75117e  ·  /customrole color:#75117e color2:#ff7ad9",
              "A perk for **server boosters**. Pick one color for a solid role, or two for a gradient. "
              "You'll see a preview first. Once you send it, staff review it and you'll get a DM when it's "
              "approved or denied. You can send one request a week.\n"
              "The role is named after you. If you stop boosting it's removed, and it comes back automatically "
              "if you boost again. Run it again any time to ask for a new color."),
    HelpEntry("/boostersetup", "Boosters", True,
              "Choose the category where custom role requests open",
              "/boostersetup category:Staff",
              "Request channels are created inside this category. Remembered after restarts."),
    HelpEntry("/botinfo", "General", False,
              "Bot stats: uptime, ping, version and latest changes",
              "/botinfo",
              "Shows how long the bot has been online, its ping to Discord, the version it's running, "
              "the roster size, the last coin check and the three most recent changes. Only you see it."),
    HelpEntry("/help", "General", False,
              "This menu",
              "/help",
              "Pick any command from the menu to see what it does and how to use it."),

    HelpEntry("/roster add", "Roster", True,
              "Add someone to the clan with rank, Discord and starting coins",
              "/roster add roblox:pramishp4 discord_user:@1TAP coins:863128 rank:Member",
              "Checks the Roblox name is real, saves their Discord account and starting coins, "
              "gives them **gg Member** plus their rank's role in Discord, and sets their **Roblox group** role "
              "(if they're already in the group).\n"
              "**coins** is their Contribution number right now (leave it empty for 0). Their next coin check measures from it.\n"
              "Only you see the reply. A New Clan Member card (no pings) goes to the roster log channel."),
    HelpEntry("/roster rank", "Roster", True,
              "Change someone's clan rank (and their Discord role)",
              "/roster rank roblox:zayn rank:Officer",
              "Updates the roster and swaps their Discord rank role and Roblox group role to match. "
              "Staff keep **Clan Member** in the group as well as their staff role. "
              "Only you see the reply. A Promoted / Demoted card (no pings) goes to the roster log channel."),
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
              "Only you see the reply. A Left the Clan card (no pings) goes to the roster log channel."),
    HelpEntry("/roster start", "Roster", True,
              "Set or fix someone's starting coins",
              "/roster start roblox:pramishp4 coins:863128",
              "Use this if you got their starting number wrong, or added them without one."),
    HelpEntry("/roster exempt", "Roster", True,
              "Make someone exempt from coin checks (or not)",
              "/roster exempt roblox:zayn exempt:True",
              "Exempt members show in a separate list and never pass or fail."),
    HelpEntry("/roster sync", "Roster", True,
              "Check everyone's roles and fix any that are wrong",
              "/roster sync  ·  /roster sync remove_extras:True",
              "Goes through the whole roster and makes sure everyone has the right **Discord roles** "
              "(gg Member + their rank role) and **Roblox group roles** (Clan Member + their staff role), "
              "fixing anything that's wrong. Staff are also made exempt from coin checks.\n"
              "It also lists people who have clan roles but aren't on the roster. Set **remove_extras** to True "
              "to take those roles away too.\nTakes a minute or two. Only you see the results."),
    HelpEntry("/roster note", "Roster", True,
              "Add a note to someone",
              "/roster note roblox:pramishp4 note:on vacation until Dec",
              "Leave the note empty to clear it."),
    HelpEntry("/roster list", "Roster", True,
              "Browse the roster",
              "/roster list",
              "Switch between by contribution, A–Z, staff & exempt and not linked. "
              "**Spreadsheet** gives you the full list as a file."),
    HelpEntry("/roster reset", "Roster", True,
              "Wipe the whole roster and every coin check (admins only)",
              "/roster reset confirm:RESET",
              "Can't be undone. Server admins only, and you have to type RESET in capitals."),

    HelpEntry("/coins import", "Coin Checks", True,
              "Import this month's totals, check the preview, then save",
              "/coins import label:Nov 2026  (then paste)  ·  or attach a file",
              "Leave **file** empty and a box opens: paste one `username number` per line "
              "(one line per member, copied from the in-game clan list).\n"
              "You get a private **preview** first: who matched, who's missing, who isn't on the roster, "
              "and anyone who changed their Roblox username (spotted by their Roblox account, so their "
              "Discord link and history move with them). Nothing is saved until you click **Save**. "
              "Then the results are posted here and in the staff channel. Roster and Discord data are never changed, "
              "except to update a renamed Roblox username.\n"
              "Pick **mode: Starting coins only** to set everyone's starting coins in one go instead "
              "(nothing graded, no check saved)."),
    HelpEntry("/coins results", "Coin Checks", True,
              "Show the latest coin check again",
              "/coins results",
              "Use the menu to see Everyone, Failed, Passed, Missing, New or Exempt."),
    HelpEntry("/coins status", "Coin Checks", True,
              "See one member's coin history",
              "/coins status roblox:pramishp4",
              "Shows their starting coins and every check since."),
    HelpEntry("/coins set", "Coin Checks", True,
              "Fix one member's number in the latest check",
              "/coins set roblox:pramishp4 total:875128",
              "Use this when a number was read wrong. Their result updates straight away."),
    HelpEntry("/coins minimum", "Coin Checks", True,
              "Change the monthly minimum (default 10,000)",
              "/coins minimum amount:10000",
              "Results use the new minimum straight away."),
    HelpEntry("/coins undo", "Coin Checks", True,
              "Delete the latest import",
              "/coins undo confirm:Nov 2026",
              "Type the check's name exactly to confirm."),

    HelpEntry("/staffguide", "Staff Tools", True,
              "The staff guide: how to add, rank and remove members",
              "/staffguide",
              "A short guide with a page for each job. Pick a page from the menu. "
              "Set **public** to True to show it to the channel."),
    HelpEntry("/check", "Staff Tools", True,
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
    HelpEntry("/status", "Bot", True,
              "Change the text under the bot's name",
              "/status text:SIGNUPS OPEN!!  ·  /status  (clears it)",
              "Changes the bot's status straight away and keeps it after restarts. "
              "Handy for things like signups opening and closing."),
    HelpEntry("/update", "Bot", True,
              "Download the newest bot version and restart",
              "/update",
              "Gets the newest version of the bot. The bot is back in a few seconds."),
]

# Clan Manager commands: need the Administrator permission
ADMIN_ONLY = {"/boostersetup", "/status", "/roster sync", "/roster rank", "/roster start", "/roster exempt", "/roster reset", "/coins import", "/coins set",
              "/coins minimum", "/coins undo", "/update", "/restart", "/reminders"}

# (name, emoji, one line for the menu). Order = order in the menu.
CATEGORIES = [
    ("General", "👋", "Clan info, leaderboard, user info and bot stats"),
    ("Boosters", "💎", "Perks for server boosters, like custom role colors"),
    ("Roster", "📋", "Add, remove, link and rank clan members"),
    ("Coin Checks", "🪙", "Monthly coin check results and history"),
    ("Staff Tools", "🛡️", "Role checks and the staff guide"),
    ("Bot", "⚙️", "Status, updates, restarts and reminders"),
]
CATEGORY_EMOJI = {name: emoji for name, emoji, _ in CATEGORIES}


def mark(c: HelpEntry) -> str:
    return " 👑" if c.name in ADMIN_ONLY else " 🔒" if c.staff else ""


def in_category(cat: str) -> list[HelpEntry]:
    return [c for c in COMMANDS if c.category == cat and c.name != "/help"]


def home() -> tuple[str, list[tuple[str, str, bool]]]:
    """The main menu: (description, fields)."""
    desc = ("`/help` · Shows this menu.\n"
            "Choose a category from the dropdown to see its commands.")
    half = (len(CATEGORIES) + 1) // 2
    col = lambda cats: "\n".join(f"> **{n}** · {len(in_category(n))}" for n, _, _ in cats)
    fields = [("Categories", col(CATEGORIES[:half]), True),
              ("\u200b", col(CATEGORIES[half:]), True),
              ("Guides", "> Staff Guide · `/staffguide`\n> Clan Info · `/claninfo`", False),
              ("Key", "> 🔒 Staff only · 👑 Clan Manager only\n"
                        "> Most private replies have a **public** option to show everyone.", False)]
    return desc, fields


def category_page(cat: str) -> str:
    desc = next(d for n, _, d in CATEGORIES if n == cat)
    lines = [f"-# {desc}", ""]
    for c in in_category(cat):
        lines += [f"**`{c.name}`**{mark(c)}", f"> {c.short}", ""]
    lines.append("-# Pick a command below for the details.")
    return "\n".join(lines)


def detail(name: str) -> str:
    c = next(c for c in COMMANDS if c.name == name)
    who = ("👑 Clan Manager only (needs Administrator)" if c.name in ADMIN_ONLY
           else "🔒 Staff only (needs Manage Roles)" if c.staff else "Anyone can use this")
    return f"-# {c.category} · {who}\n\n{c.details}\n\n**How to use it**\n> `{c.how}`"
