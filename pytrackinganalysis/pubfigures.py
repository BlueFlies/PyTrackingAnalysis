"""Publication Figures: plotnine-rendered, journal-ready vector figures.

Per ADR-0004 this is a *separate* rendering path from the matplotlib report
figures: the two share the same summarized, exclusion-filtered data — never
rendering code. A figure is defined by a per-plot :class:`PlotSpec` (content:
labels, facet/treatment inclusion and order, limits, reference line) plus a
named, reusable :class:`PlotStyle` (look: size, theme, fonts, point/mean
styling, treatment colors). Both persist in ``<project>/plot_specs.yaml``,
written only by the Plot Editor; saved figures land in ``<project>/figures/``.

SVG output uses ``svg.fonttype='none'`` so labels arrive in Illustrator as
live, editable text; PDF embeds TrueType (fonttype 42) for the same reason.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field, asdict

import matplotlib
import pandas as pd
import yaml

SPECS_FILENAME = "plot_specs.yaml"
FIGURES_DIRNAME = "figures"

#: Ordered fallback palette for treatments a style does not name explicitly.
DEFAULT_PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706",
                   "#7c3aed", "#0891b2", "#64748b", "#be185d"]

_THEMES = ("classic", "bw", "minimal")
_MEAN_STYLES = ("point+sem", "bar+sem")
_GEOMS = ("dots", "box", "box+dots")
_STRIP_STYLES = ("plain", "boxed")

#: The faceted metric plots. ``ref_line`` / ``y_limits`` are per-type spec
#: defaults; ``y_label`` may carry ``{region1}`` (resolved per experiment).
PLOT_TYPES: dict[str, dict] = {
    "faceted_pi": {
        "metric": "FinalPI", "y_label": "Preference index",
        "y_limits": (-1.0, 1.0), "ref_line": 0.0,
        "display": "Preference index (faceted)",
    },
    "faceted_percentage": {
        "metric": "FinalPercentage", "y_label": "Fraction of time in {region1}",
        "y_limits": (0.0, 1.0), "ref_line": 0.5,
        "display": "Time in region 1 (faceted)",
    },
    "faceted_movement": {
        "metric": "TotalDistancePerMin", "y_label": "Movement (mm/min)",
        "y_limits": None, "ref_line": None,
        "display": "Movement (faceted)",
    },
    "faceted_transitions": {
        "metric": "TransitionsPerMin", "y_label": "Transitions per minute",
        "y_limits": None, "ref_line": None,
        "display": "Transitions (faceted)",
    },
}


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass
class PlotStyle:
    """A named, reusable look shared by every figure that references it."""

    width_mm: float = 180.0
    height_mm: float = 70.0
    #: Per-facet panel width (mm). 0 = off (the figure is ``width_mm`` wide
    #: and panels share it). >0 = the figure width is derived as
    #: ``axis margin + facet_width_mm × shown facets`` so each panel keeps the
    #: same width when facets are added or removed.
    facet_width_mm: float = 0.0
    theme: str = "classic"            # classic | bw | minimal
    font_family: str = "Arial"
    base_pt: float = 8.0
    point_size: float = 1.6
    point_alpha: float = 0.6
    jitter_width: float = 0.18
    mean_style: str = "point+sem"     # point+sem | bar+sem
    mean_color: str = "#111111"
    #: Black outline around each point (pt). 0 = no outline (points are drawn
    #: solid in the treatment color); >0 = black edge of this weight with the
    #: treatment color as the fill.
    point_stroke: float = 0.0
    #: Data geometry: jittered dots, boxplots, or boxplots with dots overlaid.
    geom: str = "dots"                # dots | box | box+dots
    #: ggplot-default facet strips: a bordered title box ("boxed") vs bare
    #: text ("plain"). ``strip_bg`` fills the box; ``panel_bg`` (empty = theme
    #: default) fills the plotting panels — the two are independent.
    strip_style: str = "plain"        # plain | boxed
    strip_bg: str = "#d9d9d9"
    panel_bg: str = ""
    #: Line weight (pt) for axis lines, ticks, panel/strip borders, and box
    #: outlines.
    line_pt: float = 0.8
    #: treatment name -> hex color; unmapped treatments cycle the palette.
    colors: dict = field(default_factory=dict)
    palette: list = field(default_factory=lambda: list(DEFAULT_PALETTE))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "PlotStyle":
        data = dict(data or {})
        known = {f for f in cls.__dataclass_fields__}
        style = cls(**{k: v for k, v in data.items() if k in known})
        if style.theme not in _THEMES:
            style.theme = "classic"
        if style.mean_style not in _MEAN_STYLES:
            style.mean_style = "point+sem"
        if style.geom not in _GEOMS:
            style.geom = "dots"
        if style.strip_style not in _STRIP_STYLES:
            style.strip_style = "plain"
        style.colors = dict(style.colors or {})
        style.palette = list(style.palette or DEFAULT_PALETTE)
        return style

    def color_for(self, treatment: str, index: int) -> str:
        explicit = (self.colors or {}).get(str(treatment))
        if explicit:
            return str(explicit)
        palette = self.palette or DEFAULT_PALETTE
        return palette[index % len(palette)]


@dataclass
class PlotSpec:
    """One figure's content decisions, plus the name of its style."""

    style: str = "default"
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    #: Phase labels to include, in order; None/empty = all phases.
    facets: list | None = None
    #: Original phase label -> display override for this figure.
    facet_labels: dict = field(default_factory=dict)
    #: treatment name -> {"label": display, "show": bool}; dict order = plot
    #: order. Treatments present in the data but absent here are appended.
    treatments: dict = field(default_factory=dict)
    y_limits: list | None = None
    ref_line: float | None = None
    #: Draw per-facet pairwise p-value brackets (Welch for two shown
    #: treatments, Tukey HSD beyond — the same policy as Stats.txt).
    p_values: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "PlotSpec":
        data = dict(data or {})
        known = {f for f in cls.__dataclass_fields__}
        spec = cls(**{k: v for k, v in data.items() if k in known})
        spec.facet_labels = dict(spec.facet_labels or {})
        spec.treatments = {
            str(name): {"label": str((entry or {}).get("label", name)),
                        "show": bool((entry or {}).get("show", True))}
            for name, entry in (spec.treatments or {}).items()
        }
        if spec.y_limits is not None:
            spec.y_limits = [float(v) for v in spec.y_limits]
        return spec


