"""Text for /staffguide: how staff use the bot. Each page is one dropdown choice."""
from __future__ import annotations

PAGES: list[tuple[str, str, str, str]] = [   # (key, emoji, title, body)
    ("start", "👋", "Before You Start",
     "Staff use the bot to add, update and remove clan members. It keeps Discord roles and the Roblox group "
     "in step with the roster. Coin checks are run by the Clan Manager.\n\n"
     "• **Who can use staff commands:** anyone with the **Manage Roles** permission.\n"
     "• **Add, rank and remove replies are private** by default. Set **public** to True to show the channel.\n"
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
     "**rank** · Member, Officer, Admin or Leader (blank = Member).\n"
     "**exempt** · True for staff who don't do coin checks.\n"
     "**notes** · Anything staff should know.\n\n"
     "**What happens:**\n"
     "1. The bot checks the Roblox account is real.\n"
     "2. Discord: they get **gg Member** plus their rank's role.\n"
     "3. Roblox group: their join request is accepted (if sent) and they get their rank's role.\n"
     "4. You get a private summary, and a **New Clan Member** card goes to the roster log.\n\n"
     "Read the summary: if something couldn't be done (for example no join request yet), it says so. "
     "Get **coins** right, since their first coin check measures from it. Fix it with `/roster start`."),
    ("change", "✏️", "Changing a Member",
     "**`/roster rank`** · Promote or demote. Swaps their Discord and Roblox group roles and posts a "
     "**Promoted** / **Demoted** card.\n`/roster rank roblox:zayn rank:Officer`\n\n"
     "**`/roster link`** · Add or change someone's Discord account. Also gives them the right roles.\n"
     "`/roster link roblox:pramishp4 discord_user:@1TAP`\n\n"
     "**`/roster exempt`** · Make someone skip coin checks (usually staff), or stop skipping.\n"
     "`/roster exempt roblox:zayn exempt:True`\n\n"
     "**`/roster note`** · Leave a note, like \"on vacation until Dec\". Leave it empty to clear it.\n\n"
     "**`/roster start`** · Fix someone's starting coins if they were entered wrong.\n"
     "`/roster start roblox:pramishp4 coins:863128`\n\n"
     "-# The bot never changes anyone with a higher Roblox group role (like Head Administrator). "
     "It leaves them alone and says so."),
    ("remove", "👋", "Removing a Member",
     "Use `/roster remove` when someone leaves or is kicked from the clan.\n"
     "`/roster remove roblox:pramishp4`\n\n"
     "• Takes them off the roster.\n"
     "• Removes **gg Member** and their rank role in Discord.\n"
     "• Drops them to the basic role in the Roblox group.\n"
     "• Posts a **Left the Clan** card in the roster log.\n\n"
     "Set **keep_roles** to True to only take them off the roster. Their coin history is kept either way, "
     "so re-adding them later is safe."),
    ("lookup", "🔎", "Looking Things Up",
     "**`/roster list`** · The whole roster: by contribution, A–Z, staff & exempt, and not linked. "
     "**📄 Spreadsheet** downloads it.\n\n"
     "**`/coins status`** · One member's starting coins and every check since. Good for \"did I pass?\"\n\n"
     "**`/coins results`** · The latest coin check: Everyone, Failed, Passed, Missing, New and Exempt.\n\n"
     "**`/check`** · Who needs **gg Member** or a Roblox clan role, and who has one but isn't on the roster. "
     "It only reports, and also runs once a week in the staff channel. Fix what it finds with "
     "`/roster add`, `/roster link` or `/roster rank`.\n\n"
     "**`/leaderboard`** · Everyone's coins and gains, posted in the channel.\n\n"
     "-# On any list, use the menu to switch lists and the arrows to change pages."),
    ("bot", "⚙️", "Keeping the Bot Running",
     "**`/botinfo`** · Uptime, ping, version and the latest changes.\n"
     "**`/restart`** · Turns the bot off and on again. Use it if the bot seems stuck.\n"
     "**`/update`** · Gets the newest version. Run it when the Clan Manager says an update is out.\n"
     "**`/reminders`** · When the monthly coin check reminder goes off, plus a test ping.\n\n"
     "If the bot is offline or commands say **\"The application did not respond\"**, these can't reach it. "
     "Tell the Clan Manager."),
    ("manager", "🔒", "Leave to the Clan Manager",
     "You can see these, but please don't run them. They change coin check results for the whole clan.\n\n"
     "• `/coins import` · imports the monthly coin check\n"
     "• `/coins set` · changes someone's number in a coin check\n"
     "• `/coins undo` · deletes the latest coin check\n"
     "• `/coins minimum` · changes the monthly minimum\n"
     "• `/roster reset` · wipes everything (server admins only)\n\n"
     "If a member says their result is wrong, check `/coins status` and pass it on to the Clan Manager."),
    ("quick", "⚡", "Quick Reference",
     "**Someone joined the clan** · `/roster add`\n"
     "**Promoted or demoted** · `/roster rank`\n"
     "**Needs their Discord linked** · `/roster link`\n"
     "**Left the clan** · `/roster remove`\n"
     "**Starting coins are wrong** · `/roster start`\n"
     "**Staff shouldn't be coin checked** · `/roster exempt`\n"
     "**Check everyone's roles** · `/check`\n"
     "**One member's coins** · `/coins status`\n"
     "**The bot seems stuck** · `/restart`"),
]
