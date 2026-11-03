"""[gg] Clan bot: starts everything. main.py runs this after checking GitHub for updates.

    core.py      settings, the bot, the database and shared helpers
    commands/    every slash command, one file each

Everyone:        /userinfo /leaderboard /claninfo /customrole /botinfo /help
Staff:           /roster add | remove | link | note | list, /coins results | status, /check, /staffguide
Clan Manager:    /roster rank | exempt | start | sync, /coins import | set | undo | minimum,
                 /backup, /boostersetup, /status, /update, /restart, /reminders
"""
import os
import sys
import time

import discord

import datetime as dt

from core import HERE, RUNNING_VERSION, TOKEN, bot, log, store

import commands  # noqa: E402,F401  (registers every command)

BLOCKED_WAIT_MINUTES = 15


def run():
    log.info("Starting [gg] bot v%s", RUNNING_VERSION)
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.HTTPException as e:
        if e.status != 429:
            raise
        # Discord is blocking the host's shared address for a while (Cloudflare error 1015). Crashing would make
        # the host restart the bot straight away, which only keeps the block going, so wait quietly instead.
        log.warning("Discord is temporarily blocking this server's internet address (it's shared with other bots "
                    "on the host). Trying again in %d minutes.", BLOCKED_WAIT_MINUTES)
        if not store.get_setting("blocked_since"):   # so the bot can announce when it's back
            store.set_setting("blocked_since", dt.datetime.now(dt.timezone.utc).isoformat())
        time.sleep(BLOCKED_WAIT_MINUTES * 60)
        os.execv(sys.executable, [sys.executable, str(HERE / "main.py")])


if __name__ == "__main__":
    run()
