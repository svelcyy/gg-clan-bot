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
if repo and os.getenv("AUTO_UPDATE", "on").lower() not in ("off", "no", "false", "0"):
    print(f"[updater] Checking GitHub ({repo}) for the newest code…", flush=True)
    try:
        result = updater.sync(repo, os.getenv("GITHUB_BRANCH", "main"), os.getenv("GITHUB_TOKEN"))
        if result.changed:
            print(f"[updater] Updated to {result.new_sha[:7]}: {', '.join(result.changed)}", flush=True)
            if "requirements.txt" in result.changed:
                print("[updater] Installing new packages…", flush=True)
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(HERE / "requirements.txt")])
        else:
            print(f"[updater] Code is up to date ({result.new_sha[:7]})", flush=True)
    except Exception as e:
        print(f"[updater] Couldn't check GitHub ({e}). Starting with the current code.", flush=True)

if not (HERE / "bot.py").exists():
    print("[updater] bot.py is missing and couldn't be downloaded. Check the line above for why "
          "(usually GitHub couldn't be reached). Restart to try again.", flush=True)
    sys.exit(1)

import bot  # noqa: E402

bot.run()
