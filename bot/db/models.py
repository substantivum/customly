"""ORM models mirroring the schema in valorant-bot-architecture.md.

Core flow tables (guilds, users, member_roles, maps, customs,
custom_registrations, queues, queue_members, matches, match_teams,
match_players, map_veto, match_results, drafts, draft_picks, player_stats,
audit_log) are fully used by the bot. Tournament/engagement tables are
declared for schema parity; their cogs are stubbed (see README).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- identity ---
class Guild(Base):
    """A row here is created lazily, the first time a guild's language or
    notify-role is set (see bot.services.guild_svc) — not the moment the bot
    joins. Every other table's `guild_id` is therefore a bare Discord snowflake,
    not a ForeignKey to this table: a guild can have customs, maps, matches
    and more long before (or without ever) getting a `guilds` row.
    """

    __tablename__ = "guilds"
    guild_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class User(Base):
    """A row here only exists for a player who has completed Riot registration
    (see bot.services.identity) — anyone can join a queue or play a match
    without one. Every other table's `user_id` is therefore a bare Discord
    snowflake, not a ForeignKey to this table.
    """

    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # discord id
    riot_id: Mapped[str | None] = mapped_column(String(32))          # canonical Name#Tag, from API
    riot_puuid: Mapped[str | None] = mapped_column(String(64))
    riot_region: Mapped[str | None] = mapped_column(String(8))       # from the account API
    # None = never submitted. No RSO/OAuth exists to prove Discord-user →
    # Riot-account ownership (see README), so this is the manual trust step:
    # the account API only confirms the tag *exists*, a human confirms it's
    # genuinely this player's.
    riot_status: Mapped[str | None] = mapped_column(String(16))
    riot_reviewed_by: Mapped[int | None] = mapped_column(Integer)
    riot_reviewed_at: Mapped[datetime | None] = mapped_column()
    rank_updated_at: Mapped[datetime | None] = mapped_column()       # cache staleness clock
    main_role: Mapped[str | None] = mapped_column(String(16))
    roles_json: Mapped[str] = mapped_column(Text, default="[]")
    cur_rank: Mapped[str | None] = mapped_column(String(16))         # API-sourced, approved only
    peak_rank: Mapped[str | None] = mapped_column(String(16))
    cur_rr: Mapped[int | None] = mapped_column(Integer)
    wins: Mapped[int] = mapped_column(Integer, default=0)    # customs won, +1 per finished match
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    __table_args__ = (
        CheckConstraint(
            "main_role IS NULL OR main_role IN "
            "('Duelist','Controller','Initiator','Sentinel','Flex')",
            name="ck_user_role",
        ),
        CheckConstraint(
            "riot_status IS NULL OR riot_status IN ('pending','approved','denied')",
            name="ck_user_riot_status",
        ),
    )


class MemberRole(Base):
    __tablename__ = "member_roles"
    guild_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    __table_args__ = (
        CheckConstraint(
            "role IN ('superadmin','admin','player')", name="ck_member_role"
        ),
    )


class Map(Base):
    __tablename__ = "maps"
    guild_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # part of the guild's "current competitive pool" — a named subset admins keep
    # in sync with Riot's active rotation, offered as one click at custom creation
    competitive: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which game this map belongs to — not part of the primary key (map names
    # don't collide across games in practice), so a guild's Valorant and CS2
    # pools just live side by side in the same table.
    game: Mapped[str] = mapped_column(String(16), default="valorant")
    __table_args__ = (
        CheckConstraint("game IN ('valorant','dota2','cs2')", name="ck_map_game"),
    )


# ----------------------------------------------------------------- customs ---
class Custom(Base):
    __tablename__ = "customs"
    custom_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    game: Mapped[str] = mapped_column(String(16), default="valorant")
    format: Mapped[str] = mapped_column(String(4))           # BO1|BO3|BO5
    duration_h: Mapped[int] = mapped_column(Integer)         # 1/3/5
    team_size: Mapped[int] = mapped_column(Integer, default=5)  # players per side (2-5)
    map_pool: Mapped[str] = mapped_column(Text)              # JSON list
    draft_mode: Mapped[str] = mapped_column(String(16), default="snake")  # snake|alternate
    # How captains are picked when this custom starts. Chosen once, at creation —
    # the start button shouldn't be where you decide how the game is run.
    captain_method: Mapped[str] = mapped_column(String(16), default="random")
    start_time: Mapped[datetime] = mapped_column()           # ISO, overlap checks
    # Created without a time: `start_time` is the creation instant so the overlap
    # rule still works, but everything user-facing says "ASAP" instead of a clock.
    start_asap: Mapped[bool] = mapped_column(Boolean, default=False)
    vc_category: Mapped[int | None] = mapped_column(Integer)
    reg_channel: Mapped[int | None] = mapped_column(Integer)  # #custom-<id>
    reg_message: Mapped[int | None] = mapped_column(Integer)  # registration embed
    # team voice channels: their names carry the captain's nickname, so the ids
    # are what the lifecycle (occupancy guard, teardown, lobby links) looks up
    vc_a: Mapped[int | None] = mapped_column(Integer)
    vc_b: Mapped[int | None] = mapped_column(Integer)
    config_chan: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="registration")
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.match_id"))
    owner_id: Mapped[int] = mapped_column(Integer)           # transferable manager
    created_by: Mapped[int] = mapped_column(Integer)         # immutable creator
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    __table_args__ = (
        CheckConstraint("format IN ('BO1','BO3','BO5')", name="ck_custom_fmt"),
        CheckConstraint("game IN ('valorant','dota2','cs2')", name="ck_custom_game"),
    )


class CustomRegistration(Base):
    __tablename__ = "custom_registrations"
    custom_id: Mapped[int] = mapped_column(
        ForeignKey("customs.custom_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reg_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ------------------------------------------------------------------ queues ---
class Queue(Base):
    __tablename__ = "queues"
    queue_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer)
    custom_id: Mapped[int | None] = mapped_column(
        ForeignKey("customs.custom_id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(16))           # 5v5|10man|scrim|tournament
    size: Mapped[int] = mapped_column(Integer)
    format: Mapped[str | None] = mapped_column(String(4))
    open: Mapped[bool] = mapped_column(Boolean, default=True)


class QueueMember(Base):
    __tablename__ = "queue_members"
    queue_id: Mapped[int] = mapped_column(
        ForeignKey("queues.queue_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ----------------------------------------------------------------- matches ---
class Match(Base):
    __tablename__ = "matches"
    match_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer)
    tournament_id: Mapped[int | None] = mapped_column(Integer)
    # Deliberately not a ForeignKey: deleting/pruning a custom (custom.py
    # delete_custom) never touches its matches — match history is meant to
    # outlive the custom, so this can and does legitimately point at a
    # custom_id that no longer exists in `customs`.
    custom_id: Mapped[int | None] = mapped_column(Integer)
    # Copied from Custom.game at creation — kept here too (not just on the
    # custom) since match history is meant to outlive its custom.
    game: Mapped[str] = mapped_column(String(16), default="valorant")
    format: Mapped[str] = mapped_column(String(4))
    state: Mapped[str] = mapped_column(String(16), default="created")
    party_code: Mapped[str | None] = mapped_column(String(16))
    start_time: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    # coin toss → who picked first in the draft
    first_pick_side: Mapped[str | None] = mapped_column(String(1))    # A|B
    # attack/defence on the decider, chosen by the team that didn't ban it away
    side_map: Mapped[str | None] = mapped_column(String(32))
    side_pick: Mapped[str | None] = mapped_column(String(8))          # attack|defence
    side_pick_side: Mapped[str | None] = mapped_column(String(1))     # A|B


class MatchTeam(Base):
    __tablename__ = "match_teams"
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.match_id", ondelete="CASCADE"))
    side: Mapped[str] = mapped_column(String(1))            # A|B
    name: Mapped[str | None] = mapped_column(String(64))
    logo_url: Mapped[str | None] = mapped_column(Text)
    captain_id: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer, default=0)


class MatchPlayer(Base):
    __tablename__ = "match_players"
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    # Not a ForeignKey to `users`: `users` only holds players who completed
    # Riot registration, but any Discord member can join a queue and play.
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("match_teams.team_id"))
    side: Mapped[str | None] = mapped_column(String(1))
    checked_in: Mapped[bool] = mapped_column(Boolean, default=False)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sub: Mapped[bool] = mapped_column(Boolean, default=False)


class MapVeto(Base):
    __tablename__ = "map_veto"
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    step: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(8))         # ban|pick|decider
    team_side: Mapped[str | None] = mapped_column(String(1))
    map_name: Mapped[str] = mapped_column(String(32))


class MatchMapSide(Base):
    """Attack/defence per played map, in the order the maps are played.

    Its own table rather than columns on `map_veto`: a side is chosen for a
    *map*, not for a veto step, and the number of them varies with the format.
    `Match.side_pick` still holds the decider's, for matches recorded before
    sides were tracked per map.
    """

    __tablename__ = "match_map_sides"
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    map_index: Mapped[int] = mapped_column(Integer, primary_key=True)   # 1-based
    map_name: Mapped[str] = mapped_column(String(32))
    team_side: Mapped[str] = mapped_column(String(1))      # A|B — who chose
    choice: Mapped[str] = mapped_column(String(8))         # attack|defence


class MatchResult(Base):
    __tablename__ = "match_results"
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    map_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    map_name: Mapped[str] = mapped_column(String(32))
    score_a: Mapped[int] = mapped_column(Integer)
    score_b: Mapped[int] = mapped_column(Integer)
    winner_side: Mapped[str] = mapped_column(String(1))


# ------------------------------------------------------------------ drafts ---
class Draft(Base):
    __tablename__ = "drafts"
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    method: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    turn_side: Mapped[str | None] = mapped_column(String(1))
    deadline: Mapped[datetime | None] = mapped_column()


class DraftPick(Base):
    __tablename__ = "draft_picks"
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    pick_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_side: Mapped[str] = mapped_column(String(1))
    # Not a ForeignKey to `users` — see MatchPlayer.user_id.
    user_id: Mapped[int] = mapped_column(Integer)
    auto: Mapped[bool] = mapped_column(Boolean, default=False)


# -------------------------------------------------------------------- stats ---
class PlayerStats(Base):
    __tablename__ = "player_stats"
    guild_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    mvps: Mapped[int] = mapped_column(Integer, default=0)
    captain_wins: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(128))
    meta_json: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(default=_utcnow)


class PanelBoard(Base):
    """A posted control board, so the bot can find it again to redraw it.

    One board per tier per guild: re-running `/panel` for a tier replaces the
    row (and deletes the message it points at), which is what keeps a stale
    board from lingering after an update.
    """

    __tablename__ = "panel_boards"
    guild_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tier: Mapped[str] = mapped_column(String(16), primary_key=True)  # player|admin|superadmin
    channel_id: Mapped[int] = mapped_column(Integer)
    message_id: Mapped[int] = mapped_column(Integer)
    posted_by: Mapped[int | None] = mapped_column(Integer)
    posted_at: Mapped[datetime] = mapped_column(default=_utcnow)
    __table_args__ = (
        CheckConstraint("tier IN ('player','admin','superadmin')", name="ck_panel_tier"),
    )


class Ban(Base):
    __tablename__ = "bans"
    guild_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text)
    banned_by: Mapped[int | None] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(default=_utcnow)


# NOTE: match_spectators was dropped — team voice channels are open to everyone,
# so there is nothing to grant. Old databases keep the (unused) table.
