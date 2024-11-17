import pandas as pd
import numpy as np 
import Tracker
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class PairwiseInteractionTracker(Tracker.Tracker):
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        ## All of the relevant parameters are defined in the parent class.
        super().__init__(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)     
  
    
    
    def set_neighbor(self,neighbor_tracker):
        self.neighbor_tracker = neighbor_tracker
        
        if 'ClosestNeighbor' not in self.rawdata.columns:           
            self.set_neighbor_distance()
        
        self.set_neighbor_quality_and_distance_mm()
        self.update_neighbor_interactions()
    
    
    ## This function is called in Arena post processing because it needs access
    ## to other trackers.       
    def set_neighbor_distance(self):
        ## Check to make sure the short cut will work.
        ## It will only if each row of each tracker has the same frame number.
        if(sum(self.rawdata['Frame'] - self.neighbor_tracker.rawdata['Frame'])!=0):
            raise ValueError(f"Frame mismatch between trackers.")
    
        ## This is the distance between the two trackers at the current time point.
        x1 = self.rawdata['X']
        y1 = self.rawdata['Y']
        x2 = self.neighbor_tracker.rawdata['X']
        y2 = self.neighbor_tracker.rawdata['Y']
        distance = np.sqrt((x1-x2)**2+(y1-y2)**2) 
        self.rawdata['ClosestNeighbor']=distance

    ## This function is called in Arena post processing because it needs access
    ## to other trackers.       
    def set_neighbor_quality_and_distance_mm(self):
        ## This will be a column that is true if the quality of the data is high for both trackers.
        ## This will be used to filter out bad data.
         ## Create a boolean column flagging measures that may not be valid.
        ## If at least one of the two was not found.
        ## Values are High, Low, Indiscrenable, and Not Found.  I don't know whether Low is ever used.
        quality = (self.rawdata['DataQuality']=="High") & (self.neighbor_tracker.rawdata['DataQuality']=="High")
        one_blob = (self.rawdata['NObjects'] + self.neighbor_tracker.rawdata['NObjects']) == 2
        neg_one_distance = (self.rawdata['ClosestNeighbor'] == -1) | (self.neighbor_tracker.rawdata['ClosestNeighbor'] == -1) 
        
        final_quality = quality | one_blob | (~neg_one_distance)
        
        self.rawdata['IsNeighborValid'] = final_quality 
        
        self.rawdata['ClosestNeighbor_mm'] = self.rawdata['ClosestNeighbor']
        self.rawdata.loc[~self.rawdata['IsNeighborValid'], 'ClosestNeighbor_mm'] = np.nan
        self.rawdata['ClosestNeighbor_mm'] *= self.parameters.mm_per_pixel

    def get_interaction_subset(self, range_minutes):
        if(len(range_minutes)!=2):            
            raise ValueError(f"Invalid range_minutes: {range_minutes}. Must be a list of two integers.")
        if(sum(range_minutes)==0):
            return self.interaction_data.copy()
        data_subset = self.interaction_data[(self.interaction_data['Minutes']>=range_minutes[0]) & (self.interaction_data['Minutes']<=range_minutes[1])]
        data_subset.reset_index(drop=True, inplace=True)
        return data_subset

    def get_frames_interacting(self, range_minutes=(0,0)):
        data = self.get_interaction_subset(range_minutes)
        results =[]
        for dist in self.parameters.interaction_distance_mm:
            results.append(data[f'Interaction_{dist}'].sum()) 
        return results
    
    def get_total_frames_with_valid_neighbor(self, range_minutes=(0,0)):
        data = self.get_data_subset(range_minutes)
        return data['IsNeighborValid'].sum()

    def get_mean_neighbor_distance(self, range_minutes=(0,0)):
        data = self.get_data_subset(range_minutes)
        return data['ClosestNeighbor_mm'].mean()

    def get_median_neighbor_distance(self, range_minutes=(0,0)):
        data = self.get_data_subset(range_minutes)
        return data['ClosestNeighbor_mm'].median()

    def is_partner(self, tracker):
        return self.tracking_region_id == tracker.tracking_region_id
    
    def update_neighbor_interactions(self):
        self.interaction_data = self.rawdata.loc[:,['Minutes','Indicator','ClosestNeighbor_mm','IsNeighborValid']]
        for dist in self.parameters.interaction_distance_mm:
            self.interaction_data[f'Interaction_{dist}'] = (self.interaction_data['ClosestNeighbor_mm'] < dist) & (self.interaction_data['IsNeighborValid'])    
      
    def summarize(self, range_minutes=(0,0)):        
        tmp = Tracker.Tracker.summarize(self, range_minutes)
        mean_neighbor_distance = self.get_mean_neighbor_distance(range_minutes)
        median_neighbor_distance = self.get_median_neighbor_distance(range_minutes)
        frames_interacting = self.get_frames_interacting(range_minutes)
        total_valid_frames = self.get_total_frames_with_valid_neighbor(range_minutes)
        percent_frames_interacting = [x/total_valid_frames for x in frames_interacting]
        
        distance_names = [f"FramesInteracting_{dist}" for dist in self.parameters.interaction_distance_mm]    
        distance_names2 = [f"PercentInteracting_{dist}" for dist in self.parameters.interaction_distance_mm]    
        
        frames_interacting_series = pd.Series(frames_interacting, index=distance_names)
        percent_frames_interacting_series = pd.Series(percent_frames_interacting, index=distance_names2)
        
        result = pd.concat([tmp,pd.Series({'MeanDistance': mean_neighbor_distance}),pd.Series({"MedianDistance" : median_neighbor_distance}),\
            pd.Series({'ValidFrames': total_valid_frames}),frames_interacting_series,percent_frames_interacting_series])

        return result