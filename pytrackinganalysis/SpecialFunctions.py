"""
SpecialFunctions.py — legacy module.

These functions are now methods on the Arena class.  This module remains for
backward compatibility but simply delegates to the corresponding Arena methods.
"""
import numpy as np
import pandas as pd
from .Arena import Arena
from .Parameters import Parameters, TrackingType


def analyze_rle_data(arena: Arena, change_none_to_light=True, min_duration_frames=1, range_minutes=(0, 0)):
    """Deprecated: call arena.analyze_rle_data() instead."""
    return arena.analyze_rle_data(
        change_none_to_light=change_none_to_light,
        min_duration_frames=min_duration_frames,
        range_minutes=range_minutes,
    )


def analyze_rle_data_facet(arena: Arena, cutoffs=(10, 70), change_none_to_light=True,
                           min_duration_frames=1, write_to_csvfile=False):
    """Deprecated: call arena.analyze_rle_data_facet() instead."""
    return arena.analyze_rle_data_facet(
        cutoffs=cutoffs,
        change_none_to_light=change_none_to_light,
        min_duration_frames=min_duration_frames,
        write_to_csvfile=write_to_csvfile,
    )


def analyze_distance_by_light(arena: Arena, range_minutes=(0, 0)):
    """Deprecated: call arena.analyze_distance_by_light() instead."""
    return arena.analyze_distance_by_light(range_minutes=range_minutes)


def analyze_distance_by_light_facet(arena: Arena, cutoffs=(10, 70),
                                    copy_to_clipboard=False, write_to_csvfile=True):
    """Deprecated: call arena.analyze_distance_by_light_facet() instead."""
    return arena.analyze_distance_by_light_facet(
        cutoffs=cutoffs,
        copy_to_clipboard=copy_to_clipboard,
        write_to_csvfile=write_to_csvfile,
    )