def default_spec(plot_id: str, region1: str = "region 1") -> PlotSpec:
    info = PLOT_TYPES[plot_id]
    y_limits = info["y_limits"]
    return PlotSpec(
        y_label=str(info["y_label"]).format(region1=region1),
        y_limits=list(y_limits) if y_limits is not None else None,
        ref_line=info["ref_line"],
    )


# --------------------------------------------------------------------------
# plot_specs.yaml
# --------------------------------------------------------------------------

@dataclass
class ProjectSpecs:
    """The parsed ``plot_specs.yaml``: named styles, the project default
    style, and the per-plot specs."""

    default_style: str = "default"
    styles: dict = field(default_factory=dict)   # name -> PlotStyle
    plots: dict = field(default_factory=dict)    # plot_id -> PlotSpec

    def style_for(self, spec: PlotSpec) -> PlotStyle:
        return (self.styles.get(spec.style)
                or self.styles.get(self.default_style)
                or PlotStyle())

    def ensure_default_style(self) -> None:
        if not self.styles:
            self.styles["default"] = PlotStyle()
        if self.default_style not in self.styles:
            self.default_style = next(iter(self.styles))


def specs_path(project_dir: str) -> str:
    return os.path.join(project_dir, SPECS_FILENAME)


def load_project_specs(project_dir: str) -> ProjectSpecs:
    path = specs_path(project_dir)
    raw: dict = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    specs = ProjectSpecs(
        default_style=str(raw.get("default_style", "default")),
        styles={str(k): PlotStyle.from_dict(v)
                for k, v in (raw.get("styles") or {}).items()},
        plots={str(k): PlotSpec.from_dict(v)
               for k, v in (raw.get("plots") or {}).items()
               if str(k) in PLOT_TYPES},
    )
    specs.ensure_default_style()
    return specs


def save_project_specs(project_dir: str, specs: ProjectSpecs) -> str:
    specs.ensure_default_style()
    payload = {
        "default_style": specs.default_style,
        "styles": {k: v.to_dict() for k, v in specs.styles.items()},
        "plots": {k: v.to_dict() for k, v in specs.plots.items()},
    }
    path = specs_path(project_dir)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
    return path


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def region1_name(experiment) -> str:
    regions = (getattr(experiment, "config", None) or {}).get("counting_regions") or {}
    for name in regions:
        return str(name)
    return "region 1"


