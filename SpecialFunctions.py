"""
SpecialFunctions.py — legacy module.

These functions are now methods on the Arena class.  This module remains for
backward compatibility but simply delegates to the corresponding Arena methods.
"""
import numpy as np
import pandas as pd
from Arena import Arena
from Parameters import Parameters, TrackingType


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
