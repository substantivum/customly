"""Stateful match-run controllers (draft, veto). Held in memory keyed by
match_id; key outcomes persisted to SQLite so a restart can recover results."""
from __future__ import annotations

import random
from datetime import datetime

import discord
from sqlalchemy import select

from bot.core.embeds import DASH, EMBED_COLOR, member_name
from bot.db import SessionLocal
from bot.db.models import DraftPick, MapVeto, MatchMapSide, MatchPlayer, MatchTeam
from bot.i18n import t
from bot.services import draft as draft_svc
from bot.services import veto as veto_svc

SIDES = ("attack", "defence")


def other_side(side: str) -> str:
    return "B" if side == "A" else "A"


def other_choice(choice: str) -> str:
    return "defence" if choice == "attack" else "attack"


class CoinflipController:
    """Heads/tails toss that decides which team is Team A.

    A random captain calls the coin; the winner then takes Team A or Team B.
    Team A drafts first and opens the map veto, so taking B is a real trade —
    it's the same right the official rules give the better-seeded team.
    """

    FACES = ("heads", "tails")

    def __init__(self, match_id: int, cap_a: int, cap_b: int,
                 guild: discord.Guild | None = None):
        self.match_id = match_id
        self.cap_a, self.cap_b = cap_a, cap_b
        self.guild = guild
        self.caller_side = random.choice(("A", "B"))
        self.call: str | None = None          # heads|tails
        self.face: str | None = None          # what the coin landed on
        self.winner_side: str | None = None
        self.letter: str | None = None        # the letter the winner took
        self.auto = False                     # any step decided by the timer

    @property
    def first_side(self) -> str | None:
        """Team A opens the draft — but only once the letters are settled."""
        return "A" if self.letter else None

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
        if self.letter is None:
            return "letter"
        return "done"

    @property
    def done(self) -> bool:
        return self.stage == "done"

    def actor_id(self) -> int | None:
        """Whoever the flow is waiting on right now."""
        if self.stage == "call":
            return self.caller_id
        if self.stage == "letter":
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

    def choose_letter(self, choice: str, auto: bool = False) -> str:
        """`A` or `B` — the letter the toss winner takes.

        The captains swap places when the winner takes the other letter, so
        everything downstream (draft order, veto turns, team channels) can go on
        reading Team A as Team A.
        """
        if choice not in ("A", "B"):
            raise ValueError(choice)
        if choice != self.winner_side:
            self.cap_a, self.cap_b = self.cap_b, self.cap_a
            self.caller_side = other_side(self.caller_side)
            self.winner_side = choice
        self.letter = choice
        self.auto = self.auto or auto
        return choice

    def random_call(self) -> str:
        return random.choice(self.FACES)

    def random_letter(self) -> str:
        return random.choice(("A", "B"))

    # ---------------------------------------------------------------- embed ---
    def embed(self) -> discord.Embed:
        e = discord.Embed(
            title=t("coin.title", match_id=self.match_id), color=EMBED_COLOR
        )
        e.add_field(
            name=t("coin.calling"),
            value=f"{member_name(self.guild, self.caller_id)} ({self.caller_side})",
            inline=True,
        )
        if self.call:
            e.add_field(name=t("coin.call"), value=t(f"coin.{self.call}"), inline=True)
            e.add_field(name=t("coin.landed"), value=f"**{t(f'coin.{self.face}')}**",
                        inline=True)
            e.add_field(
                name=t("coin.winner"),
                value=f"{member_name(self.guild, self.captain(self.winner_side))} "
                      f"({self.winner_side})",
                inline=False,
            )
        if self.stage == "call":
            e.add_field(name=t("common.waiting_on"), value=t("coin.wait_call"),
                        inline=False)
        elif self.stage == "letter":
            e.add_field(
                name=t("common.waiting_on"),
                value=t("coin.wait_letter",
                        captain=member_name(self.guild, self.captain(self.winner_side))),
                inline=False,
            )
        else:
            e.add_field(
                name=t("common.teams"),
                value=t("coin.teams_value", cap_a=member_name(self.guild, self.cap_a),
                        cap_b=member_name(self.guild, self.cap_b))
                      + (t("common.auto_note") if self.auto else ""),
                inline=False,
            )
        return e