def faceted_data(experiment, metric: str) -> pd.DataFrame:
    """Tidy per-fly data for one metric: Treatment, Phase (ordered), Value.

    Reads the exclusion-filtered summaries; without facet cutoffs the whole
    recording becomes a single phase.
    """
    cutoffs = getattr(experiment, "facet_cutoffs", None)
    if cutoffs:
        summary = experiment.arena.summarize_facet(cutoffs)
        windows: list = []
        for w in summary["FacetRange"]:
            if w not in windows:
                windows.append(w)
        exp_type = getattr(experiment, "experiment_type", None)
        if exp_type is not None:
            global_cfg = (getattr(experiment, "config", None) or {}).get("global") or {}
            labels = exp_type.phase_labels_for(windows, global_cfg)
        else:
            labels = [str(w) for w in windows]
        label_of = dict(zip(map(tuple, windows), labels))
        phase = summary["FacetRange"].map(lambda w: label_of[tuple(w)])
    else:
        summary = experiment.arena.summarize()
        labels = ["Whole recording"]
        phase = pd.Series(["Whole recording"] * len(summary), index=summary.index)

    if metric not in summary.columns:
        return pd.DataFrame(columns=["Treatment", "Phase", "Value"])
    df = pd.DataFrame({
        "Treatment": summary["Treatment"].astype(str).str.strip(),
        "Phase": pd.Categorical(phase, categories=labels, ordered=True),
        "Value": pd.to_numeric(summary[metric], errors="coerce"),
    })
    df = df[(df["Treatment"] != "") & df["Value"].notna()]
    return df.reset_index(drop=True)


def data_treatments(df: pd.DataFrame) -> list[str]:
    seen: list[str] = []
    for value in df["Treatment"]:
        if value not in seen:
            seen.append(value)
    return seen


def merged_treatments(spec: PlotSpec, df: pd.DataFrame) -> dict:
    """The spec's treatment table, completed with any treatments present in
    the data but not yet in the spec (appended, shown, own name as label)."""
    merged = {name: dict(entry) for name, entry in spec.treatments.items()}
    for name in data_treatments(df):
        merged.setdefault(name, {"label": name, "show": True})
    return merged


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

_INSTALLED_FAMILIES: set | None = None


def resolve_font_family(preferred: str) -> list[str]:
    """The preferred family filtered to what is actually installed, with sane
    sans fallbacks — so matplotlib never spams findfont warnings, and the SVG
    names a font the current machine really rendered with."""
    global _INSTALLED_FAMILIES
    if _INSTALLED_FAMILIES is None:
        from matplotlib import font_manager
        _INSTALLED_FAMILIES = {f.name for f in font_manager.fontManager.ttflist}
    candidates = [preferred, "Helvetica", "Arial", "Liberation Sans",
                  "DejaVu Sans"]
    available = [c for c in dict.fromkeys(candidates) if c in _INSTALLED_FAMILIES]
    return available or ["DejaVu Sans"]


#: Width allowance (mm) for the y-axis title, tick labels, and outer padding
#: when the figure width is derived from a per-facet width. Keeping it
#: constant is what makes each panel come out the same width regardless of
#: how many facets are shown.
_AXIS_MARGIN_MM = 16.0


def effective_width_mm(style: PlotStyle, n_facets: int | None) -> float:
    """The figure width to render at: ``width_mm``, unless a per-facet width
    is set — then margin + facet_width_mm × facets."""
    if style.facet_width_mm and style.facet_width_mm > 0 and n_facets:
        return _AXIS_MARGIN_MM + float(style.facet_width_mm) * int(n_facets)
    return float(style.width_mm)


