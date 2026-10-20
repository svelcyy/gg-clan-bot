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
PROTECTED = {".env", "clan.db", ".version", ".packages"}


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


def latest_sha(repo: str, branch: str) -> str | None:
    """Ask GitHub which commit the branch points at right now.

    Uses git's own "info/refs" address: it is never cached and isn't limited to 60 calls an hour
    like GitHub's API. Returns None if it can't tell (then we fall back to the branch download).
    """
    url = f"https://github.com/{repo}.git/info/refs?service=git-upload-pack"
    req = urllib.request.Request(url, headers={"User-Agent": "git/2.40 gg-clan-bot-updater"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode(errors="ignore")
    except Exception:
        return None
    for line in text.split("\n"):
        if line.rstrip().endswith(f"refs/heads/{branch}"):
            sha = line.strip().split(" ")[0][-40:]   # strip git's 4-character length prefix
            if len(sha) == 40:
                return sha
    return None


def _download_zip(repo: str, branch: str, token: str | None) -> bytes:
    if token:  # private repositories
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/zipball/{branch}",
                                     headers={"User-Agent": "gg-clan-bot-updater",
                                              "Authorization": f"Bearer {token}"})
    else:
        # Download the exact newest commit: a commit's zip never changes, so it's never stale.
        sha = latest_sha(repo, branch)
        ref = sha or f"refs/heads/{branch}"
        req = urllib.request.Request(f"https://github.com/{repo}/archive/{ref}.zip?t={int(time.time())}",
                                     headers={"User-Agent": "gg-clan-bot-updater"})
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
