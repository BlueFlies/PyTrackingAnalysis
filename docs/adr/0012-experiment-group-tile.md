# The Experiment tile returns as a group: three container tiles over four sub-tiles

Amends ADR-0007 (the strip's tile set and widths) and ADR-0008 (which
removed the Experiment tile). The Experiment *panel* stays gone; what
returns is a tile with no panel of its own.

## Context

ADR-0008 made the Hub Project-first and dropped the Experiment tile, leaving
a flat strip of six: Batch · Project · Analyze · Plots · Scripts · AI. Two
levels of the containment hierarchy (a Batch holds Projects, a Project holds
experiments) had a tile each, and the third — the loaded experiment — was a
second summary line on the Project tile plus four sibling tiles for the
tools that act on it. The strip therefore read as six peers when it is
really three levels, with the last level's tools spread across two-thirds of
the row; and the Project tile's second line switched meaning (replicate
counts, then the loaded experiment) depending on state.

## Decision

- **The strip is three wide container tiles: Batch · Project · Experiment.**
  Each is 1.3125× a regular tile (155–257px instead of 118–196px: 1.75×,
  then a quarter off on 2026-08-29 so the readout keeps most of the strip),
  one width for all three so the hierarchy reads as three equal levels. The
  status readout takes what is left, as before.
- **The Experiment tile is a group, not a panel.** Clicking it expands a
  **sub-strip** — a second row of the four regular-width tiles it groups,
  **Analyze · Plots · Scripts · AI**, left-aligned under it — and clicking it
  again collapses the row. The sub-tiles are **title-only** (icon and name
  on a 38px chip): the Experiment tile above already says what is loaded,
  so their status lines go to the tooltip instead of the chip. The four tiles, their panels, cards, and handlers
  are the existing ones, unchanged; only their row moved. Opening one of
  those panels programmatically (the auto-open of Analyze after Load + QC)
  expands the sub-strip first, because the panel hangs from a tile in it.
- **The expanded group is "the open thing".** ADR-0007's one-at-a-time
  rule extends to it: choosing Batch or Project, or clicking away into the
  output, folds the sub-strip away together with any sub-tile panel, and a
  Batch or Project panel therefore always opens under the strip; expanding
  the group closes an open Batch or Project panel in turn. Collapsing
  the sub-strip closes a panel hanging from one of its tiles; panels anchor
  under the ribbon's last row (`_ribbon_bottom`), so a sub-tile panel sits
  under the sub-strip and never covers it.
- **The Experiment tile is enabled only while an experiment is loaded.**
  This is the one deliberate exception to ADR-0007's "dimmed but still
  clickable": that rule exists because a dimmed tile's panel holds the fix
  for its missing state, and the Experiment tile has no panel — nothing
  loads from it, and the row it would expand has nothing to act on. So with
  nothing loaded it is dimmed *and* inert, and its hint names where the fix
  is ("double-click a replicate in Project"). Unloading the experiment (a
  Create/Update report or a Batch Run, per ADR-0008's rule) collapses the
  sub-strip and closes any sub-tile panel.
- **Load status moves from the Project tile to the Experiment tile.** The
  Project tile's second line is always the replicates' state; the Experiment
  tile carries two complete thoughts — which experiment (its name, with its
  tracking type when that fits) and its flies (total, excluded, flagged).
  Each line is chosen to *fit*: the tile measures candidate wordings from
  most to least detailed and shows the first that renders without an
  ellipsis (`StatusTile.fitting`); the character cap of ADR-0007 remains
  only as the last resort for a name that cannot fit on its own.

Alternatives considered: keeping the six-tile strip and only widening Batch
and Project (leaves the hierarchy misread and gives the two entry tiles room
they have no text for); a seventh peer tile for Experiment (the same
misreading, one wider); the sub-tiles as an anchored panel of tiles (a panel
that opens panels — two overlays deep, and the sub-tiles' own panels would
have nowhere to anchor).

## Consequences

- `_hub_tiles.StatusTile` grows a `wide` mode (width range and summary cap
  scaled by `WIDE_SCALE`), a `set_clickable` gate, a `sizeHint` at the top
  of its range — left to the content hint, a wide tile drew at ~208px
  whatever the window — and `fits`/`fitting`, a measured alternative to the
  character cap for a summary that must not elide.
- The Hub's strip becomes a `_ribbon` (strip + `_sub_strip`); the click-away
  filter treats the whole ribbon as tile territory, and panel anchoring goes
  through `_ribbon_bottom()`. `_tiles` still holds all seven tiles by key, so
  tests and callers that address a tile by key are unchanged.
- The sub-strip adds one tile row (92px) below the strip while expanded, so
  the output area is that much shorter in the working state. At 1366px the
  ribbon fits with room to spare: three tiles at their maximum plus the
  readout's minimum is 955px, and the sub-strip's indent plus four tiles at
  their maximum is 1320px (their minimum, 1008px).
