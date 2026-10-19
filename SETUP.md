# [gg] Clan Bot v2: upgrade and commands

## Upgrading from the first bot on Wispbyte (about 5 minutes)

1. In Wispbyte, **Stop** the bot.
2. Open the **File Manager** and delete the old `main.py` and `checks.py`.
3. Upload all of these from this folder:
   `main.py`, `storage.py`, `reports.py`, `roblox.py`, `requirements.txt`, `seed_roster.csv`, `seed_totals.csv`
4. On the **Environment** page:
   - Keep `DISCORD_TOKEN` and `GUILD_ID` as they are.
   - Add **`STAFF_CHANNEL_ID`**, the ID of your staff channel (right-click the channel and choose **Copy Channel ID**). Coin check results and the weekly roster check get posted there.
   - `SHEET_URL` isn't used anymore. You can delete it or leave it.
5. Press **Start**. The console should say `Loaded the starting roster…` and then `Logged in as … — 81 members on the roster`.

On the first start, the bot loads today's roster (81 members, 11 exempt, Discord IDs) and the **18 Oct 2026** totals as everyone's starting point. Your first real coin check can then work out each member's gain straight away.

> The bot saves everything in a file called **`clan.db`**, which appears in the File Manager after the first start. **Never delete it.** It's the bot's memory. For a backup, use Wispbyte's Backups menu, or run `/roster list` and save the file it gives you.

---

## Monthly coin check (about 5 minutes)

1. In Bedwars, screenshot the clan's **Contribution** list from top to bottom.
2. Turn the screenshots into a list with one `username total` per line.
3. In Discord, run **`/coins import`**, attach the file and give it a name like `Nov 2026`.
4. The bot posts:
   - **Fail**: who gained less than the minimum, and by how much they were short
   - **Missing**: roster members who weren't in the import (left the clan, or the name was misread)
   - **Not on the roster**: names in the import the bot doesn't know
   - a spreadsheet file with everyone's numbers

Wrong number? `/coins set` fixes one member. Wrong file? `/coins undo` deletes the whole import.

You can also make the `.csv` yourself in Notepad or a spreadsheet: one line per member, `robloxusername,total`.

---

## All commands

### Staff only (needs the *Manage Roles* permission)

| Command | What it does |
|---|---|
| `/roster add` | Add a new member: Roblox username, their Discord account, rank, exempt yes/no. It checks the Roblox name is real. |
| `/roster remove` | Remove someone. Their coin history is kept. |
| `/roster link` | Link or change a member's Discord account. |
| `/roster exempt` | Turn coin-check exemption on or off. |
| `/roster rank` | Change rank (Leader, Admin, Officer, Member). |
| `/roster note` | Add a note to a member. |
| `/roster list` | Roster summary plus a spreadsheet file of everyone. |
| `/coins import` | Import a month's totals and post the results. |
| `/coins results` | Show the latest results again. |
| `/coins set` | Fix one member's total in the latest check. |
| `/coins status` | One member's coin history. |
| `/coins minimum` | Change the monthly minimum (default 10,000). |
| `/coins undo` | Delete the latest import. You type its name to confirm. |
| `/check` | Compare the roster with the gg Member role and the Roblox group. |

Names autocomplete, so start typing a Roblox username and pick it from the list.

**Paged results:** long results (coin checks, `/check`, `/roster list`) come as **one embed** with **⏮ ◀ ▶ ⏭** buttons and a **"Jump to a section…"** menu, so they don't flood the channel. Only the person who ran the command, or staff, can flip the pages. The buttons switch off after 15 minutes (24 hours for posts in the staff channel). Run the command again to browse after that.

### Everyone

| Command | What it does |
|---|---|
| `/mystatus` | Shows your last coin checks, only to you. Add your current in-game Contribution number (`current:`) and it tells you how much more you need this month. |

Members need their Discord linked (`/roster link`) for `/mystatus` to find them.

---

## How Pass and Fail work

The game shows **lifetime** contribution, so for each member the bot does:
**gained = this check's total − the previous check's total**

| Status | Meaning |
|---|---|
| Pass | gained at least the minimum |
| Fail | gained less, and it shows how much short |
| Baseline | new member with no previous total yet. Next month counts. |
| Missing | on the roster but not in this import |
| Exempt | staff or anyone marked exempt. Never passes or fails. |

The bot **never** removes roles, kicks anyone or DMs people. It only reports to staff.

## Troubleshooting

| Problem | Fix |
|---|---|
| Commands show twice | Restart the bot once. It cleans up the old copies. |
| `/mystatus` says it can't find me | A staff member needs to run `/roster link` for you. |
| Results show lots of "Missing" | Usernames in the file don't match the roster. Use the @ usernames, not display names. |
| `PrivilegedIntentsRequired` | Turn on Server Members Intent in the Developer Portal (Bot page) and save. |
