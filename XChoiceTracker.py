import pandas as pd
import numpy as np 
import Tracker
import matplotlib.pyplot as plt
import matplotlib.patches as patches


class XChoiceTracker(Tracker.Tracker):
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        ## All of the relevant parameters are defined in the parent class.
        super().__init__(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)                
             
   
    def summarize(self, range_minutes=(0,0)):        
        tmp = Tracker.Tracker.summarize(self, range_minutes)
        data_subset = self.get_data_subset(range_minutes)
        avg_raw_x = data_subset['Xpos_mm'].mean()
        var_raw_x = data_subset['Xpos_mm'].var()
        avg_adjusted_x = self.get_x_positions(range_minutes).mean() 
        var_adjusted_x = self.get_x_positions(range_minutes).var()
        total_x_distance = self.rawdata['Xpos_mm'].diff().abs().sum() 
        result = pd.concat([tmp,pd.Series({'AvgX_mm': avg_raw_x}),pd.Series({"VarX_mm" : var_raw_x}),pd.Series({"AvgAdjX_mm" : avg_adjusted_x}),pd.Series({"VarAdjX_mm" : var_adjusted_x}),pd.Series({'TotalXDistance': total_x_distance})])
        return result
    
 