"""Text for /staffguide: how staff use the bot. Each page is one dropdown choice."""
from __future__ import annotations

PAGES: list[tuple[str, str, str, str]] = [   # (key, emoji, title, body)
    ("start", "👋", "Before You Start",
     "Staff use the bot to add, update and remove clan members. It keeps Discord roles and the Roblox group "
     "in step with the roster. Coin checks are run by the Clan Manager.\n\n"
     "• **Who can use staff commands:** anyone with the **Manage Roles** permission.\n"
     "• **Replies are private** by default. On add and remove, set **public** to True to show the channel.\n"
     "• **The bot never pings anyone.** Names in replies and log cards are plain text.\n"
     "• **Roster changes are logged** in the roster log channel, so other staff can see what changed.\n"
     "• **Picking a member:** start typing their Roblox username in **roblox** and pick them from the list. "
     "For Discord, start typing their name in **discord_user**.\n"
     "• **Forgot something?** `/help` explains every command."),
    ("add", "🆕", "Adding a New Member",
     "Use `/roster add` once a player has joined the clan in game.\n"
     "`/roster add roblox:pramishp4 discord_user:@1TAP coins:863128 rank:Member`\n\n"
     "**roblox** · Their Roblox **username** (the @ name, not the display name). Required.\n"
     "**discord_user** · Their Discord account, if they're in the server.\n"
     "**coins** · Their **Contribution** number in the clan list right now (blank = 0).\n"
     "**rank** · Leave it as Member. Only the Clan Manager can add staff ranks.\n"
     "**notes** · Anything staff should know.\n\n"
     "**What happens:**\n"
     "1. The bot checks the Roblox account is real.\n"
     "2. Discord: they get **gg Member** plus their rank's role.\n"
     "3. Roblox group: they get their rank's role (they need to be in the group already).\n"
     "4. You get a private summary, and a **New Clan Member** card goes to the roster log.\n\n"
     "Read the summary: if something couldn't be done (for example they're not in the Roblox group yet), it says so. "
     "Get **coins** right, since their first coin check measures from it. If it's wrong, tell the Clan Manager."),
    ("change", "✏️", "Changing a Member",
     "**`/roster link`** · Add or change someone's Discord account. Also gives them the right roles.\n"
     "`/roster link roblox:pramishp4 discord_user:@1TAP`\n\n"
     "**`/roster note`** · Leave a note, like \"on vacation until Dec\". Leave it empty to clear it.\n"
     "`/roster note roblox:pramishp4 note:on vacation until Dec`\n\n"
     "**Promotions, demotions, exemptions and starting coins** are handled by the Clan Manager "
     "(`/roster rank`, `/roster exempt`, `/roster start`). If one is needed, let them know.\n\n"
     "-# The bot never changes anyone with a higher Roblox group role (like Head Administrator). "
     "It leaves them alone and says so."),
    ("remove", "👋", "Removing a Member",
     "Use `/roster remove` when someone leaves or is kicked from the clan.\n"
     "`/roster remove roblox:pramishp4`\n\n"
     "• Takes them off the roster.\n"
     "• Removes **gg Member** and their rank role in Discord.\n"
     "• Drops them to the basic role in the Roblox group.\n"
     "• Posts a **Left the Clan** card in the roster log.\n\n"
     "You can't remove yourself, or anyone your rank or higher. Those go through the Clan Manager.\n\n"
     "Set **keep_roles** to True to only take them off the roster. Their coin history is kept either way, "
     "so re-adding them later is safe."),
    ("lookup", "🔎", "Looking Things Up",
     "**`/roster list`** · The whole roster: by contribution, A–Z, staff & exempt, and not linked. "
     "**📄 Spreadsheet** downloads it.\n\n"
     "**`/coins status`** · One member's starting coins and every check since. Good for \"did I pass?\"\n\n"
     "**`/coins results`** · The latest coin check: Everyone, Failed, Passed, Missing, New and Exempt.\n\n"
     "**`/check`** · Who needs **gg Member** or a Roblox clan role, and who has one but isn't on the roster. "
     "It only reports, and also runs once a week in the staff channel. Fix what it finds with "
     "`/roster add` or `/roster link`, or ask the Clan Manager for rank changes.\n\n"
     "**`/leaderboard`** · Everyone's coins and gains, posted in the channel.\n\n"
     "-# On any list, use the menu to switch lists and the arrows to change pages."),
    ("bot", "⚙️", "If the Bot Has a Problem",
     "**`/botinfo`** · Uptime, ping, version and the latest changes.\n\n"
     "If the bot seems stuck, is offline, or commands say **\"The application did not respond\"**, "
     "tell the Clan Manager. They can restart or update it."),
    ("manager", "👑", "Clan Manager Only",
     "These need the **Administrator** permission. If you don't have it, they won't work for you.\n\n"
     "• `/roster rank` · promotions and demotions\n"
     "• `/roster exempt` · coin check exemptions (staff ranks are exempt automatically)\n"
     "• `/roster start` · fixing starting coins\n"
     "• `/coins import`, `/coins set`, `/coins undo`, `/coins minimum` · coin checks\n"
     "• `/update`, `/restart`, `/reminders` · running the bot\n"
     "• `/roster reset` · wipes everything\n\n"
     "If a member says their coin check result is wrong, check `/coins status` and pass it on to the Clan Manager."),
    ("quick", "⚡", "Quick Reference",
     "**Someone joined the clan** · `/roster add`\n"
     "**Someone left the clan** · `/roster remove`\n"
     "**Needs their Discord linked** · `/roster link`\n"
     "**Leave a note on someone** · `/roster note`\n"
     "**Check everyone's roles** · `/check`\n"
     "**One member's coins** · `/coins status`\n"
     "**Promotion, demotion, exemption or wrong coins** · ask the Clan Manager\n"
     "**The bot has a problem** · tell the Clan Manager"),
]
