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


class DraftController:
    def __init__(self, match_id: int, cap_a: int, cap_b: int, pool: list[int]):
        self.match_id = match_id
        self.cap_a, self.cap_b = cap_a, cap_b
        self.pool = list(pool)                      # selectable players
        self.team = {"A": [cap_a], "B": [cap_b]}
        self.order = draft_svc.snake_order(len(self.pool))
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
        e = discord.Embed(title=f"🐍 Snake Draft — Match #{self.match_id}", color=VAL_RED)
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