class ReadyCheckController:
    """Attendance check before a custom starts.

    Every starter has to say ✅ before the match flow begins — a Valorant custom
    needs both teams full, and a player drafted onto a team who never turns up
    ruins the game for nine other people.

    `❌ Can't play` is an *answer*, not a refusal to answer: once every seat has
    given one the check resolves immediately rather than sitting out the clock.
    """

    def __init__(self, custom_id: int, name: str, starters: list[int],
                 deadline: datetime, round_no: int = 1,
                 guild: discord.Guild | None = None):
        self.custom_id = custom_id
        self.name = name
        self.starters = list(starters)
        self.deadline = deadline
        self.round_no = round_no
        self.guild = guild
        self.ready: set[int] = set()
        self.declined: set[int] = set()

    # ------------------------------------------------------------- state ----
    def mark(self, user_id: int, ok: bool) -> None:
        (self.declined if ok else self.ready).discard(user_id)
        (self.ready if ok else self.declined).add(user_id)

    def is_starter(self, user_id: int) -> bool:
        return user_id in self.starters

    @property
    def missing(self) -> list[int]:
        """Signed up, but hasn't answered either way."""
        answered = self.ready | self.declined
        return [u for u in self.starters if u not in answered]

    @property
    def everyone_ready(self) -> bool:
        return len(self.ready) == len(self.starters)

    @property
    def all_answered(self) -> bool:
        return not self.missing

    @property
    def absent(self) -> list[int]:
        """Who loses their seat if the check resolves now."""
        return [u for u in self.starters if u not in self.ready]

    def mentions(self) -> str:
        return " ".join(f"<@{u}>" for u in self.starters)

    # ------------------------------------------------------------ display ---
    def _roster_lines(self) -> str:
        def mark(u: int) -> str:
            if u in self.ready:
                return "✅"
            return "❌" if u in self.declined else "⬜"

        return "\n".join(
            f"{mark(u)} {member_name(self.guild, u)}" for u in self.starters
        ) or DASH

    def embed(self, *, outcome: str | None = None) -> discord.Embed:
        e = discord.Embed(
            title=t("ready.title", custom_id=self.custom_id, name=self.name),
            description=(
                outcome
                or t("ready.desc", when=discord.utils.format_dt(self.deadline, "R"))
            ),
            color=EMBED_COLOR,
        )
        if self.round_no > 1:
            e.title += t("ready.round", n=self.round_no)
        e.add_field(
            name=t("ready.count", n=len(self.ready), total=len(self.starters)),
            value=self._roster_lines(),
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
        guild: discord.Guild | None = None,
    ):
        self.match_id = match_id
        self.cap_a, self.cap_b = cap_a, cap_b
        self.guild = guild
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
        mode = t("draft.title.snake" if self.mode == "snake" else "draft.title.alternate")
        e = discord.Embed(
            title=t("draft.title", mode=mode, match_id=self.match_id), color=EMBED_COLOR
        )
        e.add_field(
            name=t("common.team_a"),
            value="\n".join(member_name(self.guild, u) for u in self.team["A"]),
            inline=True,
        )
        e.add_field(
            name=t("common.team_b"),
            value="\n".join(member_name(self.guild, u) for u in self.team["B"]),
            inline=True,
        )
        if not self.done:
            e.add_field(
                name=t("draft.on_clock"),
                value=t("draft.on_clock_value",
                        captain=member_name(self.guild, self.captain_for_turn()),
                        side=self.current_side(), n=len(self.pool)),
                inline=False,
            )
        else:
            e.add_field(name=t("draft.complete"), value=t("draft.complete_value"),
                        inline=False)
        return e