#region ########### Distance and Time Analysis Functions ############
def analyze_distance_by_light(arena:Arena, range_minutes=(0,0)):
    """
    Analyze distance moved and time spent in light vs no light regions for all trackers.
    
    For each tracker, this function subsets rows based on whether the CountingRegion 
    column values belong to the "Light" or "NoLight" groups (as defined in 
    counting_regions_design), then sums the "Dist_mm" and "DeltaSec" columns.
    
    Parameters:
    range_minutes (tuple): Range of minutes to analyze. Default (0,0) means analyze all data.
    
    Returns:
    DataFrame: Combined results containing:
        - Tracker: Tracker identifier
        - Treatment: Treatment group
        - Light_Distance_mm: Total distance moved in light regions (mm)
        - NoLight_Distance_mm: Total distance moved in no light regions (mm)
        - Light_Time_sec: Total time spent in light regions (seconds)
        - NoLight_Time_sec: Total time spent in no light regions (seconds)
        - Light_Distance_mm_sec: Light distance divided by time (mm/sec)
        - NoLight_Distance_mm_sec: No light distance divided by time (mm/sec)
    """
    results = []
    
    for key, tracker in arena.trackers.items():
        # Get data subset for the specified time range
        data_subset = tracker.get_data_subset(range_minutes)
        
        # Get treatment information
        treatment = tracker.tracking_region_design['Treatment'].iloc[0] if tracker.tracking_region_design is not None else "Unknown"
        
        # Get counting region design to determine Light vs NoLight groups
        if tracker.counting_regions_design is None:
            # If no counting regions design, skip this tracker or use default
            continue
        
        # Find which group names correspond to Light and NoLight
        # The counting_regions_design is a dict like {'Light': ['Light', 'Lt', 'L'], 'NoLight': ['NoLight', 'NL', 'N']}
        light_group_name = None
        nolight_group_name = None
        
        for group_name in tracker.counting_regions_design.keys():
            group_name_lower = group_name.lower()
            if 'light' in group_name_lower and 'no' not in group_name_lower:
                light_group_name = group_name
            elif 'nolight' in group_name_lower or ('no' in group_name_lower and 'light' in group_name_lower):
                nolight_group_name = group_name
        
        # If we can't find the groups by name, use the first two groups
        if light_group_name is None or nolight_group_name is None:
            group_names = list(tracker.counting_regions_design.keys())
            if len(group_names) >= 2:
                light_group_name = group_names[0]
                nolight_group_name = group_names[1]
            else:
                # Skip this tracker if we can't determine the groups
                continue
        
        # Get the list of CountingRegion values for each group
        light_values = tracker.counting_regions_design[light_group_name]
        nolight_values = tracker.counting_regions_design[nolight_group_name]
        
        # Check if CountingRegion column exists
        if 'CountingRegion' not in data_subset.columns:
            # Skip this tracker if CountingRegion column doesn't exist
            continue
        
        # Subset rows for light and no light regions
        light_data = data_subset[data_subset['CountingRegion'].isin(light_values)]
        nolight_data = data_subset[data_subset['CountingRegion'].isin(nolight_values)]
        
        # Sum distance and time for each region
        light_distance = light_data['Dist_mm'].sum() if 'Dist_mm' in light_data.columns else 0
        nolight_distance = nolight_data['Dist_mm'].sum() if 'Dist_mm' in nolight_data.columns else 0
        light_time = light_data['DeltaSec'].sum() if 'DeltaSec' in light_data.columns else 0
        nolight_time = nolight_data['DeltaSec'].sum() if 'DeltaSec' in nolight_data.columns else 0
        
        # Store results
        result = {
            'Tracker': key,
            'Treatment': treatment,
            'Light_Distance_mm': light_distance,
            'NoLight_Distance_mm': nolight_distance,
            'Light_Time_sec': light_time,
            'NoLight_Time_sec': nolight_time
        }
        
        results.append(result)
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)

    # Add Light_Distance_mm_sec and NoLight_Distance_mm_sec columns
    # Handle division by zero by filling with np.nan
    import numpy as np
    results_df['Light_Distance_mm_sec'] = results_df['Light_Distance_mm'] / results_df['Light_Time_sec']
    results_df['NoLight_Distance_mm_sec'] = results_df['NoLight_Distance_mm'] / results_df['NoLight_Time_sec']
    results_df['Light_Distance_mm_sec'] = results_df['Light_Distance_mm_sec'].replace([np.inf, -np.inf], np.nan)
    results_df['NoLight_Distance_mm_sec'] = results_df['NoLight_Distance_mm_sec'].replace([np.inf, -np.inf], np.nan)

    return results_df

    
def analyze_distance_by_light_facet(arena:Arena, cutoffs=(10,70), copy_to_clipboard=False, write_to_csvfile=True):
    """
    Analyze distance moved and time spent in light vs no light regions across time facets.
    
    Parameters:
    cutoffs (tuple): Cutoff values for facets.
    copy_to_clipboard (bool): Flag to copy results to clipboard.
    write_to_csvfile (bool): Flag to write results to CSV file.
    
    Returns:
    DataFrame: Combined results with FacetRange column.
    """
    if(isinstance(cutoffs, tuple)):
        cutoffs = list(cutoffs)
    elif(isinstance(cutoffs, int)):
        cutoffs = [cutoffs]
    else:
        raise ValueError("Invalid cutoffs. Must be a tuple or a single integer")
    cutoffs.insert(0,0)
    cutoffs.append(float('inf'))
    results = []
    for i in range(len(cutoffs)-1):
        tmp = analyze_distance_by_light(arena, range_minutes=tuple([cutoffs[i],cutoffs[i+1]]))
        tmp['FacetRange']=[tuple([cutoffs[i],cutoffs[i+1]])]*len(tmp)
        results.append(tmp)
    all_results = pd.concat(results, ignore_index=True)
    if(copy_to_clipboard):            
        all_results.to_clipboard(index=False)
    if(write_to_csvfile==True):            
        all_results.to_csv(f"./Data/DistanceByLight_Facet.csv",index=False)      
    return all_results

