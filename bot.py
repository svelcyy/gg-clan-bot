"""[gg] Clan bot: starts everything. main.py runs this after checking GitHub for updates.

    core.py      settings, the bot, the database and shared helpers
    commands/    every slash command, one file each

Everyone:        /userinfo /leaderboard /claninfo /customrole /botinfo /help
Staff:           /roster add | remove | link | note | list, /coins results | status, /check, /staffguide
Clan Manager:    /roster rank | exempt | start | sync | reset, /coins import | set | undo | minimum,
                 /backup, /boostersetup, /status, /update, /restart, /reminders
"""
from core import RUNNING_VERSION, TOKEN, bot, log

import commands  # noqa: E402,F401  (registers every command)


def run():
    log.info("Starting [gg] bot v%s", RUNNING_VERSION)
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    run()
