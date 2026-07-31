"""Stateful match-run controllers (draft, veto). Held in memory keyed by
match_id; key outcomes persisted to SQLite so a restart can recover results."""
from __future__ import annotations

import random

import discord
from sqlalchemy import select

from bot.core.embeds import VAL_RED
from bot.db import SessionLocal
from bot.db.models import DraftPick, MapVeto, MatchPlayer, MatchTeam
from bot.services import draft as draft_svc
from bot.services import veto as veto_svc


def other_side(side: str) -> str:
    return "B" if side == "A" else "A"


class CoinflipController:
    """Heads/tails toss that decides who drafts first.

    A random captain calls the coin; whoever wins the toss then chooses first or
    second pick — so the toss decides a right, not the order itself.
    """

    FACES = ("heads", "tails")

    def __init__(self, match_id: int, cap_a: int, cap_b: int):
        self.match_id = match_id
        self.cap_a, self.cap_b = cap_a, cap_b
        self.caller_side = random.choice(("A", "B"))
        self.call: str | None = None          # heads|tails
        self.face: str | None = None          # what the coin landed on
        self.winner_side: str | None = None
        self.first_side: str | None = None    # who picks first in the draft
        self.auto = False                     # any step decided by the timer

    # ------------------------------------------------------------- helpers ---
    def captain(self, side: str) -> int:
        return self.cap_a if side == "A" else self.cap_b

    @property
    def caller_id(self) -> int:
        return self.captain(self.caller_side)

    @property
    def stage(self) -> str:
        if self.call is None:
            return "call"
        if self.first_side is None:
            return "order"
        return "done"

    @property
    def done(self) -> bool:
        return self.stage == "done"

    def actor_id(self) -> int | None:
        """Whoever the flow is waiting on right now."""
        if self.stage == "call":
            return self.caller_id
        if self.stage == "order":
            return self.captain(self.winner_side)
        return None

    # -------------------------------------------------------------- actions ---
    def flip(self, call: str, auto: bool = False) -> str:
        """Record the call, flip, and set the toss winner. Returns the face."""
        self.call = call
        self.face = random.choice(self.FACES)
        self.winner_side = (
            self.caller_side if self.call == self.face else other_side(self.caller_side)
        )
        self.auto = self.auto or auto
        return self.face

    def choose_order(self, choice: str, auto: bool = False) -> str:
        """`first` or `second` — sets which side opens the draft."""
        self.first_side = (
            self.winner_side if choice == "first" else other_side(self.winner_side)
        )
        self.auto = self.auto or auto
        return self.first_side

    def random_call(self) -> str:
        return random.choice(self.FACES)

    def random_order(self) -> str:
        return random.choice(("first", "second"))

    # ---------------------------------------------------------------- embed ---
    def embed(self) -> discord.Embed:
        e = discord.Embed(title=f"🪙 Coin Toss — Match #{self.match_id}", color=VAL_RED)
        e.add_field(
            name="Calling",
            value=f"<@{self.caller_id}> ({self.caller_side})",
            inline=True,
        )
        if self.call:
            e.add_field(name="Call", value=self.call.title(), inline=True)
            e.add_field(name="Landed", value=f"**{self.face.title()}**", inline=True)
            e.add_field(
                name="Toss winner",
                value=f"<@{self.captain(self.winner_side)}> ({self.winner_side})",
                inline=False,
            )
        if self.stage == "call":
            e.add_field(name="Waiting on", value="heads or tails", inline=False)
        elif self.stage == "order":
            e.add_field(
                name="Waiting on",
                value=f"<@{self.captain(self.winner_side)}> — **first** or **second** pick",
                inline=False,
            )
        else:
            e.add_field(
                name="Draft order",
                value=f"<@{self.captain(self.first_side)}> ({self.first_side}) picks first"
                      + (" _(auto)_" if self.auto else ""),
                inline=False,
            )
        return e


