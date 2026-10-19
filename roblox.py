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


# ============================================================ Open Cloud ===
# Changing group roles needs an Open Cloud API key (ROBLOX_API_KEY) with the
# Groups read + write permissions. It acts as the account that created it.

CLOUD = "https://apis.roblox.com/cloud/v2"


def membership_id(user_id: int) -> str:
    """Roblox's membership id is the user id, base64url-encoded without padding."""
    import base64
    return base64.urlsafe_b64encode(str(user_id).encode()).decode().rstrip("=")


def plan_role_change(current: set[int], wanted: int | None, managed: set[int],
                     ranks: dict[int, int], names: dict[int, str],
                     ignore: set[int] = frozenset()) -> tuple[set[int], set[int], str | None]:
    """Decide which clan roles to add and remove.

    current: role ids the user has now · wanted: the clan role they should have (None = leaving the clan)
    managed: every clan role the bot is allowed to touch · ranks/names: role id -> rank number / name
    Returns (add, remove, reason_to_skip). Someone holding a higher role the bot doesn't manage
    (like Head Administrator) is left alone so they can't be demoted by accident.
    """
    target_rank = ranks.get(wanted, 0) if wanted else 0
    higher = [r for r in current
              if r not in managed and r not in ignore and ranks.get(r, 0) > max(target_rank, 1)]
    if higher:
        top = max(higher, key=lambda r: ranks.get(r, 0))
        return set(), set(), f"Left alone, because they have a higher group role ({names.get(top, top)})."
    add = {wanted} - current if wanted else set()
    remove = (current & managed) - ({wanted} if wanted else set())
    return add, remove, None


class GroupManager:
    def __init__(self, api_key: str, group_id: int, role_names: dict[str, str], ignore_names: set[str] = frozenset()):
        self.key, self.group = api_key, group_id
        self.ignore_names = {n.lower() for n in ignore_names}
        self.role_names = role_names          # clan rank -> group role name, e.g. {"Officer": "Clan Officer"}
        self.roles: dict[str, dict] = {}      # role name (lowercase) -> {"id", "rank", "name"}

    def _h(self) -> dict:
        return {"x-api-key": self.key, "Content-Type": "application/json", **UA}

    async def load_roles(self, session: aiohttp.ClientSession):
        data = await _get(session, f"https://groups.roblox.com/v1/groups/{self.group}/roles")
        self.roles = {r["name"].lower(): r for r in data["roles"]}

    def role_id(self, name: str) -> int | None:
        r = self.roles.get((name or "").lower())
        return r["id"] if r else None

    async def _call(self, session, method: str, path: str, json: dict | None = None, params=None):
        async with session.request(method, f"{CLOUD}{path}", headers=self._h(), json=json, params=params) as r:
            body = await r.text()
            if r.status >= 400:
                raise CloudError(r.status, body[:300])
            return await r.json(content_type=None) if body else {}

    async def membership(self, session, user_id: int) -> dict | None:
        data = await self._call(session, "GET", f"/groups/{self.group}/memberships",
                                params={"maxPageSize": 1, "filter": f"user == 'users/{user_id}'"})
        items = data.get("groupMemberships") or []
        return items[0] if items else None

    async def sync(self, session: aiohttp.ClientSession, user_id: int, rank: str | None) -> str:
        """Put the user in the right clan role. rank=None means they left the clan."""
        if not self.roles:
            await self.load_roles(session)
        joined = False
        mem = await self.membership(session, user_id)
        if mem is None and rank is not None:
            try:  # they may have a pending join request
                await self._call(session, "POST", f"/groups/{self.group}/join-requests/{user_id}:accept", json={})
                joined = True
                mem = await self.membership(session, user_id)
            except CloudError as e:
                if e.status in (400, 404):
                    return "Not in the group yet. Ask them to request to join, then run `/roster rank` to finish."
                raise
        if mem is None:
            return "Not in the group, so nothing was changed."
        current = {int(r.split("/")[-1]) for r in (mem.get("roles") or [mem.get("role")]) if r}
        wanted = self.role_id(self.role_names.get(rank, "")) if rank else None
        managed = {i for i in (self.role_id(n) for n in self.role_names.values() if n) if i}
        ranks = {r["id"]: r["rank"] for r in self.roles.values()}
        names = {r["id"]: r["name"] for r in self.roles.values()}
        ignore = {r["id"] for n, r in self.roles.items() if n in self.ignore_names}
        add, remove, skip = plan_role_change(current, wanted, managed, ranks, names, ignore)
        if skip:
            return skip
        mid = membership_id(user_id)
        for rid in add:
            await self._call(session, "POST", f"/groups/{self.group}/memberships/{mid}:assignRole",
                             json={"role": f"groups/{self.group}/roles/{rid}"})
        for rid in remove:
            try:
                await self._call(session, "POST", f"/groups/{self.group}/memberships/{mid}:unassignRole",
                                 json={"role": f"groups/{self.group}/roles/{rid}"})
            except CloudError as e:
                if e.status not in (400, 404):  # already gone (e.g. the new role replaced it)
                    raise
        parts = ["✅ Accepted their join request"] if joined else []
        if add:
            parts.append("➕ " + ", ".join(names.get(r, str(r)) for r in add))
        if remove:
            parts.append("➖ " + ", ".join(names.get(r, str(r)) for r in remove))
        return "\n".join(parts) or "Already correct."


class CloudError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"Roblox said {status}: {body}")
        self.status, self.body = status, body

    def friendly(self) -> str:
        if self.status in (401, 403):
            return ("Roblox refused the change. Check the API key has Groups read and write for [gg] Clan, "
                    "its IP restriction includes Wispbyte's address, and the role is below your own rank.")
        if self.status == 429:
            return "Roblox is busy right now. Try again in a minute."
        return str(self)
