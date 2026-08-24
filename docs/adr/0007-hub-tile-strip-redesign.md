# The Hub becomes a tile strip with anchored panels

> Partly superseded by ADR-0008: the Experiment tile is gone (five tiles), and
> the "effective project" below — the selection, or its parent while a
> replicate was selected — was replaced by a selection that always names a
> Project, with the loaded experiment as a separate context.

## Context

The Hub's layout was a left sidebar plus a ~450px scrollable column of eight
stacked cards beside the output area. The column was a chronic fitting
problem — labels truncated, tables squeezed, repeated width fights — and it
permanently taxed the space the user actually watches: the log and the plots.

## Decision

- **A horizontal tile strip across the top replaces the card column**, Hub
  only (Config Editor, QC Viewer, and Plot Editor have no fitting problem
  and are untouched). Six consolidated tiles: **Project** (directory +
  identity + replicate health; absorbs the directory card, project view, and
  the Create/Load entry points), **Experiment** (the loaded replicate:
  name, flies, excluded/flagged, config), **Analyze**, **Plots**,
  **Scripts**, **AI**. Tools drops out of the strip and lives only in the
  sidebar. Eight 1:1 tiles were rejected (the fitting problem rotated 90°);
  four mega-tiles were rejected (the stacking problem moved inside the
  popup).
- **Each tile shows only live status** (icon, title, 2–3 summary lines).
  **All controls live in an anchored panel** that drops down under the
  clicked tile: frameless, one open at a time, Esc/click-away closes, and
  **starting a background task auto-closes it** so the streaming output is
  immediately visible. Panels are persistent hidden children created at
  startup — widget state survives open/close, and the existing tests'
  findChildren/click patterns keep working. Floating non-modal dialogs
  (window clutter, off-screen drift) and modal dialogs (hide the output at
  launch time) were rejected.
- **The sidebar stays but changes verb**: items open the matching panel
  (same as clicking the tile — one mental model, two entry points); the
  Create project / Create experiment rail actions remain; Tools opens only
  from the sidebar.
- **Everything below the strip is the output area at full width** — the
  existing Output/Errors tabs and plot dock, given the room the redesign is
  for.
- **Tiles are always present, context-dimmed**: fixed positions, a dimmed
  tile shows a one-line hint (e.g. Experiment: "double-click a replicate")
  and still opens its panel — the panel holds the very control that fixes
  the missing state. The Project tile always reflects the *effective*
  project (the enclosing one while a replicate is loaded). Hiding
  inapplicable tiles (positions jump) and disabling them (locks the user
  away from the fix) were rejected.

## Consequences

- hub.py is restructured around tiles/panels, but the Card widgets and every
  handler are reused inside panels — behavior-level tests largely survive.
- Tile summaries are a new live-status surface that must refresh on the same
  events as the project view (directory change, task completion).
- The strip is the new width constraint: tiles compress between 118–196px,
  giving the Hub a ~950px minimum width (fits 1366×768); tile summaries are
  hard-capped in length (full text in the tooltip) rather than allowed to
  grow.
- The strip, tiles, and panels use explicit per-theme surface colors
  (`ui.theme.surface_colors`) rather than `palette(...)` roles — qdarktheme
  leaves Window/Base/Mid at light values, which rendered unreadable light
  chips on the dark UI. The same fix was applied to the app-wide Card/TopBar
  QSS, healing a pre-existing dark-mode defect in all four apps.

## Amendment (2026-08-24): which tiles dim, and what dimming looks like

"Context-dimmed" was tracked but never painted: `StatusTile._dimmed` reached
no stylesheet, so all seven chips looked equally available in every state.
Dimming is now real — the tile recedes to the band color, its title and
summary go muted, and its icon renders in Qt's disabled mode — and it applies
to the Cards inside the panel too, so a state reads the same from the strip
and from the panel it opens.

Not every tile takes part. **Batch**, **Project**, and **Tools** never dim:
the first two are the way into the Hub (their panels hold the pickers that
create the state everything else waits on) and the third is housekeeping that
needs no subject. All three say their state in words instead — "no project —
open or create one", "selection is a project — load its parent to batch".
Dimming is reserved for the four tiles whose subject is a loaded replicate:
**Analyze**, **Plots**, **Scripts**, **AI**. AI dims without an experiment
even when a provider key is present — a key with nothing to summarize is not
"ready".
