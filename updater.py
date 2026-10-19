"""Keeps the bot's code in sync with its GitHub repository.

How it works:
  1. Ask GitHub for the newest commit on the branch (one API call).
  2. Read files.txt from that commit: the list of code files to keep in sync.
  3. Download each file from that exact commit and replace the local copy.

It never touches .env, clan.db, or anything not listed in files.txt.
Only uses the Python standard library, so it works even before packages are installed.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
PROTECTED = {".env", "clan.db", ".version"}


@dataclass
class SyncResult:
    old_sha: str
    new_sha: str
    message: str = ""
    changed: list[str] = field(default_factory=list)

    @property
    def updated(self) -> bool:
        return self.old_sha != self.new_sha or bool(self.changed)


def _request(url: str, token: str | None, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "gg-clan-bot-updater", "Accept": accept})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def current_version(dest: Path = HERE) -> str:
    try:
        return (dest / ".version").read_text().strip()
    except OSError:
        return "unknown"


def sync(repo: str, branch: str = "main", token: str | None = None, dest: Path = HERE) -> SyncResult:
    """Download the newest code. Raises on network/GitHub errors (callers decide what to do)."""
    commit = json.loads(_request(f"https://api.github.com/repos/{repo}/commits/{branch}", token))
    sha = commit["sha"]
    message = commit.get("commit", {}).get("message", "").split("\n")[0]
    old = current_version(dest)

    def fetch(path: str) -> bytes:
        # contents API at a fixed commit: never stale, works for private repos with a token
        return _request(f"https://api.github.com/repos/{repo}/contents/{path}?ref={sha}", token,
                        accept="application/vnd.github.raw")

    files = [l.strip() for l in fetch("files.txt").decode().splitlines()
             if l.strip() and not l.startswith("#")]
    changed = []
    for name in files:
        if name in PROTECTED or "/" in name or "\\" in name or name.startswith("."):
            continue  # safety: only plain files in the bot folder, never secrets or data
        data = fetch(name)
        target = dest / name
        if target.exists() and target.read_bytes() == data:
            continue
        tmp = target.with_suffix(target.suffix + ".new")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        changed.append(name)
    (dest / ".version").write_text(sha)
    return SyncResult(old, sha, message, changed)
