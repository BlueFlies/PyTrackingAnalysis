# The Hub becomes a tile strip with anchored panels

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
- The strip is the new width constraint: six tiles must fit a laptop window;
  tile summaries are hard-capped in length rather than allowed to grow.
