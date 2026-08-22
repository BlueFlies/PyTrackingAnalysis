# Plot Editor

The Plot Editor (`pytrack-plots`) creates Project-level publication figures from pooled replicate data. It writes `plot_specs.yaml` and vector files under `figures/`; it does not edit `project.yaml` or any `tracking_config.yaml`.

## Before opening

Run **Build combined analysis** first. The Plot Editor needs the Project's combined faceted summary data. If you open a replicate inside a Project, the app redirects to the Project root. A standalone experiment is refused with guidance to create a Project around it first.

## What it edits

- **`plot_specs.yaml`** stores Plot Specs and Plot Styles.
- **`figures/*.svg`** and **`figures/*.pdf`** are saved publication outputs.

SVG text stays editable in Illustrator. PDF output embeds fonts.

## Main controls

- **Open project...** loads the Project.
- **Plot** chooses the metric figure to edit.
- **Style** chooses the shared style used by the current plot.
- **Save style as...** stores the current look under a new style name.
- **Set as project default** makes that style the default for new or reset plots.
- **Restore defaults** resets the current plot's content settings, not the shared style.
- **Save SVG...** and **Save PDF...** write vector files to `figures/`.

## Left panel

**Style (shared across plots)** controls figure size, font, theme, point styling, mean styling, geometry, line weights, strip style, and optional panel background.

**This plot** controls title, axis labels, y limits, independent y axes, reference line, p-value brackets, and whether points are marked by replicate.

**Facets** lets you include, exclude, and rename phases.

**Treatments** lets you include, exclude, rename, recolor, and reorder treatment groups.

## Project-specific options

- **Mark experiments** gives each replicate its own point shape and legend.
- **P-value brackets** use the same treatment-comparison policy as the statistics output: Welch's t-test for two treatments and Tukey HSD for more.
- **Free y** is useful for movement and transitions, where each phase may need its own scale.

## Headless rendering

The same specs can be rendered without opening the app by the Project API or a Project Script:

```
Project(project_dir).render_figures(formats=("svg", "pdf"))
```

The Project Script action is **Render publication figures**.
