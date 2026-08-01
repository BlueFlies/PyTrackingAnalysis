import pandas as pd
import numpy as np 
from . import Tracker
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class XChoiceTracker(Tracker.Tracker):
    """
    A class to represent an XChoiceTracker. It is important to properly set up the 
    experimental design file to have the proper X position polarity to use this class

    Inherits from Tracker.
    Generally not called by the user.
    
    Methods
    -------
    summarize(range_minutes=(0, 0)):
        Summarizes the data for the given range of minutes.
    """

    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design, rawdata):
        """
        Constructs all the necessary attributes for the XChoiceTracker object.
        Generally not called by the user.
        Parameters
        ----------
        tracking_region_id : str
            The ID of the tracking region.
        object_id : str
            The ID of the object.
        tracking_regions : DataFrame
            The tracking regions.
        counting_regions : DataFrame
            The counting regions.
        parameters : object
            The parameters for the tracker.
        exp_design : object
            The experimental design.
        rawdata : DataFrame
            The raw data for the tracker.
        """
        super().__init__(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design, rawdata)                
             
    def summarize(self, range_minutes=(0, 0)):        
        """
        Summarizes the data for the given range of minutes.

        Parameters (optional)
        ----------
        range_minutes : tuple, optional
            The range of minutes to summarize (default is (0, 0)).

        Returns
        -------
        Series
            A summary of the data.
        """
        tmp = Tracker.Tracker.summarize(self, range_minutes)
        data_subset = self.get_data_subset(range_minutes)
        avg_raw_x = data_subset['Xpos_mm'].mean()
        var_raw_x = data_subset['Xpos_mm'].var()
        avg_adjusted_x = self.get_x_positions(range_minutes).mean() 
        var_adjusted_x = self.get_x_positions(range_minutes).var()
        ## XDist_mm is windowed by get_data_subset with the same step-attribution
        ## rule as Dist_mm; diffing the slice here would drop the step that
        ## crosses into the window and disagree with TotalDistance.
        total_x_distance = data_subset['XDist_mm'].sum()
        result = pd.concat([tmp, pd.Series({'AvgX_mm': avg_raw_x}), pd.Series({"VarX_mm" : var_raw_x}), pd.Series({"AvgAdjX_mm" : avg_adjusted_x}), pd.Series({"VarAdjX_mm" : var_adjusted_x}), pd.Series({'TotalXDistance_mm': total_x_distance})])
        return result