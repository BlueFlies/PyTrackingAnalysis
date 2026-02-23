What was changed
XChoiceTracker.py

Bug fix: total_x_distance now uses data_subset (respects range_minutes) instead of the full self.rawdata
Column renamed TotalXDistance → TotalXDistance_mm to match the name Arena's plotting code already expected
Parameters.py

Removed the duplicate __str__ (was defined twice; second silently overwrote first)
Extracted _set_rig_values() and _set_pairwise_rig_values() private helpers — all 11 preset methods now delegate to these, eliminating ~100 lines of repeated boilerplate
Fixed mutable default argument (micromove_speed_mm_sec=None with internal default list)
Tracker.py

__str__ no longer references the nonexistent TotalDistanceDTrack column (would have crashed on print(tracker))
Removed dead total_distance_dtrack calculation from summarize()
Fixed six "Fipped" → "Flipped" typos in plot titles
SpecialFunctions.py

Replaced ~250 lines of duplicated logic with thin delegation wrappers that call the new Arena methods, preserving backward compatibility
ExperimentalDesign.py

Replaced two bare except blocks with FileNotFoundError, KeyError/ValueError, and Exception handlers that emit proper logging.warning() messages
read_yaml_config now raises directly (no silent suppression) so the caller gets meaningful messages
Arena.py

Added import logging / logger
get_experimental_design bare except replaced with specific ValueError + Exception catches with logger.warning()
Fixed the duplicate plot_adjusted_x_position_facet definition — the backend implementation is now correctly named plot_adj_x_pos_facet_xchoicetracker, restoring the type-checking public dispatcher
Added four new methods ported from SpecialFunctions: analyze_rle_data(), analyze_rle_data_facet(), analyze_distance_by_light(), analyze_distance_by_light_facet() — CSV paths now use self.data_path/experiment_name instead of hardcoded ./Data/
Experiment.py — six new user-facing methods plus facet_cutoffs:

Method / attribute	What it does
facet_cutoffs	Set once (from yaml global.facet_cutoffs or default (10,70)), used everywhere
info()	Prints experiment name, rig, tracker count/quality, time range, paths
qc(cutoff, save)	Prints quality report; saves {name}_data_quality.csv to qc/
save_summary(cutoffs)	Saves flat + faceted summary CSVs to analysis/
stats(cutoffs, save)	Runs all appropriate pairwise comparisons; saves {name}_Stats.txt
save_plots(cutoffs)	Intercepts plt.show() calls and saves all relevant plots as PNGs to analysis/
run_analysis()	Calls all four above in sequence — full pipeline in one line
