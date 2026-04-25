"""
SpecialFunctions.py — legacy module.

These functions are now methods on the Arena class.  This module remains for
backward compatibility but simply delegates to the corresponding Arena methods.
"""
import glob
import os

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