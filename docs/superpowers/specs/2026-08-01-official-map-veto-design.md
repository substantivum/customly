# Official map selection + per-map side picks

Bring the veto in line with the published Riot map selection process for BO1 /
BO3 / BO5, and give every map its own attack/defence choice instead of one
choice on the decider.

## What's wrong today

* Only the **decider** gets a side pick (`actions._run_side_pick`). The maps a
  captain picks in a BO3/BO5 are played on whatever sides the lobby hands out.
* The decider's side goes to "the team that did not ban last"
  (`VetoController.side_choice_side`). For BO5 the rules give it to **Team B**;
  that rule returns A.
* Team A/B are assigned when captains are chosen. The rules give the choice of
  letter to the better-seeded team; the coin toss here only decides draft order.

## Decisions

* **BO3/BO5 require exactly 7 maps.** Any 7 maps count — `maps:competitive` is
  the normal way to get them, but a hand-typed 7 is accepted. BO1 keeps working
  on any pool ≥ 2, alternating bans down to one map (at 7 maps this *is* the
  official BO1 sequence).
* **The coin toss winner picks their letter** (Team A or Team B), replacing the
  first/second-pick prompt. Team A drafts first and bans first.

## Sequences

Team A always acts first. `side X` = team X chooses attack or defence for the
map just decided.

| Format | Sequence (7 maps) |
|---|---|
| BO1 | ban A, ban B, ban A, ban B, ban A, ban B, decider, **side A** |
| BO3 | ban A, ban B, pick A, **side B**, pick B, **side A**, ban A, ban B, decider, **side A** |
| BO5 | ban A, ban B, pick A, **side B**, pick B, **side A**, pick A, **side B**, pick B, **side A**, decider, **side B** |

BO3 and BO5 are literal tables — no generation. BO1 is generated: alternating
bans from A until one map remains, then the side goes to whoever did **not** ban
last (Team A on an odd-sized pool, Team B on an even one).

## Components

**`bot/services/veto.py`** — `VetoStep` gains `action="side"`. `MIN_POOL` is
replaced by a pool rule per format (`BO1`: min 2, `BO3`/`BO5`: exactly 7) and a
`check_pool(fmt, size)` that raises with the message a captain should read.
`veto_plan` returns the tables above.

**`bot/core/controllers.py`**

* `CoinflipController.choose_order()` → `choose_letter(choice: "A"|"B")`. The
  controller reports the letter the toss winner takes; `first_side` stays as
  the derived draft opener (always `"A"`).
* `VetoController.apply()` handles map steps only and refuses to run on a side
  step. New `apply_side(choice)` records attack/defence against the map the
  step refers to (the most recently decided map).
* `side_choice_side` is deleted — the plan encodes who picks each side.
* `history` entries carry the choice so the embed can render
  `Ascent — Team B defence`.
* `persist()` writes the side rows as well as the veto rows.

**`bot/core/views.py`** — `VetoView` renders per-step: map buttons on a
ban/pick/decider step, Attack/Defence on a side step, both gated to the captain
on the clock and both auto-resolved at random by the existing
`veto_pick_seconds` timer. `SidePickView` is deleted. `CoinflipView`'s second
stage becomes Team A / Team B.

**`bot/core/actions.py`**

* `begin_match` validates the custom's pool against its format before creating
  anything, so a legacy BO3 custom with 5 maps fails at start with a clear
  message instead of stranding drafted teams at the veto.
* `after_coin` swaps `cap_a`/`cap_b` when the toss winner takes the other
  letter. Nothing is persisted before the draft, so the swap is safe. The
  pre-toss announcement no longer asserts letters.
* `_run_side_pick` is deleted; the veto's completion goes straight to
  `finish_veto`.
* `build_lobby_embed` lists one line per map with both teams' sides.

**`bot/db/models.py`** — new table `match_map_sides`
(`match_id`, `map_index`, `map_name`, `team_side`, `choice`), PK
`(match_id, map_index)`. Its own table rather than columns on `map_veto`: a side
belongs to a *map*, not to a veto step, and how many there are varies with the
format. Live databases pick it up on boot — `create_all` adds missing tables and
`engine._add_missing_columns` patches in missing columns.
`Match.side_map/side_pick/side_pick_side` keep receiving the decider's choice,
and the lobby falls back to them for matches recorded before this change.

**`bot/services/custom.py`** — create-time validation uses `check_pool`, so
`/custom create format:BO3 maps:<5 maps>` is rejected at creation.

## Data flow

```
coin toss → letter → (swap captains) → draft → veto plan
   → per step: map buttons | side buttons  → MapVeto + MatchMapSide rows
   → lobby embed reads both tables back
```

The lobby is rebuilt from the database, not the in-memory controller, so it
survives a restart — that stays true for sides.

## Error handling

* Pool wrong for the format: rejected at `/custom create`, and again at match
  start for customs created earlier. Both name the format, the requirement and
  the actual count.
* A captain who stalls on a side step is auto-resolved at random, flagged
  `(auto)` in the channel exactly as map auto-picks already are.
* Team VC creation failure stays non-fatal, unchanged.

## Testing

`tests/test_logic.py`:

* The three sequences above asserted step by step against the rule text.
* BO3/BO5 reject any pool that isn't 7; BO1 accepts 2..N and always ends on one
  map.
* Every picked map's side is chosen by the team that did not pick it.
* Driving a whole veto produces one side row per played map.
* Coin toss: the winner's chosen letter is the letter they end up holding, and
  Team A opens the draft.
