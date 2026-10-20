"""Start here (Wispbyte runs this file).

1. If GITHUB_REPO is set, download the newest bot code from GitHub.
2. Start the bot.
If GitHub can't be reached, the bot still starts with the code it already has.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

try:
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except ImportError:
    pass

import updater  # noqa: E402

repo = os.getenv("GITHUB_REPO") or "svelcyy/gg-clan-bot"
if repo and os.getenv("BOT_AUTO_UPDATE", "on").lower() not in ("off", "no", "false", "0"):
    print(f"[updater] Checking GitHub ({repo}) for the newest code…", flush=True)
    try:
        result = updater.sync(repo, os.getenv("GITHUB_BRANCH", "main"), os.getenv("GITHUB_TOKEN"))
        if result.changed:
            print(f"[updater] Updated to {result.new_sha[:7]}: {', '.join(result.changed)}", flush=True)
        else:
            print(f"[updater] Code is up to date ({result.new_sha[:7]})", flush=True)
    except Exception as e:
        print(f"[updater] Couldn't check GitHub ({e}). Starting with the current code.", flush=True)



def install_packages():
    """Install requirements.txt whenever it changed since the last install (including changes /update made)."""
    import hashlib
    req = HERE / "requirements.txt"
    marker = HERE / ".packages"
    if not req.exists():
        return
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    if marker.exists() and marker.read_text().strip() == digest:
        return
    print("[updater] Installing packages…", flush=True)
    cmd = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(req)]
    ok = subprocess.run(cmd).returncode == 0 or subprocess.run(cmd + ["--user"]).returncode == 0
    if ok:
        marker.write_text(digest)
        print("[updater] Packages ready.", flush=True)
    else:
        print("[updater] Couldn't install some packages. The bot will still start.", flush=True)


try:
    install_packages()
except Exception as e:
    print(f"[updater] Package check failed ({e}).", flush=True)

if not (HERE / "bot.py").exists():
    print("[updater] bot.py is missing and couldn't be downloaded. Check the line above for why "
          "(usually GitHub couldn't be reached). Restart to try again.", flush=True)
    sys.exit(1)

import bot  # noqa: E402

bot.run()
