"""/customrole and /boostersetup: booster custom roles, plus the hourly booster check."""
from __future__ import annotations

import colorpreview
import sqlite3

from core import *  # noqa: F401,F403  (shared settings, bot, database and helpers)

# Boosters ask for a custom colour (solid or gradient). A private channel opens for the approvers, who
# click Approve or Deny. The role is named after the booster, isn't hoisted and has no permissions.
# If they stop boosting, the role is deleted; if they boost again, it comes back automatically.

def is_approver(member: discord.Member) -> bool:
    if is_admin(member):
        return True
    return any(r in member.roles for r in approver_roles(member.guild))


def approver_roles(guild: discord.Guild) -> list[discord.Role]:
    return [r for r in (find_role(guild, n) for n in CUSTOMROLE_APPROVERS) if r]


def color_text(primary: int, secondary: int | None) -> str:
    return f"`#{primary:06X}` → `#{secondary:06X}`" if secondary is not None else f"`#{primary:06X}`"


async def dm(user: discord.abc.User, text: str):
    try:
        await user.send(embed=simple(text, BLURPLE))
    except discord.HTTPException:
        pass   # their DMs are closed


async def apply_custom_role(guild: discord.Guild, member: discord.Member, primary: int,
                            secondary: int | None) -> tuple[int, str]:
    """Create or update the member's custom role with these colours. Returns (role id, warning or "")."""
    colors = {"primary_color": primary, "secondary_color": secondary, "tertiary_color": None}
    saved = store.custom_role(member.id)
    role = guild.get_role(saved["role_id"]) if saved and saved["role_id"] else None
    if role is None and saved and saved["role_id"]:
        try:
            role = next((r for r in await guild.fetch_roles() if r.id == saved["role_id"]), None)
        except discord.HTTPException:
            role = None
    if role is None:   # they may already have a custom role staff made by hand: take that one over
        names = {member.name.lower(), member.display_name.lower()}
        role = next((r for r in member.roles if r.name.lower() in names and not r.managed
                     and r.permissions.value == 0 and not r.is_default()), None)
    if role is not None:
        await bot.http.request(discord.http.Route("PATCH", "/guilds/{guild_id}/roles/{role_id}",
                                                  guild_id=guild.id, role_id=role.id),
                               json={"name": member.name, "colors": colors}, reason="[gg] custom role update")
        role_id = role.id
    else:
        data = await bot.http.create_role(guild.id, reason="[gg] booster custom role", name=member.name,
                                          colors=colors, hoist=False, mentionable=False, permissions="0")
        role_id = int(data["id"])
    await member.add_roles(discord.Object(role_id), reason="[gg] booster custom role")
    store.save_custom_role(member.id, role_id, primary, secondary, "active")
    return role_id, await place_custom_role(guild, member, role_id)


async def place_custom_role(guild: discord.Guild, member: discord.Member, role_id: int, alert: bool = True) -> str:
    """Move the custom role above the member's other coloured roles, so its colour is the one that shows.
    Returns a warning if the bot's own role is too low to do that, otherwise ""."""
    try:
        roles = await guild.fetch_roles()
    except discord.HTTPException:
        return ""
    by_id = {r.id: r for r in roles}
    custom = by_id.get(role_id)
    me = by_id.get(guild.me.top_role.id) if guild.me else None
    if custom is None or me is None:
        return ""
    held = {r.id for r in member.roles}
    colored = [r for r in roles if r.id in held and r.id != role_id and not r.is_default() and r.colour.value]
    highest = max((r.position for r in colored), default=0)
    if custom.position > highest:
        return ""                                   # already on top of their other colours
    if highest >= me.position:
        blocker = max(colored, key=lambda r: r.position)
        warning = (f"Their **{blocker.name}** role is above the bot's role, so its color still shows. "
                   f"In Server Settings › Roles, drag the bot's role above **{blocker.name}**. The bot then moves "
                   "custom roles into place by itself within an hour.")
        if alert:   # only when a request is approved; the hourly check stays quiet about it
            await staff_alert(f"customrole-position:{member.id}", "Custom Role Color Hidden", warning,
                              every_hours=24 * 7)
        return warning
    try:
        await bot.http.move_role_position(guild.id, [{"id": role_id, "position": highest}],   # takes their spot, they shift down
                                          reason="[gg] custom role above their other colours")
    except discord.HTTPException:
        log.warning("Couldn't move custom role %s", role_id)
    return ""