def _theme_for(style: PlotStyle, n_facets: int | None = None):
    import plotnine as p9

    base = {"classic": p9.theme_classic,
            "bw": p9.theme_bw,
            "minimal": p9.theme_minimal}.get(style.theme, p9.theme_classic)
    families = resolve_font_family(style.font_family)
    lw = float(style.line_pt)
    overrides = dict(
        text=p9.element_text(family=families),
        figure_size=(effective_width_mm(style, n_facets) / 25.4,
                     style.height_mm / 25.4),
        legend_position="none",
        strip_text=p9.element_text(size=style.base_pt + 1),
        plot_title=p9.element_text(size=style.base_pt + 2),
        axis_line=p9.element_line(size=lw),
        axis_ticks=p9.element_line(size=lw),
    )
    # ggplot-default facet look: a bordered, filled title box per panel.
    if style.strip_style == "boxed":
        overrides["strip_background"] = p9.element_rect(
            fill=style.strip_bg or "#d9d9d9", color="black", size=lw)
        # A boxed strip reads best sitting on a bordered panel.
        overrides["panel_border"] = p9.element_rect(color="black", size=lw,
                                                    fill=None)
    else:
        overrides["strip_background"] = p9.element_blank()
    if style.panel_bg:
        overrides["panel_background"] = p9.element_rect(fill=style.panel_bg)
    return base(base_size=style.base_pt) + p9.theme(**overrides)


def build_ggplot(df: pd.DataFrame, spec: PlotSpec, style: PlotStyle):
    """The plotnine figure for a faceted metric plot: per-treatment jittered
    points, a mean with SEM overlay, one panel per phase."""
    import numpy as np
    import plotnine as p9

    treatments = merged_treatments(spec, df)
    order = [name for name, entry in treatments.items() if entry.get("show", True)]
    data = df[df["Treatment"].isin(order)].copy()

    # Facet inclusion and per-figure renaming.
    all_phases = list(data["Phase"].cat.categories)
    include = [p for p in (spec.facets or all_phases) if p in all_phases]
    data = data[data["Phase"].isin(include)].copy()
    shown = [str(spec.facet_labels.get(p, p)) for p in include]
    data["Phase"] = pd.Categorical(
        data["Phase"].astype(str).map(lambda p: str(spec.facet_labels.get(p, p))),
        categories=shown, ordered=True)

    # Treatment display order, labels, and colors (keyed by original name).
    labels = [str(treatments[name].get("label", name)) for name in order]
    colors = [style.color_for(name, i) for i, name in enumerate(order)]
    data["Treatment"] = pd.Categorical(
        data["Treatment"].astype(str).map(
            {n: str(treatments[n].get("label", n)) for n in order}),
        categories=labels, ordered=True)

    g = (p9.ggplot(data, p9.aes("Treatment", "Value", color="Treatment"))
         + p9.facet_wrap("~Phase", nrow=1)
         + p9.scale_color_manual(values=colors)
         + p9.labs(title=spec.title or "",
                   x=spec.x_label or "",
                   y=spec.y_label or ""))
    if spec.ref_line is not None:
        g = g + p9.geom_hline(yintercept=float(spec.ref_line),
                              linetype="dashed", color="#888888", size=0.3)

    # ---- data geometry ----------------------------------------------------
    boxed = style.geom in ("box", "box+dots")
    if boxed:
        g = g + p9.geom_boxplot(
            fill="white", width=0.6, size=style.line_pt * 0.9,
            outlier_size=(0 if style.geom == "box+dots"
                          else max(style.point_size * 0.8, 0.5)),
            outlier_alpha=style.point_alpha)
    if style.geom in ("dots", "box+dots"):
        stroke = max(0.0, float(style.point_stroke))
        if stroke > 0:
            # Outlined points: black edge, treatment color as the fill.
            g = (g
                 + p9.geom_jitter(p9.aes(fill="Treatment"), color="black",
                                  stroke=stroke, width=style.jitter_width,
                                  height=0, size=style.point_size,
                                  alpha=style.point_alpha, random_state=0)
                 + p9.scale_fill_manual(values=colors))
        else:
            g = g + p9.geom_jitter(width=style.jitter_width, height=0,
                                   size=style.point_size,
                                   alpha=style.point_alpha, random_state=0)
    if not boxed:
        # Mean ± SEM overlay belongs to the dot plot; a boxplot already
        # carries its own centre and spread.
        stats = (data.groupby(["Phase", "Treatment"], observed=True)["Value"]
                 .agg(mean="mean", sd="std", n="count").reset_index())
        stats["sem"] = (stats["sd"] / np.sqrt(stats["n"].clip(lower=1))).fillna(0.0)
        stats["lo"] = stats["mean"] - stats["sem"]
        stats["hi"] = stats["mean"] + stats["sem"]
        if style.mean_style == "bar+sem":
            g = (g
                 + p9.geom_errorbar(p9.aes(x="Treatment", ymin="lo", ymax="hi"),
                                    data=stats, inherit_aes=False, width=0.18,
                                    color=style.mean_color, size=0.5)
                 + p9.geom_errorbar(p9.aes(x="Treatment", ymin="mean",
                                           ymax="mean"),
                                    data=stats, inherit_aes=False, width=0.45,
                                    color=style.mean_color, size=0.9))
        else:
            g = g + p9.geom_pointrange(
                p9.aes(x="Treatment", y="mean", ymin="lo", ymax="hi"),
                data=stats, inherit_aes=False, color=style.mean_color,
                size=0.5, fatten=2.5)

    # ---- p-value brackets -------------------------------------------------
    y_limits = list(spec.y_limits) if spec.y_limits is not None else None
    if spec.p_values:
        layers, y_limits = _pvalue_layers(data, style, y_limits)
        for layer in layers:
            g = g + layer

    if y_limits is not None:
        g = g + p9.coord_cartesian(ylim=tuple(y_limits))
    return g + _theme_for(style, n_facets=len(shown))


