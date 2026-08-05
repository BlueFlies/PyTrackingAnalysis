# Batch tools

Open from the Hub **Tools → Batch tools**. Operates on **immediate subdirectories** of the current project (parent) folder.

## Convert subdirectories

For each subdirectory, create a `data/` folder and move every non-YAML file at the top level into it. Use this to prep folders that still have DTrack exports at the root.

## Rename helpers

- **Prepend / Append** — add a substring to every subdirectory name.
- **Remove** — strip a substring from every subdirectory name.

## Combine summary CSVs

Stack every `analysis/*_Summary.csv` and `*_Summary_Facet.csv` under each subdirectory into `<project>_combined.csv` and `<project>_combined_facet.csv` at the parent root. Adds a `subdirectory` column for origin.

## Copy YAML to subdirs

Pick a YAML from the parent directory and copy it into every subdirectory (overwrites if present). Useful when all trials share one design / `batch` script template — then edit per folder only if needed.

After preparing folders, use Hub **Load → Batch experiments → Run batch script**.