class VetoController:
    def __init__(self, match_id: int, fmt: str, pool: list[str], cap_a: int, cap_b: int,
                 guild: discord.Guild | None = None):
        self.match_id = match_id
        self.cap_a, self.cap_b = cap_a, cap_b
        self.guild = guild
        self.remaining = list(pool)
        self.plan = veto_svc.veto_plan(fmt, len(pool))
        self.step = 0
        self.picked_maps: list[str] = []
        # (action, side, map, choice) — choice is set on side steps only
        self.history: list[tuple[str, str | None, str, str | None]] = []
        self.sides: list[tuple[str, str, str]] = []   # (map, chooser, choice)

    @property
    def current(self):
        return self.plan[self.step] if self.step < len(self.plan) else None

    @property
    def done(self) -> bool:
        return self.step >= len(self.plan)

    def captain_for_turn(self) -> int | None:
        cur = self.current
        if cur is None or cur.side is None:
            return None
        return self.cap_a if cur.side == "A" else self.cap_b

    def auto_pick_map(self) -> bool:
        """Random remaining map for the current step — used on captain timeout."""
        if not self.remaining:
            return True
        return self.apply(random.choice(self.remaining))

    def auto_pick_side(self) -> bool:
        """Random attack/defence — used when a captain stalls on a side step."""
        return self.apply_side(random.choice(SIDES))

    def apply(self, map_name: str) -> bool:
        cur = self.current
        if cur is None or cur.action == "side" or map_name not in self.remaining:
            return self.done
        if cur.action in ("pick",):
            self.picked_maps.append(map_name)
        self.remaining.remove(map_name)
        # record step (decider handled at completion)
        self._record(cur.action, cur.side, map_name)
        self.step += 1
        self._resolve_decider()
        return self.done

    def apply_side(self, choice: str) -> bool:
        """Attack or defence on the map this step follows."""
        cur = self.current
        map_name = self.current_side_map
        if cur is None or choice not in SIDES or map_name is None:
            return self.done
        self.sides.append((map_name, cur.side, choice))
        self._record("side", cur.side, map_name, choice)
        self.step += 1
        # a side step can be the last thing standing between us and the decider
        self._resolve_decider()
        return self.done

    def _resolve_decider(self) -> None:
        """The last map standing needs nobody's click — take it automatically."""
        cur = self.current
        if cur and cur.action == "decider" and len(self.remaining) == 1:
            decider = self.remaining[0]
            self.picked_maps.append(decider)
            self._record("decider", None, decider)
            self.remaining.clear()
            self.step += 1

    def _record(self, action: str, side: str | None, map_name: str,
                choice: str | None = None) -> None:
        self._pending = getattr(self, "_pending", [])
        self._pending.append((self.step, action, side, map_name, choice))
        self.history.append((action, side, map_name, choice))

    @property
    def decider_map(self) -> str | None:
        """The map the veto ends on."""
        return self.picked_maps[-1] if self.picked_maps else None

    @property
    def current_side_map(self) -> str | None:
        """The map the pending side step is about — the one just decided."""
        cur = self.current
        if cur is None or cur.action != "side" or not self.picked_maps:
            return None
        return self.picked_maps[-1]

    def side_text(self, map_name: str, chooser: str, choice: str) -> str:
        return t(
            "veto.side_text",
            map=map_name,
            chooser=chooser,
            choice=t(f"veto.{choice}"),
            other=other_side(chooser),
            flip=t(f"veto.{other_choice(choice)}"),
        )

    async def persist(self) -> None:
        async with SessionLocal() as s:
            for step, action, side, name, choice in getattr(self, "_pending", []):
                if action == "side":
                    continue
                s.add(MapVeto(match_id=self.match_id, step=step,
                              action=action, team_side=side, map_name=name))
            for i, (name, chooser, choice) in enumerate(self.sides, start=1):
                s.add(MatchMapSide(match_id=self.match_id, map_index=i,
                                   map_name=name, team_side=chooser, choice=choice))
            await s.commit()
        self._pending = []

    def result_text(self, auto: bool = False) -> str:
        note = t("common.auto_paren") if auto else ""
        if self.sides:
            lines = "\n".join(
                f"{i}. {self.side_text(*s)}" for i, s in enumerate(self.sides, start=1)
            )
            return t("veto.result_maps", note=note, lines=lines)
        maps = ", ".join(self.picked_maps) if self.picked_maps else DASH
        return t("veto.result_simple", note=note, maps=maps)

    async def on_complete(self, itx: discord.Interaction) -> None:
        await self.persist()
        await itx.followup.send(self.result_text())

    def embed(self) -> discord.Embed:
        e = discord.Embed(
            title=t("veto.title", match_id=self.match_id), color=EMBED_COLOR
        )
        e.add_field(name=t("veto.remaining"), value=", ".join(self.remaining) or DASH,
                    inline=False)
        if self.picked_maps:
            e.add_field(name=t("veto.picked"), value=", ".join(self.picked_maps),
                        inline=False)
        if self.sides:
            e.add_field(
                name=t("veto.sides"),
                value="\n".join(self.side_text(*s) for s in self.sides),
                inline=False,
            )
        cur = self.current
        if cur and cur.side:
            captain = member_name(self.guild, self.captain_for_turn())
            turn = (
                t("veto.turn_side", captain=captain, map=self.current_side_map)
                if cur.action == "side"
                else t("veto.turn_action", captain=captain,
                       action=t(f"veto.action.{cur.action}"))
            )
            e.add_field(name=t("veto.turn"), value=turn, inline=False)
        return e