def facet_pvalues(data: pd.DataFrame) -> pd.DataFrame:
    """Per-facet pairwise p-values on the displayed groups — Welch's t-test
    for two treatments, Tukey HSD beyond, the same policy as Stats.txt.
    Columns: ``Phase, a, b, p`` (a/b are display labels)."""
    def _levels(series: pd.Series):
        if isinstance(series.dtype, pd.CategoricalDtype):
            return list(series.cat.categories)
        return list(dict.fromkeys(series))

    rows: list = []
    for phase in _levels(data["Phase"]):
        sub = data[data["Phase"] == phase]
        groups = {}
        for treat in _levels(sub["Treatment"]):
            vals = sub.loc[sub["Treatment"] == treat, "Value"].values
            if len(vals) >= 2:
                groups[str(treat)] = vals
        if len(groups) < 2:
            continue
        try:
            if len(groups) == 2:
                from scipy import stats as sstats
                (name_a, vals_a), (name_b, vals_b) = groups.items()
                _stat, p = sstats.ttest_ind(vals_a, vals_b, equal_var=False)
                rows.append((phase, name_a, name_b, float(p)))
            else:
                import itertools

                import numpy as np
                from statsmodels.stats.multicomp import pairwise_tukeyhsd
                endog = np.concatenate(list(groups.values()))
                labels = np.concatenate([[t] * len(v)
                                         for t, v in groups.items()])
                res = pairwise_tukeyhsd(endog=endog, groups=labels, alpha=0.05)
                for (ga, gb), p in zip(
                        itertools.combinations(res.groupsunique, 2),
                        res.pvalues):
                    rows.append((phase, str(ga), str(gb), float(p)))
        except Exception:  # noqa: BLE001
            continue
    return pd.DataFrame(rows, columns=["Phase", "a", "b", "p"])


