"""Everything the bot remembers, kept in one SQLite file (clan.db).

No Discord code in here, so it can be tested on its own.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

RANKS = ["Leader", "Admin", "Officer", "Member"]
DEFAULT_MINIMUM = 10_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    roblox_username TEXT PRIMARY KEY COLLATE NOCASE,
    roblox_id       INTEGER,
    discord_id      INTEGER,
    rank            TEXT NOT NULL DEFAULT 'Member',
    exempt          INTEGER NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT '',
    added_at        TEXT NOT NULL,
    start_total     INTEGER
);
CREATE TABLE IF NOT EXISTS checks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    label      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS totals (
    check_id        INTEGER NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
    roblox_username TEXT NOT NULL COLLATE NOCASE,
    total           INTEGER NOT NULL,
    PRIMARY KEY (check_id, roblox_username)
);
CREATE TABLE IF NOT EXISTS custom_roles (
    user_id         INTEGER PRIMARY KEY,
    role_id         INTEGER,
    primary_color   INTEGER NOT NULL,
    secondary_color INTEGER,
    status          TEXT NOT NULL,          -- active | removed (stopped boosting)
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS role_requests (
    channel_id      INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    primary_color   INTEGER NOT NULL,
    secondary_color INTEGER,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS former (
    roblox_username TEXT PRIMARY KEY COLLATE NOCASE,
    roblox_id       INTEGER,
    discord_id      INTEGER,
    start_total     INTEGER,
    removed_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Member:
    roblox_username: str
    roblox_id: int | None
    discord_id: int | None
    rank: str
    exempt: bool
    notes: str
    start_total: int | None = None   # their in-game Contribution when they were added
    added_at: str = ""


@dataclass
class Result:
    member: Member
    status: str            # Pass, Fail, Exempt, Baseline, Missing, New
    total: int | None      # total in this check
    previous: int | None   # total in the previous check
    gained: int | None
    short_by: int | None


class Store:
    def __init__(self, path: str = "clan.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(members)")}
        if "start_total" not in cols:  # databases made by older versions
            self.db.execute("ALTER TABLE members ADD COLUMN start_total INTEGER")
        self.db.execute("UPDATE members SET exempt=1 WHERE rank != 'Member'")   # staff never do coin checks
        self.db.commit()

    # ------------------------------------------------------------ settings --
    def get_minimum(self) -> int:
        row = self.db.execute("SELECT value FROM settings WHERE key='minimum'").fetchone()
        return int(row["value"]) if row else DEFAULT_MINIMUM

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.db.commit()

    # -------------------------------------------------------- custom roles --
    def custom_role(self, user_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM custom_roles WHERE user_id=?", (user_id,)).fetchone()

    def custom_roles(self, status: str | None = None) -> list[sqlite3.Row]:
        if status:
            return self.db.execute("SELECT * FROM custom_roles WHERE status=?", (status,)).fetchall()
        return self.db.execute("SELECT * FROM custom_roles").fetchall()

    def save_custom_role(self, user_id: int, role_id: int | None, primary: int, secondary: int | None,
                         status: str = "active") -> None:
        self.db.execute("INSERT OR REPLACE INTO custom_roles(user_id,role_id,primary_color,secondary_color,status,"
                        "updated_at) VALUES(?,?,?,?,?,?)", (user_id, role_id, primary, secondary, status, _now()))
        self.db.commit()

    def add_role_request(self, channel_id: int, user_id: int, primary: int, secondary: int | None) -> None:
        self.db.execute("INSERT OR REPLACE INTO role_requests VALUES(?,?,?,?,?)",
                        (channel_id, user_id, primary, secondary, _now()))
        self.db.commit()

    def role_request(self, channel_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM role_requests WHERE channel_id=?", (channel_id,)).fetchone()

    def role_request_for(self, user_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM role_requests WHERE user_id=?", (user_id,)).fetchone()

    def close_role_request(self, channel_id: int) -> None:
        self.db.execute("DELETE FROM role_requests WHERE channel_id=?", (channel_id,))
        self.db.commit()

    def set_minimum(self, amount: int) -> None:
        self.db.execute("INSERT INTO settings(key,value) VALUES('minimum',?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(amount),))
        self.db.commit()

    # ------------------------------------------------------------- members --
    @staticmethod
    def _member(row) -> Member:
        return Member(row["roblox_username"], row["roblox_id"], row["discord_id"],
                      row["rank"], bool(row["exempt"]), row["notes"], row["start_total"], row["added_at"])

    def get_member(self, roblox_username: str) -> Member | None:
        row = self.db.execute("SELECT * FROM members WHERE roblox_username=?",
                              (roblox_username.strip(),)).fetchone()
        return self._member(row) if row else None

    def member_by_discord(self, discord_id: int) -> Member | None:
        row = self.db.execute("SELECT * FROM members WHERE discord_id=?", (discord_id,)).fetchone()
        return self._member(row) if row else None

    def members(self) -> list[Member]:
        """Exempt first (Leader > Admin > Officer > Member), then everyone else A-Z."""
        rows = self.db.execute("SELECT * FROM members").fetchall()
        ms = [self._member(r) for r in rows]
        rank_pos = {r: i for i, r in enumerate(RANKS)}
        return sorted(ms, key=lambda m: (not m.exempt, rank_pos.get(m.rank, 9) if m.exempt else 0,
                                         m.roblox_username.lower()))

    def add_member(self, roblox_username: str, roblox_id: int | None = None, discord_id: int | None = None,
                   rank: str = "Member", exempt: bool = False, notes: str = "",
                   start_total: int | None = None) -> bool:
        """Returns False if that Roblox username is already on the roster."""
        if self.get_member(roblox_username):
            return False
        exempt = exempt or rank != "Member"   # staff are always exempt
        self.db.execute(
            "INSERT INTO members(roblox_username,roblox_id,discord_id,rank,exempt,notes,added_at,start_total) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (roblox_username.strip(), roblox_id, discord_id, rank, int(exempt), notes, _now(), start_total))
        self.db.commit()
        return True

    def rename_member(self, old: str, new: str) -> bool:
        """Someone changed their Roblox username: keep their roster entry, Discord link and coin history."""
        if old.lower() == new.lower():
            cur = self.db.execute("UPDATE members SET roblox_username=? WHERE roblox_username=?", (new, old))
        else:
            if self.get_member(new):
                return False
            cur = self.db.execute("UPDATE members SET roblox_username=? WHERE roblox_username=?", (new, old))
            self.db.execute("UPDATE OR REPLACE totals SET roblox_username=? WHERE roblox_username=?", (new, old))
        self.db.commit()
        return cur.rowcount > 0

    def remove_member(self, roblox_username: str) -> bool:
        m = self.get_member(roblox_username)
        if m:   # remember them, so re-adding them later picks up where they left off
            self.db.execute("INSERT OR REPLACE INTO former(roblox_username,roblox_id,discord_id,start_total,removed_at) "
                            "VALUES(?,?,?,?,?)", (m.roblox_username, m.roblox_id, m.discord_id, m.start_total, _now()))
        cur = self.db.execute("DELETE FROM members WHERE roblox_username=?", (roblox_username.strip(),))
        self.db.commit()
        return cur.rowcount > 0

    def former_discord_id(self, roblox_username: str, roblox_id: int | None = None) -> int | None:
        """The Discord account someone had linked the last time they were on the roster, if any."""
        row = self.db.execute("SELECT discord_id FROM former WHERE roblox_id=? OR roblox_username=? "
                              "ORDER BY removed_at DESC LIMIT 1", (roblox_id or -1, roblox_username.strip())).fetchone()
        return row["discord_id"] if row else None

    def update_member(self, roblox_username: str, **fields) -> bool:
        allowed = {"roblox_id", "discord_id", "rank", "exempt", "notes", "start_total"}
        if "rank" in fields:   # staff are always exempt; going back to Member makes them checked again
            fields.setdefault("exempt", fields["rank"] != "Member")
        sets = {k: (int(v) if k == "exempt" else v) for k, v in fields.items() if k in allowed}
        if not sets:
            return False
        sql = "UPDATE members SET " + ", ".join(f"{k}=?" for k in sets) + " WHERE roblox_username=?"
        cur = self.db.execute(sql, (*sets.values(), roblox_username.strip()))
        self.db.commit()
        return cur.rowcount > 0

    def discord_id_owner(self, discord_id: int) -> list[str]:
        return [r["roblox_username"] for r in
                self.db.execute("SELECT roblox_username FROM members WHERE discord_id=?", (discord_id,))]

    # -------------------------------------------------------------- checks --
    def checks(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM checks ORDER BY id").fetchall()

    def latest_check_id(self) -> int | None:
        row = self.db.execute("SELECT MAX(id) AS id FROM checks").fetchone()
        return row["id"]

    def previous_check_id(self, check_id: int) -> int | None:
        row = self.db.execute("SELECT MAX(id) AS id FROM checks WHERE id < ?", (check_id,)).fetchone()
        return row["id"]

    def check_created(self, check_id: int) -> str:
        row = self.db.execute("SELECT created_at FROM checks WHERE id=?", (check_id,)).fetchone()
        return row["created_at"] if row else ""

    def check_label(self, check_id: int) -> str:
        row = self.db.execute("SELECT label FROM checks WHERE id=?", (check_id,)).fetchone()
        return row["label"] if row else "?"

    def totals(self, check_id: int) -> dict[str, int]:
        return {r["roblox_username"].lower(): r["total"] for r in
                self.db.execute("SELECT roblox_username,total FROM totals WHERE check_id=?", (check_id,))}

    def import_check(self, label: str, totals: dict[str, int], created_by: str = "") -> tuple[int, list[str]]:
        """Save a new coin check. Returns (check_id, names that aren't on the roster).
        Names not on the roster are still saved, in case they're added later."""
        cur = self.db.execute("INSERT INTO checks(label,created_at,created_by) VALUES(?,?,?)",
                              (label, _now(), created_by))
        cid = cur.lastrowid
        self.db.executemany("INSERT OR REPLACE INTO totals(check_id,roblox_username,total) VALUES(?,?,?)",
                            [(cid, n.strip(), int(t)) for n, t in totals.items()])
        self.db.commit()
        unknown = [n for n in totals if not self.get_member(n)]
        return cid, unknown

    def set_total(self, check_id: int, roblox_username: str, total: int) -> None:
        self.db.execute("INSERT INTO totals(check_id,roblox_username,total) VALUES(?,?,?) "
                        "ON CONFLICT(check_id,roblox_username) DO UPDATE SET total=excluded.total",
                        (check_id, roblox_username.strip(), total))
        self.db.commit()

    def delete_check(self, check_id: int) -> None:
        self.db.execute("DELETE FROM checks WHERE id=?", (check_id,))
        self.db.commit()

    # ------------------------------------------------------------- results --
    def results(self, check_id: int) -> list[Result]:
        prev_id = self.previous_check_id(check_id)
        return self._compute(self.totals(check_id), self.totals(prev_id) if prev_id else {},
                             self.check_created(check_id))

    def preview(self, totals: dict[str, int]) -> list[Result]:
        """What the results would be if these totals were imported now (nothing is saved)."""
        latest = self.latest_check_id()
        return self._compute({k.lower(): v for k, v in totals.items()},
                             self.totals(latest) if latest else {}, _now())

    def _compute(self, now: dict[str, int], before: dict[str, int], created: str) -> list[Result]:
        minimum = self.get_minimum()
        out = []
        for m in self.members():
            key = m.roblox_username.lower()
            total, previous = now.get(key), before.get(key)
            if previous is None:          # first check since they joined: compare with their starting coins
                previous = m.start_total
            gained = total - previous if total is not None and previous is not None else None
            if gained is not None and gained < 0:
                gained = total    # their number went down: they left and rejoined in game, which resets it to 0
            if m.exempt:
                status = "Exempt"
            elif total is None and m.added_at > created:
                status = "New"            # joined after this check was imported
            elif total is None:
                status = "Missing"
            elif previous is None:
                status = "Baseline"
            elif gained >= minimum:
                status = "Pass"
            else:
                status = "Fail"
            short = minimum - gained if status == "Fail" else None
            out.append(Result(m, status, total, previous, gained, short))
        return out

    def history(self, roblox_username: str, limit: int = 6) -> list[tuple[str, int, int | None]]:
        """[(check label, total, gained since the check before)] newest first."""
        rows = self.db.execute(
            "SELECT c.id, c.label, t.total FROM totals t JOIN checks c ON c.id=t.check_id "
            "WHERE t.roblox_username=? ORDER BY c.id", (roblox_username.strip(),)).fetchall()
        m = self.get_member(roblox_username)
        out, prev = [], None
        if m and m.start_total is not None:
            out.append(("Joined", m.start_total, None))
            prev = m.start_total
        for r in rows:
            gain = None if prev is None else r["total"] - prev
            if gain is not None and gain < 0:
                gain = r["total"]   # their number went down: Contribution was reset by leaving and rejoining
            out.append((r["label"], r["total"], gain))
            prev = r["total"]
        return list(reversed(out))[:limit]

    def reset_all(self) -> None:
        """Delete every member and every coin check. Settings (like the minimum) are kept."""
        self.db.execute("DELETE FROM totals")
        self.db.execute("DELETE FROM checks")
        self.db.execute("DELETE FROM members")
        self.db.execute("DELETE FROM sqlite_sequence WHERE name='checks'")
        self.db.commit()

    # ------------------------------------------------------------- CSV i/o --
    def export_csv(self) -> str:
        cid = self.latest_check_id()
        res = {r.member.roblox_username: r for r in self.results(cid)} if cid else {}
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Roblox Username", "Rank", "Exempt?", "Discord ID", "Previous Total",
                    "Current Total", "Gained", "Status", "Short By", "Notes"])
        for m in self.members():
            r = res.get(m.roblox_username)
            w.writerow([m.roblox_username, m.rank, "Yes" if m.exempt else "",
                        str(m.discord_id or ""),
                        r.previous if r and r.previous is not None else "",
                        r.total if r and r.total is not None else "",
                        r.gained if r and r.gained is not None else "",
                        r.status if r else "", r.short_by if r and r.short_by else "", m.notes])
        return buf.getvalue()