async def delete_custom_role(guild: discord.Guild, user_id: int, reason: str):
    saved = store.custom_role(user_id)
    if not saved or saved["status"] != "active":
        return
    if saved["role_id"]:
        try:
            await bot.http.delete_role(guild.id, saved["role_id"], reason=reason)
        except discord.HTTPException:
            pass   # already gone
    store.save_custom_role(user_id, None, saved["primary_color"], saved["secondary_color"], "removed")


def request_embed(member: discord.Member, primary: int, secondary: int | None,
                  current: sqlite3.Row | None) -> tuple[discord.Embed, discord.File | None]:
    e = discord.Embed(title="🎨 Custom Role Request", color=primary,
                      description=f"**{handle(member)}** is asking for a custom role.")
    e.add_field(name="Style", value="Gradient" if secondary is not None else "Solid", inline=True)
    e.add_field(name="Color", value=color_text(primary, secondary), inline=True)
    e.add_field(name="Role Name", value=f"@{esc(member.name)}", inline=True)
    if current and current["status"] == "active":
        e.add_field(name="Current Color", value=color_text(current["primary_color"], current["secondary_color"]),
                    inline=False)
    e.set_thumbnail(url=member.display_avatar.url)
    e.set_footer(text="Approve or deny below · Clan Officers and above can decide")
    e.timestamp = discord.utils.utcnow()
    file = None
    png = colorpreview.render(member.name, primary, secondary)
    if png:
        file = discord.File(png, filename="preview.png")
        e.set_image(url="attachment://preview.png")
    return e, file


async def request_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    """Where request channels go: set with /boostersetup, or CUSTOMROLE_CATEGORY_ID on the host."""
    raw = store.get_setting("customrole_category") or CUSTOMROLE_CATEGORY_ID
    if not raw or not str(raw).strip().isdigit():
        return None
    cid = int(str(raw).strip())
    channel = guild.get_channel(cid)
    if channel is None:
        try:
            channel = await guild.fetch_channel(cid)
        except discord.HTTPException:
            channel = None
    if not isinstance(channel, discord.CategoryChannel):
        log.warning("Custom role category %s not found (or it isn't a category)", cid)
        return None
    return channel


class CustomRoleReview(discord.ui.View):
    """Approve / Deny buttons in a request channel. Persistent, so they still work after a restart."""

    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member) and is_approver(interaction.user):
            return True
        await interaction.response.send_message("Only Clan Officers and above can approve or deny custom roles.", ephemeral=True)
        return False

    async def _finish(self, interaction: discord.Interaction, title: str, color: int):
        for item in self.children:
            item.disabled = True
        e = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else simple("")
        e.title, e.colour = title, color
        e.set_footer(text=f"{title} by {interaction.user.name} · This channel closes in 10 seconds")
        store.close_role_request(interaction.channel_id)
        try:
            await interaction.edit_original_response(embed=e, view=self)
        except discord.HTTPException:
            pass
        await asyncio.sleep(10)
        try:
            await interaction.channel.delete(reason="[gg] custom role request closed")
        except discord.HTTPException:
            pass

    async def _start(self, interaction: discord.Interaction):
        """Answer Discord straight away (it gives up after 3 seconds) and claim the request so a double
        click can't handle it twice. Returns the request, or None if someone already handled it."""
        await interaction.response.defer()
        req = store.role_request(interaction.channel_id)
        if not req or interaction.channel_id in _handling:
            await interaction.followup.send("This request was already handled.", ephemeral=True)
            return None
        _handling.add(interaction.channel_id)
        return req

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="gg:customrole:approve")
    async def approve(self, interaction: discord.Interaction, _):
        req = await self._start(interaction)
        if not req:
            return
        try:
            guild = interaction.guild
            try:
                member = await guild.fetch_member(req["user_id"])
            except discord.NotFound:
                await interaction.followup.send("They've left the server, so there's nothing to approve.",
                                                ephemeral=True)
                await self._finish(interaction, "❌ Closed (left the server)", RED)
                return
            if not member.premium_since:
                await interaction.followup.send(
                    "⚠️ They're not boosting any more, so the role wasn't created. You can deny this request.",
                    ephemeral=True)
                return
            try:
                _, warning = await apply_custom_role(guild, member, req["primary_color"], req["secondary_color"])
            except discord.HTTPException as err:
                log.exception("Custom role failed")
                await interaction.followup.send(
                    f"⚠️ Couldn't create the role ({err.status}). Make sure the bot has **Manage Roles** and its "
                    "role is high in the role list.", ephemeral=True)
                return
            await dm(member, "Your custom role color was approved! Enjoy your new look in **[gg] Clan**.")
            await post_alert(simple(f"Approved for **{handle(member)}** by {handle(interaction.user)} · "
                                    f"{color_text(req['primary_color'], req['secondary_color'])}",
                                    req["primary_color"], "🎨 Custom Role Approved"))
            if warning:
                await interaction.channel.send(embed=simple(warning, AMBER, "⚠️ Color Hidden"))
            await self._finish(interaction, "✅ Approved", GREEN)
        finally:
            _handling.discard(interaction.channel_id)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="gg:customrole:deny")
    async def deny(self, interaction: discord.Interaction, _):
        req = await self._start(interaction)
        if not req:
            return
        try:
            user = bot.get_user(req["user_id"])
            if user is None:
                try:
                    user = await bot.fetch_user(req["user_id"])
                except discord.HTTPException:
                    user = None
            if user:
                await dm(user, "Sorry, your custom role color was denied. Please try again later.")
            await self._finish(interaction, "❌ Denied", RED)
        finally:
            _handling.discard(interaction.channel_id)