def _pvalue_layers(data: pd.DataFrame, style: PlotStyle, y_limits):
    """Bracket + label layers for per-facet pairwise p-values, ggpubr-style.

    Brackets stack above each facet's data; when explicit y-limits would clip
    them the upper limit is extended, so the annotation is never cut off.
    Returns ``(layers, effective_y_limits)``.
    """
    import plotnine as p9

    pvals = facet_pvalues(data)
    if pvals.empty:
        return [], y_limits
    levels = (list(data["Treatment"].cat.categories)
              if isinstance(data["Treatment"].dtype, pd.CategoricalDtype)
              else list(dict.fromkeys(data["Treatment"])))
    xpos = {t: i + 1 for i, t in enumerate(levels)}

    lo = float(min(data["Value"].min(),
                   y_limits[0] if y_limits is not None else data["Value"].min()))
    hi = float(max(data["Value"].max(),
                   y_limits[1] if y_limits is not None else data["Value"].max()))
    span = (hi - lo) or 1.0
    step, tick = 0.09 * span, 0.02 * span

    seg_rows, label_rows = [], []
    top = hi
    for phase in pvals["Phase"].unique():
        base = float(data.loc[data["Phase"] == phase, "Value"].max())
        for k, (_, row) in enumerate(pvals[pvals["Phase"] == phase].iterrows()):
            x1, x2 = xpos[row["a"]], xpos[row["b"]]
            y = base + step * (k + 0.7)
            seg_rows += [
                (phase, x1, x2, y, y),           # bracket bar
                (phase, x1, x1, y, y - tick),    # left tick
                (phase, x2, x2, y, y - tick),    # right tick
            ]
            label_rows.append((phase, (x1 + x2) / 2, y + tick * 0.6,
                               f"{row['p']:.2g}"))
            top = max(top, y + step * 0.6)
    segments = pd.DataFrame(seg_rows,
                            columns=["Phase", "x", "xend", "y", "yend"])
    labels = pd.DataFrame(label_rows, columns=["Phase", "x", "y", "label"])
    ## Layer data participates in facet layout: plain strings here would union
    ## alphabetically and scramble the phase order, so mirror the categorical.
    if isinstance(data["Phase"].dtype, pd.CategoricalDtype):
        cats = data["Phase"].cat.categories
        segments["Phase"] = pd.Categorical(segments["Phase"], categories=cats,
                                           ordered=True)
        labels["Phase"] = pd.Categorical(labels["Phase"], categories=cats,
                                         ordered=True)

    layers = [
        p9.geom_segment(p9.aes(x="x", xend="xend", y="y", yend="yend"),
                        data=segments, inherit_aes=False, color="#111111",
                        size=max(style.line_pt * 0.6, 0.3)),
        p9.geom_text(p9.aes(x="x", y="y", label="label"), data=labels,
                     inherit_aes=False, color="#111111",
                     size=style.base_pt * 0.95, va="bottom"),
    ]
    if y_limits is not None and top > y_limits[1]:
        y_limits = [y_limits[0], top]
    return layers, y_limits


def figure_for(experiment, plot_id: str, spec: PlotSpec, style: PlotStyle):
    metric = PLOT_TYPES[plot_id]["metric"]
    return build_ggplot(faceted_data(experiment, metric), spec, style)


#: rcParams that keep vector text editable: SVG text stays text; PDF embeds
#: TrueType (Type 42) rather than converting to Type 3 outlines.
_VECTOR_RC = {"svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42}


def save_ggplot(g, path: str, style: PlotStyle, dpi: int = 300) -> str:
    """Write *g* to *path* (format from the suffix).

    The size comes from the figure's own theme (set by :func:`build_ggplot`),
    which is facet-aware when the style uses a per-facet width."""
    del style  # kept for call-site symmetry; the theme owns the size
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with matplotlib.rc_context(_VECTOR_RC):
        g.save(path, dpi=dpi, verbose=False)
    return path


def render_png_bytes(g, style: PlotStyle, dpi: int = 120) -> bytes:
    """Raster preview from the SAME figure object the vector save uses."""
    del style  # the theme owns the size; see save_ggplot
    buf = io.BytesIO()
    with matplotlib.rc_context(_VECTOR_RC):
        g.save(buf, format="png", dpi=dpi, verbose=False)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Headless batch render
# --------------------------------------------------------------------------

def render_all(experiment, fmt: str = "svg", out_dir: str | None = None,
               plot_ids: list[str] | None = None) -> list[str]:
    """Re-render figures straight from ``plot_specs.yaml`` (no editor).

    Renders *plot_ids*, else every plot the file defines, else all known
    plot types with their defaults. Returns the written paths.
    """
    project_dir = getattr(experiment, "project_directory", None) or "."
    specs = load_project_specs(project_dir)
    ids = list(plot_ids or specs.plots.keys() or PLOT_TYPES.keys())
    out_dir = out_dir or os.path.join(project_dir, FIGURES_DIRNAME)
    region1 = region1_name(experiment)

    written: list[str] = []
    for plot_id in ids:
        if plot_id not in PLOT_TYPES:
            continue
        spec = specs.plots.get(plot_id) or default_spec(plot_id, region1)
        style = specs.style_for(spec)
        g = figure_for(experiment, plot_id, spec, style)
        path = os.path.join(out_dir, f"{plot_id}.{fmt}")
        save_ggplot(g, path, style)
        written.append(path)
    return written