class DraftController:
    def __init__(
        self,
        match_id: int,
        cap_a: int,
        cap_b: int,
        pool: list[int],
        mode: str = "snake",
        first: str = "A",
    ):
        self.match_id = match_id
        self.cap_a, self.cap_b = cap_a, cap_b
        self.pool = list(pool)                      # selectable players
        self.team = {"A": [cap_a], "B": [cap_b]}
        self.mode = mode if mode in draft_svc.DRAFT_MODES else "snake"
        self.first = first
        self.order = draft_svc.pick_order(self.mode, len(self.pool), first)
        self.idx = 0

    @property
    def done(self) -> bool:
        return self.idx >= len(self.order)

    def current_side(self) -> str | None:
        return None if self.done else self.order[self.idx]

    def captain_for_turn(self) -> int | None:
        side = self.current_side()
        return None if side is None else (self.cap_a if side == "A" else self.cap_b)

    async def pick(self, user_id: int, auto: bool = False) -> bool:
        side = self.current_side()
        if side is None or user_id not in self.pool:
            return self.done
        self.pool.remove(user_id)
        self.team[side].append(user_id)
        async with SessionLocal() as s:
            s.add(DraftPick(match_id=self.match_id, pick_no=self.idx,
                            team_side=side, user_id=user_id, auto=auto))
            await s.commit()
        self.idx += 1
        return self.done

    def autopick(self) -> int:
        """Random remaining player — used when a captain's timer runs out."""
        return random.choice(self.pool)

    async def persist_teams(self) -> None:
        """Write the two MatchTeam rows (with captains) and stamp each player's
        side/team. Idempotent — the draft can finish via a click or the timer."""
        async with SessionLocal() as s:
            rows = await s.execute(
                select(MatchTeam).where(MatchTeam.match_id == self.match_id)
            )
            teams = {t.side: t for (t,) in rows.all()}
            for side, cap in (("A", self.cap_a), ("B", self.cap_b)):
                if side not in teams:
                    t = MatchTeam(match_id=self.match_id, side=side,
                                  name=f"Team {side}", captain_id=cap)
                    s.add(t)
                    await s.flush()  # assign team_id
                    teams[side] = t
            for side, ids in self.team.items():
                for uid in ids:
                    mp = await s.get(MatchPlayer, (self.match_id, uid))
                    if mp:
                        mp.side = side
                        mp.team_id = teams[side].team_id
            await s.commit()

    def embed(self) -> discord.Embed:
        title = "🐍 Snake Draft" if self.mode == "snake" else "🔁 Draft (one by one)"
        e = discord.Embed(title=f"{title} — Match #{self.match_id}", color=VAL_RED)
        e.add_field(name="🟥 Team A", value="\n".join(f"<@{u}>" for u in self.team["A"]), inline=True)
        e.add_field(name="🟦 Team B", value="\n".join(f"<@{u}>" for u in self.team["B"]), inline=True)
        if not self.done:
            cap = self.captain_for_turn()
            e.add_field(name="On the clock",
                        value=f"<@{cap}> ({self.current_side()}) — {len(self.pool)} left",
                        inline=False)
        else:
            e.add_field(name="Complete", value="All players drafted.", inline=False)
        return e


class VetoController:
    def __init__(self, match_id: int, fmt: str, pool: list[str], cap_a: int, cap_b: int):
        self.match_id = match_id
        self.cap_a, self.cap_b = cap_a, cap_b
        self.remaining = list(pool)
        self.plan = veto_svc.veto_plan(fmt, len(pool))
        self.step = 0
        self.picked_maps: list[str] = []
        self.history: list[tuple[str, str | None, str]] = []  # (action, side, map)

    @property
    def _current(self):
        return self.plan[self.step] if self.step < len(self.plan) else None

    @property
    def done(self) -> bool:
        return self.step >= len(self.plan)

    def captain_for_turn(self) -> int | None:
        cur = self._current
        if cur is None or cur.side is None:
            return None
        return self.cap_a if cur.side == "A" else self.cap_b

    def auto_pick_map(self) -> bool:
        """Random remaining map for the current step — used on captain timeout."""
        if not self.remaining:
            return True
        return self.apply(random.choice(self.remaining))

    def apply(self, map_name: str) -> bool:
        cur = self._current
        if cur is None or map_name not in self.remaining:
            return self.step >= len(self.plan)
        if cur.action in ("pick",):
            self.picked_maps.append(map_name)
        self.remaining.remove(map_name)
        # record step (decider handled at completion)
        self._record(cur.action, cur.side, map_name)
        self.step += 1
        # auto-resolve any trailing decider
        if self._current and self._current.action == "decider" and len(self.remaining) == 1:
            decider = self.remaining[0]
            self.picked_maps.append(decider)
            self._record("decider", None, decider)
            self.remaining.clear()
            self.step += 1
        return self.step >= len(self.plan)

    def _record(self, action: str, side: str | None, map_name: str) -> None:
        self._pending = getattr(self, "_pending", [])
        self._pending.append((self.step, action, side, map_name))
        self.history.append((action, side, map_name))

    @property
    def decider_map(self) -> str | None:
        """The map the veto ends on — the one sides get chosen for."""
        return self.picked_maps[-1] if self.picked_maps else None

    @property
    def side_choice_side(self) -> str | None:
        """Team that picks attack/defence: the one that did NOT ban last.

        Falls back to the last team to act at all — a short BO3 pool can be all
        picks and no bans, and someone still has to choose a side."""
        for action, side, _ in reversed(self.history):
            if action == "ban" and side:
                return other_side(side)
        for _action, side, _ in reversed(self.history):
            if side:
                return other_side(side)
        return None

    async def persist(self) -> None:
        async with SessionLocal() as s:
            for step, action, side, name in getattr(self, "_pending", []):
                s.add(MapVeto(match_id=self.match_id, step=step,
                              action=action, team_side=side, map_name=name))
            await s.commit()
        self._pending = []

    def result_text(self, auto: bool = False) -> str:
        maps = ", ".join(self.picked_maps) if self.picked_maps else "—"
        note = " (auto)" if auto else ""
        return f"✅ Veto complete{note}. Maps: **{maps}**"

    async def on_complete(self, itx: discord.Interaction) -> None:
        await self.persist()
        await itx.followup.send(self.result_text())

    def embed(self) -> discord.Embed:
        e = discord.Embed(title=f"🗺 Map Veto — Match #{self.match_id}", color=VAL_RED)
        e.add_field(name="Remaining", value=", ".join(self.remaining) or "—", inline=False)
        if self.picked_maps:
            e.add_field(name="Picked", value=", ".join(self.picked_maps), inline=False)
        cur = self._current
        if cur and cur.side:
            e.add_field(name="Turn", value=f"<@{self.captain_for_turn()}> to {cur.action}", inline=False)
        return e