LINE = re.compile(r"^\s*@?([A-Za-z0-9_]{3,20})\b[\s,;:|=>\-–—]*\"?([\d][\d,.\s]*)\"?\s*$")


def parse_totals_csv(text: str) -> dict[str, int]:
    """Read 'username total' lines in almost any layout:
    pramishp4,875128 · pramishp4 875,128 · @pramishp4 - 875128 · pramishp4,"875,128" · tabs from a spreadsheet.
    Header rows and blank lines are skipped. If a name appears twice, the last line wins."""
    out: dict[str, int] = {}
    for line in text.replace("\r", "").split("\n"):
        m = LINE.match(line)
        if not m:
            continue
        digits = re.sub(r"[^0-9]", "", m.group(2))
        if digits:
            out[m.group(1)] = int(digits)
    return out


def match_totals(totals: dict[str, int], members: list["Member"], ids: dict[str, int]):
    """Match imported names to the roster.

    ids: imported name (lowercase) -> Roblox user id, for names that aren't on the roster.
    Returns (matched {roster username: total}, renames [(old roster name, new name)], unknown [names]).
    A renamed account is recognised by its Roblox user id, so their Discord link and history stay attached.
    """
    by_name = {m.roblox_username.lower(): m for m in members}
    by_id = {m.roblox_id: m for m in members if m.roblox_id}
    matched: dict[str, int] = {}
    renames: list[tuple[str, str]] = []
    unknown: list[str] = []
    for name, total in totals.items():
        m = by_name.get(name.lower())
        if m is None and ids.get(name.lower()) in by_id:
            m = by_id[ids[name.lower()]]
            if m.roblox_username.lower() != name.lower():
                renames.append((m.roblox_username, name))
        if m is None:
            unknown.append(name)
        else:
            matched[m.roblox_username] = total
    return matched, renames, unknown
