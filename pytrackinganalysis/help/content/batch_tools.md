# Batch tools

The **Batch tools** button lives in the Hub's **Batch** panel and is currently disabled, pending a rework for the Project structure. These are housekeeping tools for immediate subdirectories of the currently selected folder, usually a Project root. They do not replace the Project workflow, and they are unrelated to Batch Runs over many Projects - for those, see the **Batch runs** help topic.

## Convert subdirectories

For each subdirectory, create a `data/` folder and move every non-YAML top-level file into it. Use this when old DTrack exports sit at the replicate root instead of inside `data/`.

## Rename helpers

- **Prepend to subdir names** adds a substring to the start of every subdirectory name.
- **Append to subdir names** adds a substring to the end of every subdirectory name.
- **Remove from subdir names** removes a substring from every subdirectory name.

The tool plans the renames first and skips collisions.

## Combine summary CSVs

Stack every `analysis/*_Summary.csv` and `analysis/*_Summary_Facet.csv` found under each subdirectory into `<folder>_combined.csv` and `<folder>_combined_facet.csv` at the current folder root. A `subdirectory` column records the source.

This is a legacy convenience output. For Project statistics, reports, and publication figures, use **Create report** or **Update report** in the Project panel.

## Copy YAML to subdirs

Pick a YAML file from the current folder and copy it into every immediate subdirectory, overwriting any file with the same name.

For new Project work, prefer **Experiment configs...**, which scaffolds each replicate config from `project.yaml`'s design. Use Copy YAML only when you deliberately want the same hand-prepared file in every subdirectory.