_handling: set[int] = set()   # request channels being approved or denied right now


REQUEST_COOLDOWN = dt.timedelta(days=7)


def cooldown_ends(user_id: int) -> dt.datetime | None:
    """When this booster can send their next request, or None if they can send one now."""
    raw = store.get_setting(f"customrole_last:{user_id}")
    if not raw:
        return None
    ends = dt.datetime.fromisoformat(raw) + REQUEST_COOLDOWN
    return ends if ends > dt.datetime.now(dt.timezone.utc) else None


async def submit_request(interaction: discord.Interaction, member: discord.Member, primary: int,
                         secondary: int | None) -> discord.TextChannel | None:
    """Open the private request channel for the approvers. Returns None if it couldn't."""
    guild = interaction.guild
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                  guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True,
                                                        attach_files=True, manage_channels=True)}
    for role in approver_roles(guild):
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                       read_message_history=True)
    category = await request_category(guild)
    try:
        channel = await guild.create_text_channel(f"role-{member.name}"[:90], overwrites=overwrites,
                                                  category=category, reason="[gg] custom role request")
    except discord.HTTPException:
        log.exception("Couldn't create the request channel")
        return None
    store.add_role_request(channel.id, member.id, primary, secondary)
    store.set_setting(f"customrole_last:{member.id}", dt.datetime.now(dt.timezone.utc).isoformat())
    embed, file = request_embed(member, primary, secondary, store.custom_role(member.id))
    await channel.send(embed=embed, view=CustomRoleReview(), **({"file": file} if file else {}))
    return channel


class ConfirmColor(discord.ui.View):
    """The booster's own preview: send the request, or go back and pick another color."""

    def __init__(self, member: discord.Member, primary: int, secondary: int | None):
        super().__init__(timeout=300)
        self.member, self.primary, self.secondary = member, primary, secondary

    async def _close(self, interaction: discord.Interaction, embed: discord.Embed):
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None, attachments=[])

    @discord.ui.button(label="Yes, send my request", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _):
        if store.role_request_for(self.member.id) or (cooldown_ends(self.member.id)
                                                       and not is_admin(self.member)):
            await self._close(interaction, simple("You've already sent a request.", AMBER))
            return
        await interaction.response.edit_message(embed=simple("Sending your request…", BLURPLE), view=None,
                                                attachments=[])
        self.stop()
        channel = await submit_request(interaction, self.member, self.primary, self.secondary)
        if channel is None:
            await interaction.edit_original_response(embed=simple(
                "Sorry, something went wrong sending your request. Please let a staff member know.", RED))
            return
        done = simple("Your request has been sent to staff. You'll get a DM once it's been looked at.",
                      self.primary, "🎨 Request Sent")
        done.add_field(name="Color", value=color_text(self.primary, self.secondary), inline=True)
        done.set_footer(text="You can send another request in 7 days.")
        await interaction.edit_original_response(embed=done)

    @discord.ui.button(label="Pick a different color", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _):
        await self._close(interaction, simple(
            "No problem! Run `/customrole` again with a new color whenever you're ready.", BLURPLE))


