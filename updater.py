"""Keeps the bot's code in sync with its GitHub repository.

How it works:
  1. Download the repository as a .zip from github.com (the normal "Download ZIP" link).
     This is NOT GitHub's API, so it isn't limited to 60 checks an hour, which matters on
     free hosts where many bots share one internet address.
  2. Read files.txt inside the zip: the list of code files to keep in sync.
  3. Replace only those files. Never touches .env, clan.db, or anything else.

Only uses the Python standard library, so it works even before packages are installed.
"""
from __future__ import annotations

import io
import os
import time
import urllib.request
import zipfile
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
        return bool(self.changed)


def current_version(dest: Path = HERE) -> str:
    try:
        return (dest / ".version").read_text().strip()
    except OSError:
        return "unknown"


def _download_zip(repo: str, branch: str, token: str | None) -> bytes:
    # cache-buster so a just-pushed change isn't served from a stale cache
    url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip?t={int(time.time())}"
    req = urllib.request.Request(url, headers={"User-Agent": "gg-clan-bot-updater"})
    if token:  # private repositories
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/zipball/{branch}",
                                     headers={"User-Agent": "gg-clan-bot-updater",
                                              "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def apply_zip(data: bytes, dest: Path = HERE) -> SyncResult:
    """Install the code files from a GitHub zip. Separate from the download so it can be tested."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    sha = zf.comment.decode(errors="ignore").strip() or "unknown"  # GitHub puts the commit id here
    root = zf.namelist()[0].split("/")[0]                           # e.g. gg-clan-bot-main/

    def read(name: str) -> bytes:
        return zf.read(f"{root}/{name}")

    files = [l.strip() for l in read("files.txt").decode().splitlines() if l.strip() and not l.startswith("#")]
    old = current_version(dest)
    changed = []
    for name in files:
        if name in PROTECTED or "/" in name or "\\" in name or name.startswith("."):
            continue  # safety: only plain files in the bot folder, never secrets or data
        new = read(name)
        target = dest / name
        if target.exists() and target.read_bytes() == new:
            continue
        tmp = target.with_name(target.name + ".new")
        tmp.write_bytes(new)
        os.replace(tmp, target)
        changed.append(name)
    (dest / ".version").write_text(sha)
    return SyncResult(old, sha, "", changed)


def sync(repo: str, branch: str = "main", token: str | None = None, dest: Path = HERE) -> SyncResult:
    """Download and install the newest code. Raises on network/GitHub errors."""
    return apply_zip(_download_zip(repo, branch, token), dest)
