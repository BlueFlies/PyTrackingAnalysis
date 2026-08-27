# Creating and opening a Project

This is the **Project -> Create/Load** card at the top of the Hub's Project panel. Four buttons, because there are three different states a folder can be in before it is a Project, plus the editor for the one that is already open.

A **Project** is a directory with a `project.yaml`. That file is the authority for the shared design - experiment type, design factors and levels, facets, quality criteria, and counting-region names - and every replicate under it is hard-validated against it each time the Project loads.

## Which button

- **Open Project** - the directory exists *and* already has a `project.yaml`. Picking the directory that is already open re-reads it from disk, so replicates added or analyzed outside the Hub show up. There is no separate Reload button; the picker is the reload.
- **Create project...** - nothing exists yet. You choose where it goes, name it, and fill in the design; the directory is created for you and `project.yaml` is written into it.
- **Initialize existing directory...** - the directory exists (usually with replicate subdirectories already in it) but has no `project.yaml`. It keeps its own name, its subdirectories become the replicates, and the design shown in the dialog is inferred from the first subdirectory that already has a `tracking_config.yaml`. This is the path for a study you started before Projects existed.
- **Edit config...** - reopens the Project editor on the `project.yaml` of the Project that is currently loaded. Disabled until one is. If the file is missing, this button creates a default one and opens it.

If you point the Hub at a folder that is itself an **Experiment Directory** (it has a `tracking_config.yaml`, not a `project.yaml`), it offers to create the Project on the *parent* instead, so that experiment becomes a replicate of it.

## After it loads

The summary line under the buttons describes what is loaded: the Project name, its experiment type, how many replicates it found, its design factors, and any load warnings. Warnings here are design mismatches - a replicate whose factors, levels, experiment type, counting-region order, or any enforced `design.global` key disagrees with `project.yaml`. Fix the replicate's config (or the design) before running anything; the whole Project refuses to load while a replicate does not conform.

Nothing on the **Experiments** or **Analysis** cards is enabled until a Project is open, because everything below inherits the design this card establishes.

**Validate YAMLs**, at the bottom of the card, checks the open Project end to end: its `project.yaml` *and* every replicate's `tracking_config.yaml`, parse errors and semantic problems alike, each file reported separately with a count at the end. Results go to the Hub's log.

## Related topics

- **Project YAML** - every key in `project.yaml`, the two script sections, and what validation enforces.
- **Creating experiments** - the same three cases one level down, for replicates.
- **Project directory layout** - the on-disk shape of Experiments, Projects, and Batches.
