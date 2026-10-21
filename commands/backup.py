"""/backup now, channel and restore, plus the daily backup."""
from __future__ import annotations

import sqlite3

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

# Every day the bot posts a copy of its data file (clan.db) to a private channel. /backup restore puts one back.

def backup_file() -> discord.File:
    """A consistent copy of the database, safe to take while the bot is running."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    dest = sqlite3.connect(path)
    store.db.backup(dest)
    dest.close()
    data = Path(path).read_bytes()
    os.remove(path)
    stamp = dt.datetime.now(reminder_tz()).strftime("%Y-%m-%d_%H%M")
    return discord.File(io.BytesIO(data), filename=f"gg-backup_{stamp}.db")


def backup_summary() -> str:
    members = store.members()
    last = store.latest_check_id()
    return " · ".join([f"{len(members)} members", f"{len(store.custom_roles())} custom roles",
                       f"last coin check: {store.check_label(last)}" if last else "no coin checks yet"])


async def post_backup(reason: str) -> discord.Message | None:
    channel_id = store.get_setting("backup_channel") or STAFF_CHANNEL_ID
    channel = bot.get_channel(int(channel_id)) if channel_id else None
    if channel is None:
        log.warning("No backup channel set")
        return None
    e = simple(backup_summary(), BLURPLE, "💾 Backup")
    e.set_footer(text=f"{reason} · Restore with /backup restore")
    e.timestamp = discord.utils.utcnow()
    return await channel.send(embed=e, file=backup_file(), allowed_mentions=discord.AllowedMentions.none())


@tasks.loop(time=dt.time(hour=4, tzinfo=reminder_tz()))
async def daily_backup():
    try:
        if not await post_backup("Daily backup"):
            await staff_alert("backup", "Backups Aren't Being Saved",
                              "The daily backup couldn't be posted because no backup channel is set. "
                              "Run `/backup channel` and pick a private staff channel.", every_hours=24)
    except Exception as e:
        log.exception("Daily backup failed")
        await staff_alert("backup", "Daily Backup Failed", f"The daily backup couldn't be saved ({e}).",
                          every_hours=24)


daily_backup.before_loop(wait_ready)


backup_group = app_commands.Group(name="backup", description="Save or restore the bot's data",
                                  default_permissions=discord.Permissions(administrator=True), guild_only=True)


@backup_group.command(name="now", description="Save a backup right now")
@admin_only
async def backup_now(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    msg = await post_backup(f"Saved by {interaction.user.name}")
    if msg:
        await interaction.followup.send(embed=simple(f"Backup saved in {msg.channel.mention}.", GREEN,
                                                     "💾 Backup Saved"), ephemeral=True)
    else:
        await interaction.followup.send(embed=simple(
            "There's no backup channel yet. Run `/backup channel` first.", AMBER), ephemeral=True)


@backup_group.command(name="channel", description="Choose the private channel where backups are saved")
@admin_only
@app_commands.describe(channel="A private staff channel (backups contain the whole roster)")
async def backup_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    store.set_setting("backup_channel", str(channel.id))
    await interaction.response.send_message(embed=simple(
        f"Backups will be saved in {channel.mention} every day at 4 AM.\n"
        "Keep this channel private: backups contain the whole roster.", GREEN, "💾 Backup Channel Set"),
        ephemeral=True)


@backup_group.command(name="restore", description="Replace the bot's data with a backup file")
@admin_only
@app_commands.describe(file="A gg-backup_….db file from the backup channel",
                       confirm="Type RESTORE in capitals to confirm")
async def backup_restore(interaction: discord.Interaction, file: discord.Attachment, confirm: str):
    if confirm != "RESTORE":
        await interaction.response.send_message(embed=simple(
            "Nothing changed. To restore, type `RESTORE` in capitals in **confirm**.", AMBER), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    if file.size > 50_000_000 or not file.filename.endswith(".db"):
        await interaction.followup.send(embed=simple("That isn't a backup file. Use a `gg-backup_….db` file.", RED),
                                        ephemeral=True)
        return
    data = await file.read()
    tmp = Path(DB_PATH + ".restore")
    tmp.write_bytes(data)
    try:   # make sure it really is one of our backups before touching anything
        check = sqlite3.connect(tmp)
        count = check.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        check.execute("SELECT COUNT(*) FROM checks").fetchone()
        check.close()
    except sqlite3.Error:
        tmp.unlink(missing_ok=True)
        await interaction.followup.send(embed=simple("That file isn't a valid backup, so nothing changed.", RED),
                                        ephemeral=True)
        return
    try:
        await post_backup(f"Automatic copy before a restore by {interaction.user.name}")
    except Exception:
        log.exception("Couldn't save a pre-restore backup")
    store.db.close()
    os.replace(tmp, DB_PATH)
    store.__init__(DB_PATH)
    await interaction.followup.send(embed=simple(
        f"Restored **{file.filename}** ({count} members).\nThe data from just before was saved to the backup "
        "channel, in case you need it.", GREEN, "💾 Backup Restored"), ephemeral=True)
    alert = simple(f"{handle(interaction.user)} restored the backup **{esc(file.filename)}**.", AMBER, "💾 Backup Restored")
    await post_alert(alert)


GROUPS.append(backup_group)
BACKGROUND_TASKS.append((daily_backup, lambda: True))
