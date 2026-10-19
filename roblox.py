"""Small helpers for Roblox's public web API (no login needed)."""
from __future__ import annotations

import asyncio

import aiohttp

UA = {"User-Agent": "gg-clan-bot/2.0"}


async def _get(session: aiohttp.ClientSession, url: str, params=None):
    for attempt in range(4):
        async with session.get(url, params=params, headers=UA) as r:
            if r.status == 429:  # rate limited: wait and retry
                await asyncio.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return await r.json()
    raise RuntimeError("Roblox kept rate-limiting the bot. Try again in a minute.")


async def lookup_usernames(session: aiohttp.ClientSession, usernames: list[str]) -> dict[str, tuple[int, str]]:
    """requested name (lowercase) -> (userId, exact current username)."""
    out: dict[str, tuple[int, str]] = {}
    for i in range(0, len(usernames), 100):
        body = {"usernames": usernames[i:i + 100], "excludeBannedUsers": False}
        async with session.post("https://users.roblox.com/v1/usernames/users", json=body, headers=UA) as r:
            r.raise_for_status()
            data = await r.json()
        for item in data.get("data", []):
            out[item["requestedUsername"].lower()] = (item["id"], item["name"])
    return out


async def clan_role_holders(session: aiohttp.ClientSession, group_id: int, min_rank: int,
                            ignore_roles: set[str]) -> dict[int, tuple[str, str]]:
    """userId -> (username, role name) for everyone at min_rank or above."""
    roles = (await _get(session, f"https://groups.roblox.com/v1/groups/{group_id}/roles"))["roles"]
    holders: dict[int, tuple[str, str]] = {}
    for role in sorted(roles, key=lambda x: x["rank"]):  # higher role wins if listed twice
        if role["rank"] < min_rank or role["name"].lower() in ignore_roles:
            continue
        cursor = None
        while True:
            params = {"limit": 100, "sortOrder": "Asc"}
            if cursor:
                params["cursor"] = cursor
            page = await _get(session, f"https://groups.roblox.com/v1/groups/{group_id}/roles/{role['id']}/users",
                              params)
            for u in page["data"]:
                holders[u["userId"]] = (u["username"], role["name"])
            cursor = page.get("nextPageCursor")
            if not cursor:
                break
    return holders