@bot.tree.command(name="customrole", description="Boosters: request your own custom role color")
@app_commands.guild_only()
@app_commands.describe(color="Your role color as a hex code (e.g. #75117e)",
                       color2="Add a second color to make it a gradient (e.g. #ff7ad9)")
async def customrole(interaction: discord.Interaction, color: app_commands.Range[str, 3, 7],
                     color2: Optional[app_commands.Range[str, 3, 7]] = None):
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.premium_since:
        await interaction.response.send_message(embed=simple(
            "Custom roles are a perk for **server boosters**. Boost the server to unlock it!", PURPLE),
            ephemeral=True)
        return
    primary, secondary = colorpreview.parse_hex(color), colorpreview.parse_hex(color2) if color2 else None
    if primary is None or (color2 and secondary is None):
        await interaction.response.send_message(embed=simple(
            "That doesn't look like a color code. Use a hex code like `#75117e`. "
            "You can pick one at **htmlcolorcodes.com**.", AMBER), ephemeral=True)
        return
    if store.role_request_for(member.id):
        await interaction.response.send_message(embed=simple(
            "You already have a request waiting for staff. Hang tight!", AMBER), ephemeral=True)
        return
    ends = cooldown_ends(member.id)
    if ends and not is_admin(member):
        await interaction.response.send_message(embed=simple(
            f"You can send one request a week. Your next one unlocks <t:{int(ends.timestamp())}:R>.",
            AMBER, "⏳ Slow Down"), ephemeral=True)
        return
    e = discord.Embed(title="🎨 Is this the color you want?", color=primary,
                      description="Here's how your role will look. Once you send it, you can't send another "
                                  "request for **7 days**.")
    e.add_field(name="Style", value="Gradient" if secondary is not None else "Solid", inline=True)
    e.add_field(name="Color", value=color_text(primary, secondary), inline=True)
    png = colorpreview.render(member.name, primary, secondary)
    kwargs = {}
    if png:
        kwargs["file"] = discord.File(png, filename="preview.png")
        e.set_image(url="attachment://preview.png")
    await interaction.response.send_message(embed=e, view=ConfirmColor(member, primary, secondary),
                                            ephemeral=True, **kwargs)


@bot.tree.command(name="boostersetup", description="Choose the category where custom role requests open")
@admin_only
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
@app_commands.describe(category="The category for request channels (staff-only, ideally)")
async def boostersetup(interaction: discord.Interaction, category: discord.CategoryChannel):
    store.set_setting("customrole_category", str(category.id))
    await interaction.response.send_message(embed=simple(
        f"Custom role requests will now open in **{esc(category.name)}**.", GREEN, "💎 Booster Setup"),
        ephemeral=True)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Unboosting removes the custom role; boosting again brings it back."""
    if before.guild.id != GUILD_ID or bool(before.premium_since) == bool(after.premium_since):
        return
    await check_booster(after)


async def check_booster(member: discord.Member):
    saved = store.custom_role(member.id)
    if not saved:
        return
    if not member.premium_since and saved["status"] == "active":
        await delete_custom_role(member.guild, member.id, "[gg] stopped boosting")
        await dm(member, "Your custom role in **[gg] Clan** was removed because you're no longer boosting. "
                         "If you boost again, it'll come back automatically.")
    elif member.premium_since and saved["status"] == "removed":
        try:
            await apply_custom_role(member.guild, member, saved["primary_color"], saved["secondary_color"])
            await dm(member, "Thanks for boosting again! Your custom role is back.")
        except discord.HTTPException:
            log.exception("Couldn't restore custom role")


@tasks.loop(hours=1)
async def booster_sweep():
    """Safety net: catches boosts that ended while the bot was offline, and people who left the server."""
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    for row in store.custom_roles():
        try:
            member = await guild.fetch_member(row["user_id"])
        except discord.NotFound:
            await delete_custom_role(guild, row["user_id"], "[gg] booster left the server")
            continue
        except discord.HTTPException:
            continue
        await check_booster(member)
        saved = store.custom_role(member.id)
        if saved and saved["status"] == "active" and saved["role_id"] and member.premium_since:
            await place_custom_role(guild, member, saved["role_id"], alert=False)   # keep it on top, quietly


booster_sweep.before_loop(wait_ready)


PERSISTENT_VIEWS.append(CustomRoleReview)
BACKGROUND_TASKS.append((booster_sweep, lambda: True))
