# Map art for the lobby

Drop one picture per map here and the final "ready to play" lobby message shows
it as an image card (in play order, with the sides). Leave a map's file out and
the lobby simply falls back to the plain map list — nothing breaks.

## Where files go

```
bot/assets/maps/<game>/<slug>.<ext>
```

- `<game>` is `valorant` or `cs2` (Dota 2 has no map veto, so no cards).
- `<slug>` is the map name **lowercased with everything but letters and digits
  removed** — see the table below.
- `<ext>` is one of `png`, `jpg`, `jpeg`, `webp` (checked in that order).

The slug rule lives in [`bot/core/assets.py`](../../core/assets.py) (`map_slug`).

## Examples

| Map name | File to add |
|----------|-------------|
| Ascent   | `valorant/ascent.png` |
| Dust II  | `cs2/dustii.png` |
| Mirage   | `cs2/mirage.png` |

## Recommended image

A landscape image (roughly 16:9, e.g. 800×450) reads best as an embed image.
Keep files reasonably small; they are uploaded with the lobby message.
