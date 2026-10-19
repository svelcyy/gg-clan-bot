"""Everything the bot remembers, kept in one SQLite file (clan.db).

No Discord code in here, so it can be tested on its own.
"""
from __future__ import annotations

import csv
import io
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
    added_at        TEXT NOT NULL
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


@dataclass
class Result:
    member: Member
    status: str            # Pass, Fail, Exempt, Baseline, Missing
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
        self.db.commit()

    # ------------------------------------------------------------ settings --
    def get_minimum(self) -> int:
        row = self.db.execute("SELECT value FROM settings WHERE key='minimum'").fetchone()
        return int(row["value"]) if row else DEFAULT_MINIMUM

    def set_minimum(self, amount: int) -> None:
        self.db.execute("INSERT INTO settings(key,value) VALUES('minimum',?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(amount),))
        self.db.commit()

    # ------------------------------------------------------------- members --
    @staticmethod
    def _member(row) -> Member:
        return Member(row["roblox_username"], row["roblox_id"], row["discord_id"],
                      row["rank"], bool(row["exempt"]), row["notes"])

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
                   rank: str = "Member", exempt: bool = False, notes: str = "") -> bool:
        """Returns False if that Roblox username is already on the roster."""
        if self.get_member(roblox_username):
            return False
        self.db.execute(
            "INSERT INTO members(roblox_username,roblox_id,discord_id,rank,exempt,notes,added_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (roblox_username.strip(), roblox_id, discord_id, rank, int(exempt), notes, _now()))
        self.db.commit()
        return True

    def remove_member(self, roblox_username: str) -> bool:
        cur = self.db.execute("DELETE FROM members WHERE roblox_username=?", (roblox_username.strip(),))
        self.db.commit()
        return cur.rowcount > 0

    def update_member(self, roblox_username: str, **fields) -> bool:
        allowed = {"roblox_id", "discord_id", "rank", "exempt", "notes"}
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
        minimum = self.get_minimum()
        now = self.totals(check_id)
        prev_id = self.previous_check_id(check_id)
        before = self.totals(prev_id) if prev_id else {}
        out = []
        for m in self.members():
            key = m.roblox_username.lower()
            total, previous = now.get(key), before.get(key)
            gained = total - previous if total is not None and previous is not None else None
            if m.exempt:
                status = "Exempt"
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
        out, prev = [], None
        for r in rows:
            out.append((r["label"], r["total"], None if prev is None else r["total"] - prev))
            prev = r["total"]
        return list(reversed(out))[:limit]

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

    def seed_if_empty(self, roster_csv: str, totals_csv: str | None, totals_label: str) -> bool:
        if self.db.execute("SELECT COUNT(*) AS n FROM members").fetchone()["n"]:
            return False
        for row in csv.DictReader(io.StringIO(roster_csv)):
            did = row.get("discord_id", "").strip()
            self.add_member(row["roblox_username"], None, int(did) if did.isdigit() else None,
                            row.get("rank") or "Member", row.get("exempt", "").lower() == "yes",
                            row.get("notes", ""))
        if totals_csv:
            totals = parse_totals_csv(totals_csv)
            self.import_check(totals_label, totals, "seed")
        return True


def parse_totals_csv(text: str) -> dict[str, int]:
    """Accepts 'roblox_username,total' rows (header optional). Commas inside numbers are fine
    if the number is quoted, e.g. pramishp4,"863,128"."""
    out: dict[str, int] = {}
    for row in csv.reader(io.StringIO(text.strip())):
        if len(row) < 2:
            continue
        name, raw = row[0].strip().lstrip("@"), "".join(row[1:]).strip()
        digits = raw.replace(",", "").replace(" ", "")
        if not name or not digits.isdigit():
            continue  # header row or junk
        out[name] = int(digits)
    return out