#endregion ########### Distance and Time Analysis Functions ############
def stack_summary_files(data_dir='./Data/', output_dir='./'):
    """
    Stack CSV files from subdirectories that match specific prefixes.
    
    This function iterates through all subdirectories of the data directory,
    finds CSV files that begin with 'cap', 'flav', or 'ver' and end with
    '*_Summary_Facet.csv', then stacks them into three output files.
    
    Parameters:
    data_dir (str): Path to the data directory containing subdirectories. Default: './Data/'
    output_dir (str): Path where output files will be saved. Default: './'
    
    Returns:
    dict: Dictionary with keys 'cap', 'flav', 'ver' containing the paths to created files.
    """
    prefixes = ['Cap', 'Flav', 'Ver']
    results = {}
    
    for prefix in prefixes:
        all_dataframes = []
        found_files = []
        
        # Walk through all subdirectories
        for root, dirs, files in os.walk(data_dir):
            # Look for matching CSV files in each subdirectory
            pattern = os.path.join(root, f"{prefix}*_Summary.csv")
            matching_files = glob.glob(pattern)
            
            for file_path in matching_files:
                try:
                    df = pd.read_csv(file_path, keep_default_na=False, na_values=['NaN'])
                    # Add a column to track source file if desired
                    df['SourceFile'] = os.path.relpath(file_path, data_dir)
                    all_dataframes.append(df)
                    found_files.append(file_path)
                except Exception as e:
                    print(f"Warning: Could not read {file_path}: {e}")
                    continue
        
        if len(all_dataframes) > 0:
            # Concatenate all dataframes
            combined_df = pd.concat(all_dataframes, ignore_index=True)
            
            # Save to output file
            output_file = os.path.join(output_dir, f"Pooled_Summary_{prefix}.csv")
            combined_df.to_csv(output_file, index=False, na_rep='NA')
            results[prefix] = output_file
            print(f"Created {output_file} with {len(combined_df)} rows from {len(found_files)} files")
        else:
            print(f"No files found matching pattern '{prefix}*_Summary_Facet.csv' in {data_dir}")
            results[prefix] = None
    
    return results

def stack_summary_facet_files(data_dir='./Data/', output_dir='./'):
    """
    Stack CSV files from subdirectories that match specific prefixes.
    
    This function iterates through all subdirectories of the data directory,
    finds CSV files that begin with 'cap', 'flav', or 'ver' and end with
    '*_Summary_Facet.csv', then stacks them into three output files.
    
    Parameters:
    data_dir (str): Path to the data directory containing subdirectories. Default: './Data/'
    output_dir (str): Path where output files will be saved. Default: './'
    
    Returns:
    dict: Dictionary with keys 'cap', 'flav', 'ver' containing the paths to created files.
    """
    prefixes = ['Cap', 'Flav', 'Ver']
    results = {}
    
    for prefix in prefixes:
        all_dataframes = []
        found_files = []
        
        # Walk through all subdirectories
        for root, dirs, files in os.walk(data_dir):
            # Look for matching CSV files in each subdirectory
            pattern = os.path.join(root, f"{prefix}*_Summary_Facet.csv")
            matching_files = glob.glob(pattern)
            
            for file_path in matching_files:
                try:
                    df = pd.read_csv(file_path, keep_default_na=False, na_values=['NaN'])
                    # Add a column to track source file if desired
                    df['SourceFile'] = os.path.relpath(file_path, data_dir)
                    all_dataframes.append(df)
                    found_files.append(file_path)
                except Exception as e:
                    print(f"Warning: Could not read {file_path}: {e}")
                    continue
        
        if len(all_dataframes) > 0:
            # Concatenate all dataframes
            combined_df = pd.concat(all_dataframes, ignore_index=True)
            
            # Save to output file
            output_file = os.path.join(output_dir, f"Pooled_Summary_Facet_{prefix}.csv")
            combined_df.to_csv(output_file, index=False, na_rep='NA')
            results[prefix] = output_file
            print(f"Created {output_file} with {len(combined_df)} rows from {len(found_files)} files")
        else:
            print(f"No files found matching pattern '{prefix}*_Summary_Facet.csv' in {data_dir}")
            results[prefix] = None
    
    return results