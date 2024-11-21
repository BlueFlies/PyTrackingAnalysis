import pandas as pd
import numpy as np 
import Counter
import PairwiseInteractionTracker
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class PairwiseInteractionCounter(Counter.Counter):
    def __init__(self, tracking_region_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        super().__init__(tracking_region_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)   
        ## I think that we can just create two pseudo partner trackers, make sure we have observations for each frame for both
        ## and then pass everything to corresponding tracker functions
         
        object_ids = self.rawdata['ObjectID'].unique()
        if(len(object_ids)<2):
            raise ValueError(f"Insufficient data for PairwiseInteractionCounter: {tracking_region_id}. Must have at least two objects.")    
        elif(len(object_ids)>2):
            print("Too many objects for PairwiseInteractionCounter.  Only the first two will be used.")
            object_ids = object_ids.drop(object_ids.index[-1])  
        
        trackers=[]
        for object_id in object_ids:
            ## Create a pseudo tracker for each object.
            tmp = PairwiseInteractionTracker.PairwiseInteractionTracker(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)    
            trackers.append(tmp)

        trackers[0].set_neighbor(trackers[1])
        trackers[1].set_neighbor(trackers[0])
      
    def summarize(self, range_minutes=(0,0)):        
        #tmp = Counter.Counter.summarize(self, range_minutes)
        #tmp2 = self.trackers[0].summarize(range_minutes)
        #tmp3 = self.trackers[1].summarize(range_minutes)

        return tmp2
    
   